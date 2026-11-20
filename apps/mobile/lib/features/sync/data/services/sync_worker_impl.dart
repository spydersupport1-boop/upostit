import 'dart:async';
import 'dart:convert';
import 'package:uuid/uuid.dart';
import '../../../../core/errors/app_exception.dart';
import '../../../attendance/data/datasources/attendance_remote_data_source.dart';
import '../../../attendance/data/models/punch_request_model.dart';
import '../../domain/entities/local_queue_item.dart';
import '../../domain/entities/sync_result.dart';
import '../../domain/entities/sync_status.dart';
import '../../domain/repositories/local_queue_dao.dart';
import '../../domain/repositories/network_connectivity_service.dart';
import '../../domain/repositories/sync_worker.dart';

/// Concrete implementation of [SyncWorker] executing strict FIFO queue synchronization,
/// account-level mutex locking, exponential backoff, crash recovery, and session quarantine.
class SyncWorkerImpl implements SyncWorker {
  final LocalQueueDao _localQueueDao;
  final AttendanceRemoteDataSource _remoteDataSource;
  final NetworkConnectivityService? _connectivityService;
  final void Function(String message)? _onAccountDeactivated;

  final Duration _initialBackoff;
  final Duration _maxBackoff;

  final Set<String> _activeWorkers = <String>{};
  final StreamController<SyncResult> _syncResultsController =
      StreamController<SyncResult>.broadcast();

  StreamSubscription<bool>? _connectivitySubscription;
  String? _autoSyncTenantId;
  String? _autoSyncUserId;
  bool _isDisposed = false;

  SyncWorkerImpl({
    required LocalQueueDao localQueueDao,
    required AttendanceRemoteDataSource remoteDataSource,
    NetworkConnectivityService? connectivityService,
    void Function(String message)? onAccountDeactivated,
    Duration initialBackoff = const Duration(seconds: 2),
    Duration maxBackoff = const Duration(seconds: 60),
  })  : _localQueueDao = localQueueDao,
        _remoteDataSource = remoteDataSource,
        _connectivityService = connectivityService,
        _onAccountDeactivated = onAccountDeactivated,
        _initialBackoff = initialBackoff,
        _maxBackoff = maxBackoff;

  @override
  Stream<SyncResult> get syncResults => _syncResultsController.stream;

  @override
  bool isSyncing(String tenantId, String userId) {
    return _activeWorkers.contains(_accountKey(tenantId, userId));
  }

  String _accountKey(String tenantId, String userId) => '$tenantId::$userId';

