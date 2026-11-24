import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../datasources/local_queue_database.dart';
import 'background_sync_scheduler.dart';

/// Result summary of secure logout.
class SecureLogoutResult {
  final bool tokensPurged;
  final bool schedulerCancelled;
  final int cachedTablesPurged;
  final int preservedPendingPunches;
  final DateTime executedAt;

  const SecureLogoutResult({
    required this.tokensPurged,
    required this.schedulerCancelled,
    required this.cachedTablesPurged,
    required this.preservedPendingPunches,
    required this.executedAt,
  });
}

/// Orchestrates secure local logout and tenant/user switching isolation:
/// - Removes authentication tokens from secure storage.
/// - Cancels background synchronization workers.
/// - Purges user-specific cached reference tables (preventing data leakage across accounts).
/// - Enforces Attendance Ledger Preservation: NEVER deletes pending offline attendance events.
/// - Closes database connections safely.
class SecureLogoutCoordinator {
  final FlutterSecureStorage _storage;
  final LocalQueueDatabase _database;
  final BackgroundSyncScheduler? _scheduler;

  SecureLogoutCoordinator({
    required FlutterSecureStorage storage,
    required LocalQueueDatabase database,
    BackgroundSyncScheduler? scheduler,
  })  : _storage = storage,
        _database = database,
        _scheduler = scheduler;

  /// Executes secure logout sequence preserving pending attendance queue.
  Future<SecureLogoutResult> executeSecureLogout({
    required String tenantId,
    required String userId,
  }) async {
    final now = DateTime.now().toUtc();
    debugPrint('SecureLogoutCoordinator: Starting secure logout for user $userId in tenant $tenantId');

    // 1. Cancel background sync scheduler
    bool schedulerCancelled = false;
    try {
      if (_scheduler != null) {
        await _scheduler.cancelPeriodicSync();
        schedulerCancelled = true;
      }
    } catch (e) {
      debugPrint('SecureLogoutCoordinator: Warning cancelling scheduler: $e');
    }

    // 2. Remove sensitive tokens from secure storage
    bool tokensPurged = false;
    try {
      await _storage.delete(key: 'access_token');
      await _storage.delete(key: 'refresh_token');
      await _storage.delete(key: 'token_expiry');
      tokensPurged = true;
    } catch (e) {
      debugPrint('SecureLogoutCoordinator: Warning deleting auth tokens: $e');
    }

    int preservedPending = 0;
    int purgedTables = 0;

    // 3. Purge cached reference data while strictly preserving pending attendance queue
    try {
      if (!_database.isOpen) {
        await _database.open();
      }
      final db = _database.database;

      // Count preserved unacknowledged punches
      final countRes = await db.rawQuery('''
        SELECT COUNT(*) AS pending_count
        FROM ${LocalQueueDatabase.queueTable}
        WHERE tenant_id = ? AND user_id = ?
          AND sync_status IN ('PENDING_SYNC', 'SYNCING', 'QUARANTINED_DEPENDENT_FAILURE', 'FLAGGED_PENDING_REVIEW')
      ''', [tenantId, userId]);
      preservedPending = (countRes.isNotEmpty ? countRes.first['pending_count'] as int? : null) ?? 0;

      // Purge cached reference tables to prevent multi-tenant / account data leakage
      final cacheTables = [
        LocalQueueDatabase.cachedEmployeeTable,
        LocalQueueDatabase.cachedShiftsTable,
        LocalQueueDatabase.cachedWorkplacesTable,
        LocalQueueDatabase.cachedHolidaysTable,
        LocalQueueDatabase.cachedLeaveTypesTable,
        LocalQueueDatabase.cachedLeaveBalancesTable,
        LocalQueueDatabase.cachedLeaveRequestsTable,
        LocalQueueDatabase.cachedAttendancePolicyTable,
        LocalQueueDatabase.cachedDirectReportsTable,
      ];

      for (final table in cacheTables) {
        try {
          await db.delete(table);
          purgedTables++;
        } catch (_) {}
      }

      debugPrint(
        'SecureLogoutCoordinator: Purged $purgedTables cached reference tables. '
        'Preserved $preservedPending pending attendance events for offline safety.',
      );
    } catch (e) {
      debugPrint('SecureLogoutCoordinator: Error during cache purge: $e');
    }

    // 4. Close database cleanly
    try {
      await _database.close();
    } catch (_) {}

    return SecureLogoutResult(
      tokensPurged: tokensPurged,
      schedulerCancelled: schedulerCancelled,
      cachedTablesPurged: purgedTables,
      preservedPendingPunches: preservedPending,
      executedAt: now,
    );
  }
}
