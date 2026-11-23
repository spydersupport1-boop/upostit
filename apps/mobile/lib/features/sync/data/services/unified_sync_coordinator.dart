import 'dart:async';
import 'package:equatable/equatable.dart';
import '../../domain/entities/downward_sync_result.dart';
import '../../domain/entities/sync_result.dart';
import '../../domain/repositories/local_queue_dao.dart';
import '../../domain/repositories/network_connectivity_service.dart';
import '../../domain/repositories/sync_worker.dart';
import '../datasources/downward_sync_dao.dart';
import 'downward_sync_coordinator.dart';

/// Granular operational phases of unified synchronization.
enum UnifiedSyncPhase {
  idle,
  checkingConnectivity,
  uploadingAttendance,
  downloadingReferenceData,
  applyingLocalUpdates,
  waitingForRetry,
  partiallySynchronized,
  fullySynchronized,
  authenticationRequired,
  conflictRequiresReview,
  fatalLocalStorageError,
}

/// Progress event emitted during synchronization.
class UnifiedSyncProgress extends Equatable {
  final UnifiedSyncPhase phase;
  final String message;
  final int pendingUploadCount;
  final int syncedAttendanceCount;
  final int downloadedItemCount;
  final DateTime? lastSuccessfulUpload;
  final DateTime? lastSuccessfulDownload;
  final int? retryAfterSeconds;

  const UnifiedSyncProgress({
    required this.phase,
    required this.message,
    this.pendingUploadCount = 0,
    this.syncedAttendanceCount = 0,
    this.downloadedItemCount = 0,
    this.lastSuccessfulUpload,
    this.lastSuccessfulDownload,
    this.retryAfterSeconds,
  });

  @override
  List<Object?> get props => [
        phase,
        message,
        pendingUploadCount,
        syncedAttendanceCount,
        downloadedItemCount,
        lastSuccessfulUpload,
        lastSuccessfulDownload,
        retryAfterSeconds,
      ];
}

/// Comprehensive result of a unified sync pass.
class UnifiedSyncResult extends Equatable {
  final bool isCompleted;
  final SyncResult? upwardResult;
  final DownwardSyncResult? downwardResult;
  final bool isAuthRequired;
  final bool hasConflicts;
  final bool isFatalStorageError;
  final String? errorMessage;
  final DateTime? completedAt;

  const UnifiedSyncResult({
    required this.isCompleted,
    this.upwardResult,
    this.downwardResult,
    this.isAuthRequired = false,
    this.hasConflicts = false,
    this.isFatalStorageError = false,
    this.errorMessage,
    this.completedAt,
  });

  @override
  List<Object?> get props => [
        isCompleted,
        upwardResult,
        downwardResult,
        isAuthRequired,
        hasConflicts,
        isFatalStorageError,
        errorMessage,
        completedAt,
      ];
}

/// Orchestrates both upward (attendance ledger events) and downward (reference data & rosters)
/// synchronization in a cohesive, isolated, and crash-resilient manner.
class UnifiedSyncCoordinator {
  final SyncWorker _syncWorker;
  final DownwardSyncCoordinator _downwardCoordinator;
  final LocalQueueDao _localQueueDao;
  final DownwardSyncDao _downwardDao;
  final NetworkConnectivityService? _connectivityService;

  final StreamController<UnifiedSyncProgress> _progressController =
      StreamController<UnifiedSyncProgress>.broadcast();

  bool _isSyncing = false;
  Future<UnifiedSyncResult>? _activeSyncFuture;
  DateTime? _lastSuccessfulUpload;
  DateTime? _lastSuccessfulDownload;

  UnifiedSyncCoordinator({
    required SyncWorker syncWorker,
    required DownwardSyncCoordinator downwardCoordinator,
    required LocalQueueDao localQueueDao,
    required DownwardSyncDao downwardDao,
    NetworkConnectivityService? connectivityService,
  })  : _syncWorker = syncWorker,
        _downwardCoordinator = downwardCoordinator,
        _localQueueDao = localQueueDao,
        _downwardDao = downwardDao,
        _connectivityService = connectivityService;

  Stream<UnifiedSyncProgress> get progressStream => _progressController.stream;
  bool get isSyncing => _isSyncing;
  DateTime? get lastSuccessfulUpload => _lastSuccessfulUpload;
  DateTime? get lastSuccessfulDownload => _lastSuccessfulDownload;
  DownwardSyncDao get downwardDao => _downwardDao;

  void _emitProgress(UnifiedSyncProgress progress) {
    if (!_progressController.isClosed) {
      _progressController.add(progress);
    }
  }

  /// Executes unified synchronization for the authenticated user and tenant.
  Future<UnifiedSyncResult> synchronizeAll({
    required String tenantId,
    required String userId,
    bool forceFullDownward = false,
  }) async {
    // 1. Concurrency Mutex: prevent overlapping sync executions
    if (_isSyncing && _activeSyncFuture != null) {
      return await _activeSyncFuture!;
    }

    _isSyncing = true;
    final completer = Completer<UnifiedSyncResult>();
    _activeSyncFuture = completer.future;

    try {
      final result = await _executeUnifiedSync(
        tenantId: tenantId,
        userId: userId,
        forceFullDownward: forceFullDownward,
      );
      completer.complete(result);
      return result;
    } catch (e) {
      final fail = UnifiedSyncResult(
        isCompleted: false,
        errorMessage: 'Unified sync failed: ${e.toString()}',
        completedAt: DateTime.now().toUtc(),
      );
      completer.complete(fail);
      return fail;
    } finally {
      _isSyncing = false;
      _activeSyncFuture = null;
    }
  }