  @override
  Future<SyncResult> synchronizeQueue({
    required String tenantId,
    required String userId,
  }) async {
    if (_isDisposed) {
      return const SyncResult(
        isCompleted: false,
        errorMessage: 'SyncWorker is disposed.',
      );
    }

    final key = _accountKey(tenantId, userId);

    // 1. Single-worker mutex lock per account
    if (_activeWorkers.contains(key)) {
      return const SyncResult(
        isCompleted: false,
        errorMessage: 'Synchronization is already active for this account.',
      );
    }
    _activeWorkers.add(key);

    int syncedCount = 0;
    int permanentlyRejectedCount = 0;
    int quarantinedCount = 0;
    int retryableFailureCount = 0;
    String? fatalErrorMessage;
    int? retryAfterSeconds;

    try {
      // 2. Crash recovery: reset zombie records stranded in SYNCING state for > 120s
      await _localQueueDao.resetZombieSyncingItems(
        timeout: const Duration(seconds: 120),
      );

      // 3. Process pending items in strict FIFO order
      bool hasMore = true;
      while (hasMore && !_isDisposed) {
        final pendingBatch = await _localQueueDao.getPendingEventsFifo(
          tenantId: tenantId,
          userId: userId,
          limit: 20,
        );

        if (pendingBatch.isEmpty) {
          hasMore = false;
          break;
        }

        for (final item in pendingBatch) {
          if (_isDisposed) break;

          // Double check item status: may have been quarantined by earlier item in this batch
          final freshItem = await _localQueueDao.getEventById(item.localId);
          if (freshItem == null ||
              freshItem.syncStatus != SyncStatus.pendingSync) {
            continue;
          }

          // Transition to SYNCING (increments retry_count and updates last_attempted_at)
          await _localQueueDao.updateSyncStatus(
            localId: item.localId,
            status: SyncStatus.syncing,
          );

          // Build exact original PunchRequestModel preserving all evidence and idempotency key
          final punchRequest = _buildPunchRequest(item);

          try {
            final response = await _remoteDataSource.recordPunch(punchRequest);

            // Determine authoritative sync status
            final reviewStatus = response.event.reviewStatus;
            final isFlagged = reviewStatus == 'PENDING_REVIEW' ||
                reviewStatus == 'FLAGGED' ||
                reviewStatus == 'FLAG_DELAYED_OFFLINE_SYNC' ||
                reviewStatus == 'FLAG_OFFLINE_WINDOW_EXCEEDED';

            final resolvedStatus =
                isFlagged ? SyncStatus.flaggedPendingReview : SyncStatus.synced;

            await _localQueueDao.updateSyncStatus(
              localId: item.localId,
              status: resolvedStatus,
              serverEventId: response.event.id,
            );

            syncedCount++;
          } catch (e) {
            final classification = _classifyError(e);

            if (classification.isAccountDeactivated) {
              // Reset current item back to pending
              await _localQueueDao.updateSyncStatus(
                localId: item.localId,
                status: SyncStatus.pendingSync,
                errorMessage: classification.message,
                statusCode: classification.statusCode,
              );
              _onAccountDeactivated?.call(classification.message);
              fatalErrorMessage = classification.message;
              hasMore = false;
              break;
            } else if (classification.isAuthenticationFailure) {
              // Token refresh failed: pause synchronization and preserve local records
              await _localQueueDao.updateSyncStatus(
                localId: item.localId,
                status: SyncStatus.pendingSync,
                errorMessage: classification.message,
                statusCode: classification.statusCode,
              );
              fatalErrorMessage = classification.message;
              hasMore = false;
              break;
            } else if (classification.isPermanent) {
              // Permanent domain rejection
              await _localQueueDao.markPermanentlyRejected(
                localId: item.localId,
                errorMessage: classification.message,
                statusCode: classification.statusCode,
              );
              permanentlyRejectedCount++;

              // Cascade quarantine for dependent events belonging ONLY to this session
              final conflictBundleId = (item.conflictBundleId != null &&
                      item.conflictBundleId!.isNotEmpty)
                  ? item.conflictBundleId!
                  : const Uuid().v4();
              final quarantinedInSession =
                  await _localQueueDao.quarantineDependentEvents(
                tenantId: tenantId,
                userId: userId,
                conflictBundleId: conflictBundleId,
                fromLocalId: item.localId,
              );
              quarantinedCount += quarantinedInSession;

              // Continue processing remaining independent shifts/sessions
              continue;
            } else {
              // Retryable transient failure (network, timeout, 429, 5xx)
              await _localQueueDao.updateSyncStatus(
                localId: item.localId,
                status: SyncStatus.pendingSync,
                errorMessage: classification.message,
                statusCode: classification.statusCode,
              );
              retryableFailureCount++;
              fatalErrorMessage = classification.message;
              final backoff = calculateBackoff(item.retryCount);
              retryAfterSeconds =
                  classification.retryAfterSeconds ?? backoff.inSeconds;

              // Break loop to respect backoff and prevent overwhelming backend
              hasMore = false;
              break;
            }
          }
        }
      }
    } finally {
      _activeWorkers.remove(key);
    }

    final result = SyncResult(
      syncedCount: syncedCount,
      permanentlyRejectedCount: permanentlyRejectedCount,
      quarantinedCount: quarantinedCount,
      retryableFailureCount: retryableFailureCount,
      isCompleted: fatalErrorMessage == null && retryableFailureCount == 0,
      errorMessage: fatalErrorMessage,
      retryAfterSeconds: retryAfterSeconds,
    );

    if (!_syncResultsController.isClosed) {
      _syncResultsController.add(result);
    }

    return result;
  }

  /// Calculates exponential backoff duration based on retry count.
  Duration calculateBackoff(int retryCount) {
    if (retryCount <= 0) return _initialBackoff;
    final backoffMs = _initialBackoff.inMilliseconds * (1 << (retryCount - 1));
    final cappedMs = backoffMs > _maxBackoff.inMilliseconds
        ? _maxBackoff.inMilliseconds
        : backoffMs;
    return Duration(milliseconds: cappedMs);
  }

  PunchRequestModel _buildPunchRequest(LocalQueueItem item) {
    Map<String, dynamic> metadata = {};
    if (item.metadataJson.isNotEmpty && item.metadataJson != '{}') {
      try {
        metadata = jsonDecode(item.metadataJson) as Map<String, dynamic>;
      } catch (_) {}
    }

    metadata['monotonic_boot_time_ms'] = item.monotonicBootTimeMs;
    metadata['boot_session_id'] = item.bootSessionId;
    metadata['is_reboot_detected'] = item.isRebootDetected;
    metadata['offline_queued'] = true;
    metadata['offline_sequence_number'] = item.sequenceNumber;
    if (item.sessionId != null) {
      metadata['session_id'] = item.sessionId;
    }

    bool? isMockLocation;
    if (metadata.containsKey('is_mock_location') &&
        metadata['is_mock_location'] is bool) {
      isMockLocation = metadata['is_mock_location'] as bool;
    }
    DateTime? locationCapturedAt;
    if (metadata.containsKey('location_captured_at') &&
        metadata['location_captured_at'] is String) {
      locationCapturedAt =
          DateTime.tryParse(metadata['location_captured_at'] as String);
    }

    return PunchRequestModel(
      eventType: item.eventType,
      idempotencyKey: item.idempotencyKey,
      deviceReportedAt: item.deviceReportedAt,
      employeeId: item.employeeId,
      locationId: item.locationId,
      latitude: item.latitude,
      longitude: item.longitude,
      accuracyMeters: item.accuracyMeters,
      wifiBssid: item.wifiBssid,
      wifiSsid: item.wifiSsid,
      wifiSignalStatus: item.wifiSignalStatus,
      deviceId: item.deviceId,
      isMockLocation: isMockLocation,
      locationCapturedAt: locationCapturedAt,
      metadata: metadata,
    );
  }

