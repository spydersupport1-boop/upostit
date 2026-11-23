import 'dart:async';
import '../../../../core/errors/app_exception.dart';
import '../../domain/entities/downward_sync_result.dart';
import '../../domain/repositories/network_connectivity_service.dart';
import '../datasources/downward_sync_dao.dart';
import '../datasources/downward_sync_remote_data_source.dart';

/// Orchestrates downward delta synchronization for reference data and shift rosters.
///
/// Ensures:
/// - Single-flight synchronization via concurrency mutex.
/// - Resilient pagination loop with bounded pages.
/// - Automatic cursor recovery if cursor is corrupted or rejected.
/// - Graceful offline fallbacks retaining cached data.
/// - Zero impact on the pending attendance queue.
class DownwardSyncCoordinator {
  final DownwardSyncRemoteDataSource _remoteDataSource;
  final DownwardSyncDao _dao;
  final NetworkConnectivityService? _connectivityService;

  bool _isSyncing = false;
  Future<DownwardSyncResult>? _activeSyncFuture;

  final _syncResultController = StreamController<DownwardSyncResult>.broadcast();
  Stream<DownwardSyncResult> get syncResults => _syncResultController.stream;

  DownwardSyncCoordinator({
    required DownwardSyncRemoteDataSource remoteDataSource,
    required DownwardSyncDao dao,
    NetworkConnectivityService? connectivityService,
  })  : _remoteDataSource = remoteDataSource,
        _dao = dao,
        _connectivityService = connectivityService;

  bool get isSyncing => _isSyncing;

  /// Executes downward delta synchronization.
  ///
  /// If [forceFull] is true, ignores committed cursor and pulls a complete full reference snapshot.
  Future<DownwardSyncResult> sync({bool forceFull = false}) async {
    // 1. Concurrency Mutex: deduplicate concurrent sync requests
    if (_isSyncing && _activeSyncFuture != null) {
      return await _activeSyncFuture!;
    }

    _isSyncing = true;
    final completer = Completer<DownwardSyncResult>();
    _activeSyncFuture = completer.future;

    try {
      final result = await _executeSyncInternal(forceFull: forceFull);
      if (!_syncResultController.isClosed) {
        _syncResultController.add(result);
      }
      completer.complete(result);
      return result;
    } catch (e) {
      final fail = DownwardSyncResult.failure(e.toString());
      if (!_syncResultController.isClosed) {
        _syncResultController.add(fail);
      }
      completer.complete(fail);
      return fail;
    } finally {
      _isSyncing = false;
      _activeSyncFuture = null;
    }
  }

  Future<DownwardSyncResult> _executeSyncInternal({required bool forceFull}) async {
    // 2. Connectivity verification
    if (_connectivityService != null) {
      final connected = await _connectivityService.isConnected();
      if (!connected) {
        return DownwardSyncResult.offline();
      }
    }

    // 3. Resolve starting cursor
    String? cursor;
    if (!forceFull) {
      cursor = await _dao.getCommittedCursor();
    }

    int totalItemsSynced = 0;
    String finalSyncType = cursor == null ? 'FULL' : 'DELTA';
    bool hasMore = true;
    int pageCount = 0;
    const int maxPages = 20; // Circuit breaker to prevent runaway pagination

    while (hasMore && pageCount < maxPages) {
      pageCount++;
      try {
        final delta = await _remoteDataSource.fetchDelta(
          cursor: cursor,
          limit: 50,
        );

        finalSyncType = delta.syncType;
        final pageItemCount = (delta.employee != null ? 1 : 0) +
            delta.shifts.length +
            delta.workplaces.length +
            delta.holidays.length +
            delta.leaveTypes.length +
            delta.leaveBalances.length +
            delta.leaveRequests.length +
            (delta.attendancePolicy != null ? 1 : 0) +
            (delta.reportingHierarchy?.directReports.length ?? 0) +
            delta.tombstones.length;

        totalItemsSynced += pageItemCount;

        // Atomically apply delta and advance cursor in SQLite
        await _dao.applyDeltaTransactionally(delta);

        hasMore = delta.hasMore;
        cursor = delta.nextCursor;
      } on ServerException catch (e) {
        // 4. Cursor Corruption / Rejection Recovery
        if (e.statusCode == 400 && cursor != null) {
          // If server rejected cursor, clear cursor and attempt clean full sync once
          await _dao.clearCacheExceptQueue();
          cursor = null;
          final recoveryDelta = await _remoteDataSource.fetchDelta(
            cursor: null,
            limit: 50,
          );
          await _dao.applyDeltaTransactionally(recoveryDelta);
          return DownwardSyncResult.success(
            syncType: 'FULL_RECOVERY',
            itemsSynced: recoveryDelta.shifts.length + recoveryDelta.workplaces.length,
          );
        }
        rethrow;
      }
    }

    return DownwardSyncResult.success(
      syncType: finalSyncType,
      itemsSynced: totalItemsSynced,
    );
  }

  /// Hook: Triggered after successful employee authentication.
  Future<DownwardSyncResult> syncOnAuthSuccess() async {
    return await sync(forceFull: false);
  }

  /// Hook: Triggered after attendance punch batch upload finishes.
  Future<DownwardSyncResult> syncAfterBatchUpload() async {
    return await sync(forceFull: false);
  }

  /// Hook: Triggered on user manual refresh / pull-to-refresh.
  Future<DownwardSyncResult> syncManual({bool forceFull = false}) async {
    return await sync(forceFull: forceFull);
  }

  void dispose() {
    _syncResultController.close();
  }
}