  Future<UnifiedSyncResult> _executeUnifiedSync({
    required String tenantId,
    required String userId,
    required bool forceFullDownward,
  }) async {
    // 2. Connectivity verification
    _emitProgress(const UnifiedSyncProgress(
      phase: UnifiedSyncPhase.checkingConnectivity,
      message: 'Checking network connectivity...',
    ));

    if (_connectivityService != null) {
      final isConnected = await _connectivityService.isConnected();
      if (!isConnected) {
        _emitProgress(const UnifiedSyncProgress(
          phase: UnifiedSyncPhase.waitingForRetry,
          message: 'Offline mode — no internet connection available.',
        ));
        return UnifiedSyncResult(
          isCompleted: false,
          errorMessage: 'Offline mode: No internet connection.',
          completedAt: DateTime.now().toUtc(),
        );
      }
    }

    // Read initial pending queue count
    int pendingCount = 0;
    try {
      pendingCount = await _localQueueDao.getPendingCount(
        tenantId: tenantId,
        userId: userId,
      );
    } catch (e) {
      _emitProgress(UnifiedSyncProgress(
        phase: UnifiedSyncPhase.fatalLocalStorageError,
        message: 'Storage error accessing offline queue: $e',
      ));
      return UnifiedSyncResult(
        isCompleted: false,
        isFatalStorageError: true,
        errorMessage: 'Local storage error: $e',
        completedAt: DateTime.now().toUtc(),
      );
    }

    // 3. Phase A: Upward Attendance Batch Synchronization
    _emitProgress(UnifiedSyncProgress(
      phase: UnifiedSyncPhase.uploadingAttendance,
      message: pendingCount > 0
          ? 'Uploading $pendingCount offline attendance punches...'
          : 'Checking offline queue...',
      pendingUploadCount: pendingCount,
    ));

    final SyncResult upwardResult = await _syncWorker.synchronizeQueue(
      tenantId: tenantId,
      userId: userId,
      useBatch: true,
    );

    if (upwardResult.syncedCount > 0) {
      _lastSuccessfulUpload = DateTime.now().toUtc();
    }

    // Handle authentication expiration during upward sync
    if (upwardResult.isAuthRequired) {
      _emitProgress(const UnifiedSyncProgress(
        phase: UnifiedSyncPhase.authenticationRequired,
        message: 'Session expired. Please log in to complete synchronization.',
      ));
      return UnifiedSyncResult(
        isCompleted: false,
        upwardResult: upwardResult,
        isAuthRequired: true,
        errorMessage: 'Authentication required.',
        completedAt: DateTime.now().toUtc(),
      );
    }

    // 4. Phase B: Downward Reference Data & Roster Synchronization
    _emitProgress(UnifiedSyncProgress(
      phase: UnifiedSyncPhase.downloadingReferenceData,
      message: 'Downloading shift schedules and workplace configurations...',
      syncedAttendanceCount: upwardResult.syncedCount,
    ));

    final DownwardSyncResult downwardResult = await _downwardCoordinator.sync(
      forceFull: forceFullDownward,
    );

    if (downwardResult.isSuccess) {
      _lastSuccessfulDownload = DateTime.now().toUtc();
    }

    // 5. Phase C: Applying Local Updates & Health Audit
    _emitProgress(const UnifiedSyncProgress(
      phase: UnifiedSyncPhase.applyingLocalUpdates,
      message: 'Applying local updates and validating sequence integrity...',
    ));

    // Check for sequence conflicts requiring review
    bool hasConflicts = false;
    try {
      final conflictBundles = await _localQueueDao.getConflictBundles(
        tenantId: tenantId,
        userId: userId,
      );
      hasConflicts = conflictBundles.isNotEmpty;
    } catch (_) {}

    // 6. Resolve final phase
    final nowUtc = DateTime.now().toUtc();
    final bool partialSuccess = upwardResult.retryableFailureCount > 0 ||
        downwardResult.isOffline ||
        downwardResult.isFailure;

    if (hasConflicts) {
      _emitProgress(UnifiedSyncProgress(
        phase: UnifiedSyncPhase.conflictRequiresReview,
        message: 'Attendance sequence conflict detected. Supervisor review required.',
        syncedAttendanceCount: upwardResult.syncedCount,
        downloadedItemCount: downwardResult.itemsSynced,
        lastSuccessfulUpload: _lastSuccessfulUpload,
        lastSuccessfulDownload: _lastSuccessfulDownload,
      ));
    } else if (partialSuccess) {
      _emitProgress(UnifiedSyncProgress(
        phase: UnifiedSyncPhase.partiallySynchronized,
        message: 'Partially synchronized. Some items will retry automatically.',
        syncedAttendanceCount: upwardResult.syncedCount,
        downloadedItemCount: downwardResult.itemsSynced,
        lastSuccessfulUpload: _lastSuccessfulUpload,
        lastSuccessfulDownload: _lastSuccessfulDownload,
        retryAfterSeconds: upwardResult.retryAfterSeconds,
      ));
    } else {
      _emitProgress(UnifiedSyncProgress(
        phase: UnifiedSyncPhase.fullySynchronized,
        message: 'All attendance events and reference data are up to date.',
        syncedAttendanceCount: upwardResult.syncedCount,
        downloadedItemCount: downwardResult.itemsSynced,
        lastSuccessfulUpload: _lastSuccessfulUpload,
        lastSuccessfulDownload: _lastSuccessfulDownload,
      ));
    }

    return UnifiedSyncResult(
      isCompleted: !partialSuccess && !hasConflicts,
      upwardResult: upwardResult,
      downwardResult: downwardResult,
      hasConflicts: hasConflicts,
      completedAt: nowUtc,
    );
  }

  void dispose() {
    _progressController.close();
  }
}