  _ErrorClassification _classifyError(dynamic error) {
    if (error is AuthException) {
      final msg = error.message.toLowerCase();
      final isDeactivated =
          msg.contains('deactivated') || msg.contains('inactive');
      return _ErrorClassification(
        isPermanent: false,
        isRetryable: false,
        isAuthenticationFailure: true,
        isAccountDeactivated: isDeactivated,
        message: error.message,
        statusCode: error.statusCode ?? 401,
      );
    }

    if (error is NetworkException) {
      return _ErrorClassification(
        isPermanent: false,
        isRetryable: true,
        message: error.message,
      );
    }

    if (error is ServerException) {
      final code = error.statusCode;
      final msg = error.message.toLowerCase();

      // Check for account deactivation in 401 / 403
      if ((code == 401 || code == 403) &&
          (msg.contains('deactivated') || msg.contains('inactive'))) {
        return _ErrorClassification(
          isPermanent: false,
          isRetryable: false,
          isAccountDeactivated: true,
          message: error.message,
          statusCode: code,
        );
      }

      // HTTP 429: Rate limited
      if (code == 429) {
        int? retryAfter;
        if (error.details is Map && error.details['retry_after'] != null) {
          retryAfter = (error.details['retry_after'] as num).toInt();
        }
        return _ErrorClassification(
          isPermanent: false,
          isRetryable: true,
          message: error.message,
          statusCode: code,
          retryAfterSeconds: retryAfter ?? 15,
        );
      }

      // Retryable HTTP status codes: 408 (Timeout), 5xx (Server Errors)
      if (code == 408 || (code != null && code >= 500 && code < 600)) {
        return _ErrorClassification(
          isPermanent: false,
          isRetryable: true,
          message: error.message,
          statusCode: code,
        );
      }

      // Permanent domain errors: 400, 422, 403, 404, etc.
      if (code != null && code >= 400 && code < 500) {
        return _ErrorClassification(
          isPermanent: true,
          isRetryable: false,
          message: error.message,
          statusCode: code,
        );
      }

      return _ErrorClassification(
        isPermanent: false,
        isRetryable: true,
        message: error.message,
        statusCode: code,
      );
    }

    return _ErrorClassification(
      isPermanent: false,
      isRetryable: true,
      message: error.toString(),
    );
  }

  @override
  void startAutoSync({
    required String tenantId,
    required String userId,
  }) {
    _autoSyncTenantId = tenantId;
    _autoSyncUserId = userId;

    _connectivitySubscription?.cancel();
    final connectivity = _connectivityService;
    if (connectivity != null) {
      _connectivitySubscription =
          connectivity.onConnectivityRestored.listen((restored) {
        if (restored && _autoSyncTenantId != null && _autoSyncUserId != null) {
          synchronizeQueue(
            tenantId: _autoSyncTenantId!,
            userId: _autoSyncUserId!,
          );
        }
      });
    }
  }

  @override
  void stopAutoSync() {
    _autoSyncTenantId = null;
    _autoSyncUserId = null;
    _connectivitySubscription?.cancel();
    _connectivitySubscription = null;
  }

  @override
  Future<SyncResult?> onAppForegrounded() async {
    if (_isDisposed) return null;
    final tenantId = _autoSyncTenantId;
    final userId = _autoSyncUserId;
    if (tenantId == null || userId == null) return null;

    final connectivity = _connectivityService;
    if (connectivity != null) {
      final isConnected = await connectivity.isConnected();
      if (!isConnected) return null;
    }

    return synchronizeQueue(
      tenantId: tenantId,
      userId: userId,
    );
  }

  @override
  void dispose() {
    _isDisposed = true;
    stopAutoSync();
    _syncResultsController.close();
  }
}

class _ErrorClassification {
  final bool isPermanent;
  final bool isRetryable;
  final bool isAuthenticationFailure;
  final bool isAccountDeactivated;
  final String message;
  final int? statusCode;
  final int? retryAfterSeconds;

  const _ErrorClassification({
    required this.isPermanent,
    required this.isRetryable,
    this.isAuthenticationFailure = false,
    this.isAccountDeactivated = false,
    required this.message,
    this.statusCode,
    this.retryAfterSeconds,
  });
}
