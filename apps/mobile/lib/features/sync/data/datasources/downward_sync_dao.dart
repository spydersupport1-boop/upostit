import 'package:sqflite_sqlcipher/sqflite.dart';
import '../models/sync_delta_model.dart';
import 'local_queue_database.dart';

/// Abstract contract for downward synchronization local persistence and offline caching.
abstract class DownwardSyncDao {
  Future<String?> getCommittedCursor();
  Future<void> saveCommittedCursor(String cursor, String serverTime);
  Future<void> applyDeltaTransactionally(SyncDeltaModel delta);
  Future<Map<String, dynamic>?> getCachedEmployee();
  Future<List<Map<String, dynamic>>> getCachedShifts();
  Future<List<Map<String, dynamic>>> getCachedWorkplaces();
  Future<List<Map<String, dynamic>>> getCachedHolidays();
  Future<List<Map<String, dynamic>>> getCachedLeaveTypes();
  Future<List<Map<String, dynamic>>> getCachedLeaveBalances();
  Future<List<Map<String, dynamic>>> getCachedLeaveRequests();
  Future<Map<String, dynamic>?> getCachedAttendancePolicy();
  Future<List<Map<String, dynamic>>> getCachedDirectReports();
  Future<void> clearCacheExceptQueue();
}

/// SQLite/SQLCipher implementation of DownwardSyncDao.
///
/// Ensures strict atomicity, crash-safe cursor advancement, and fail-closed isolation.
/// NEVER modifies, drops, or clears the pending attendance queue (local_attendance_queue).
class SqfliteDownwardSyncDao implements DownwardSyncDao {
  final LocalQueueDatabase _database;

  SqfliteDownwardSyncDao(this._database);

  Future<Database> get _db async {
    if (!_database.isOpen) {
      return await _database.open();
    }
    return _database.database;
  }

  @override
  Future<String?> getCommittedCursor() async {
    final db = await _db;
    final rows = await db.query(
      LocalQueueDatabase.syncStateTable,
      where: 'key = ?',
      whereArgs: ['last_downward_cursor'],
    );
    if (rows.isEmpty) return null;
    final val = rows.first['value'] as String?;
    return (val != null && val.trim().isNotEmpty) ? val : null;
  }

  @override
  Future<void> saveCommittedCursor(String cursor, String serverTime) async {
    final db = await _db;
    await db.transaction((txn) async {
      await txn.insert(
        LocalQueueDatabase.syncStateTable,
        {
          'key': 'last_downward_cursor',
          'value': cursor,
          'updated_at': DateTime.now().toUtc().toIso8601String(),
        },
        conflictAlgorithm: ConflictAlgorithm.replace,
      );
      await txn.insert(
        LocalQueueDatabase.syncStateTable,
        {
          'key': 'last_sync_timestamp',
          'value': serverTime,
          'updated_at': DateTime.now().toUtc().toIso8601String(),
        },
        conflictAlgorithm: ConflictAlgorithm.replace,
      );
    });
  }

  /// Helper to determine if an incoming entity update is stale compared to cached state.
  static bool isIncomingStale({
    required Map<String, dynamic>? existingRow,
    required String incomingUpdatedAt,
    int? incomingVersion,
  }) {
    if (existingRow == null) return false;

    // 1. Monotonic version comparison if version is tracked (e.g., Attendance Policy)
    if (incomingVersion != null && existingRow.containsKey('version')) {
      final existingVersion = (existingRow['version'] as num?)?.toInt();
      if (existingVersion != null) {
        if (incomingVersion < existingVersion) {
          return true; // Stale: incoming has lower version (e.g., version 5 cannot overwrite 6)
        }
        if (incomingVersion > existingVersion) {
          return false; // Newer version
        }
      }
    }

    // 2. Monotonic updated_at timestamp comparison
    final existingUpdatedStr = existingRow['updated_at'] as String?;
    if (existingUpdatedStr != null && existingUpdatedStr.isNotEmpty) {
      final existingDt = DateTime.tryParse(existingUpdatedStr);
      final incomingDt = DateTime.tryParse(incomingUpdatedAt);
      if (existingDt != null && incomingDt != null) {
        if (incomingDt.isBefore(existingDt)) {
          return true; // Stale: incoming has older timestamp
        }
      }
    }

    return false;
  }

  /// Helper to determine if a tombstone deletion is stale compared to cached state.
  static bool isTombstoneStale({
    required Map<String, dynamic>? existingRow,
    required String tombstoneDeletedAt,
  }) {
    if (existingRow == null) return false;
    final existingUpdatedStr = existingRow['updated_at'] as String?;
    if (existingUpdatedStr != null && existingUpdatedStr.isNotEmpty) {
      final existingDt = DateTime.tryParse(existingUpdatedStr);
      final tombstoneDt = DateTime.tryParse(tombstoneDeletedAt);
      if (existingDt != null && tombstoneDt != null) {
        // If entity was modified after the deletion timestamp, tombstone is stale!
        if (existingDt.isAfter(tombstoneDt)) {
          return true;
        }
      }
    }
    return false;
  }

  @override
  Future<void> applyDeltaTransactionally(SyncDeltaModel delta) async {
    final db = await _db;

    await db.transaction((txn) async {
      final nowIso = DateTime.now().toUtc().toIso8601String();
      String tenantId = '';
      String employeeId = '';

      // 1. Employee Profile Upsert with Stale Protection
      if (delta.employee != null) {
        tenantId = delta.employee!.tenantId;
        employeeId = delta.employee!.id;

        final existing = await txn.query(
          LocalQueueDatabase.cachedEmployeeTable,
          where: 'id = ?',
          whereArgs: [delta.employee!.id],
          limit: 1,
        );
        final existingRow = existing.isNotEmpty ? existing.first : null;

        if (!isIncomingStale(
          existingRow: existingRow,
          incomingUpdatedAt: delta.employee!.updatedAt,
        )) {
          await txn.insert(
            LocalQueueDatabase.cachedEmployeeTable,
            delta.employee!.toMap(),
            conflictAlgorithm: ConflictAlgorithm.replace,
          );
        }
      } else {
        // Fallback: retrieve existing cached employee tenant/id if available
        final existingEmp = await txn.query(
          LocalQueueDatabase.cachedEmployeeTable,
          limit: 1,
        );
        if (existingEmp.isNotEmpty) {
          tenantId = existingEmp.first['tenant_id'] as String? ?? '';
          employeeId = existingEmp.first['id'] as String? ?? '';
        }
      }

      // 2. Shifts Upsert with Stale Protection
      for (final shift in delta.shifts) {
        final existing = await txn.query(
          LocalQueueDatabase.cachedShiftsTable,
          where: 'id = ?',
          whereArgs: [shift.id],
          limit: 1,
        );
        final existingRow = existing.isNotEmpty ? existing.first : null;

        if (!isIncomingStale(
          existingRow: existingRow,
          incomingUpdatedAt: shift.updatedAt,
        )) {
          await txn.insert(
            LocalQueueDatabase.cachedShiftsTable,
            shift.toMap(tenantId),
            conflictAlgorithm: ConflictAlgorithm.replace,
          );
        }
      }

      // 3. Workplaces & Geofences Upsert with Stale Protection
      for (final wp in delta.workplaces) {
        final existing = await txn.query(
          LocalQueueDatabase.cachedWorkplacesTable,
          where: 'id = ?',
          whereArgs: [wp.id],
          limit: 1,
        );
        final existingRow = existing.isNotEmpty ? existing.first : null;

        if (!isIncomingStale(
          existingRow: existingRow,
          incomingUpdatedAt: wp.updatedAt,
        )) {
          await txn.insert(
            LocalQueueDatabase.cachedWorkplacesTable,
            wp.toMap(tenantId),
            conflictAlgorithm: ConflictAlgorithm.replace,
          );
        }
      }

      // 4. Holidays Upsert with Stale Protection
      for (final hol in delta.holidays) {
        final existing = await txn.query(
          LocalQueueDatabase.cachedHolidaysTable,
          where: 'id = ?',
          whereArgs: [hol.id],
          limit: 1,
        );
        final existingRow = existing.isNotEmpty ? existing.first : null;

        if (!isIncomingStale(
          existingRow: existingRow,
          incomingUpdatedAt: hol.updatedAt,
        )) {
          await txn.insert(
            LocalQueueDatabase.cachedHolidaysTable,
            hol.toMap(tenantId),
            conflictAlgorithm: ConflictAlgorithm.replace,
          );
        }
      }

      // 5. Leave Types Upsert with Stale Protection
      for (final lt in delta.leaveTypes) {
        final existing = await txn.query(
          LocalQueueDatabase.cachedLeaveTypesTable,
          where: 'id = ?',
          whereArgs: [lt.id],
          limit: 1,
        );
        final existingRow = existing.isNotEmpty ? existing.first : null;

        if (!isIncomingStale(
          existingRow: existingRow,
          incomingUpdatedAt: lt.updatedAt,
        )) {
          await txn.insert(
            LocalQueueDatabase.cachedLeaveTypesTable,
            lt.toMap(tenantId),
            conflictAlgorithm: ConflictAlgorithm.replace,
          );
        }
      }

      // 6. Leave Balances Upsert with Stale Protection
      for (final lb in delta.leaveBalances) {
        final existing = await txn.query(
          LocalQueueDatabase.cachedLeaveBalancesTable,
          where: 'id = ?',
          whereArgs: [lb.id],
          limit: 1,
        );
        final existingRow = existing.isNotEmpty ? existing.first : null;

        if (!isIncomingStale(
          existingRow: existingRow,
          incomingUpdatedAt: lb.updatedAt,
        )) {
          await txn.insert(
            LocalQueueDatabase.cachedLeaveBalancesTable,
            lb.toMap(tenantId, employeeId),
            conflictAlgorithm: ConflictAlgorithm.replace,
          );
        }
      }

      // 7. Leave Requests Upsert with Stale Protection
      for (final lr in delta.leaveRequests) {
        final existing = await txn.query(
          LocalQueueDatabase.cachedLeaveRequestsTable,
          where: 'id = ?',
          whereArgs: [lr.id],
          limit: 1,
        );
        final existingRow = existing.isNotEmpty ? existing.first : null;

        if (!isIncomingStale(
          existingRow: existingRow,
          incomingUpdatedAt: lr.updatedAt,
        )) {
          await txn.insert(
            LocalQueueDatabase.cachedLeaveRequestsTable,
            lr.toMap(tenantId, employeeId),
            conflictAlgorithm: ConflictAlgorithm.replace,
          );
        }
      }

      // 8. Attendance Policy Upsert with Monotonic Version Protection
      if (delta.attendancePolicy != null) {
        final existing = await txn.query(
          LocalQueueDatabase.cachedAttendancePolicyTable,
          where: 'id = ?',
          whereArgs: [delta.attendancePolicy!.id],
          limit: 1,
        );
        final existingRow = existing.isNotEmpty ? existing.first : null;

        if (!isIncomingStale(
          existingRow: existingRow,
          incomingUpdatedAt: delta.attendancePolicy!.updatedAt,
          incomingVersion: delta.attendancePolicy!.version,
        )) {
          await txn.insert(
            LocalQueueDatabase.cachedAttendancePolicyTable,
            delta.attendancePolicy!.toMap(tenantId),
            conflictAlgorithm: ConflictAlgorithm.replace,
          );
        }
      }

      // 9. Direct Reports Upsert with Stale Protection
      if (delta.reportingHierarchy != null) {
        for (final dr in delta.reportingHierarchy!.directReports) {
          final existing = await txn.query(
            LocalQueueDatabase.cachedDirectReportsTable,
            where: 'id = ?',
            whereArgs: [dr.id],
            limit: 1,
          );
          final existingRow = existing.isNotEmpty ? existing.first : null;

          if (!isIncomingStale(
            existingRow: existingRow,
            incomingUpdatedAt: dr.updatedAt,
          )) {
            await txn.insert(
              LocalQueueDatabase.cachedDirectReportsTable,
              dr.toMap(tenantId),
              conflictAlgorithm: ConflictAlgorithm.replace,
            );
          }
        }
      }

      // 10. Process Tombstones with Monotonic Stale Protection
      for (final tomb in delta.tombstones) {
        String targetTable = '';
        switch (tomb.entityType) {
          case 'shift':
            targetTable = LocalQueueDatabase.cachedShiftsTable;
            break;
          case 'workplace':
            targetTable = LocalQueueDatabase.cachedWorkplacesTable;
            break;
          case 'holiday':
            targetTable = LocalQueueDatabase.cachedHolidaysTable;
            break;
          case 'leave_request':
            targetTable = LocalQueueDatabase.cachedLeaveRequestsTable;
            break;
          case 'leave_balance':
            targetTable = LocalQueueDatabase.cachedLeaveBalancesTable;
            break;
        }

        if (targetTable.isNotEmpty) {
          final existing = await txn.query(
            targetTable,
            where: 'id = ?',
            whereArgs: [tomb.entityId],
            limit: 1,
          );
          final existingRow = existing.isNotEmpty ? existing.first : null;

          if (!isTombstoneStale(
            existingRow: existingRow,
            tombstoneDeletedAt: tomb.deletedAt,
          )) {
            await txn.delete(
              targetTable,
              where: 'id = ?',
              whereArgs: [tomb.entityId],
            );
          }
        }
      }

      // 11. Advance Cursor and Sync Timestamp atomically within same transaction
      if (delta.nextCursor.isNotEmpty) {
        await txn.insert(
          LocalQueueDatabase.syncStateTable,
          {
            'key': 'last_downward_cursor',
            'value': delta.nextCursor,
            'updated_at': nowIso,
          },
          conflictAlgorithm: ConflictAlgorithm.replace,
        );
      }
      if (delta.serverTime.isNotEmpty) {
        await txn.insert(
          LocalQueueDatabase.syncStateTable,
          {
            'key': 'last_sync_timestamp',
            'value': delta.serverTime,
            'updated_at': nowIso,
          },
          conflictAlgorithm: ConflictAlgorithm.replace,
        );
      }
    });
  }

  @override
  Future<Map<String, dynamic>?> getCachedEmployee() async {
    final db = await _db;
    final rows = await db.query(LocalQueueDatabase.cachedEmployeeTable, limit: 1);
    if (rows.isEmpty) return null;
    return rows.first;
  }

  @override
  Future<List<Map<String, dynamic>>> getCachedShifts() async {
    final db = await _db;
    return await db.query(
      LocalQueueDatabase.cachedShiftsTable,
      orderBy: 'effective_from DESC',
    );
  }

  @override
  Future<List<Map<String, dynamic>>> getCachedWorkplaces() async {
    final db = await _db;
    return await db.query(
      LocalQueueDatabase.cachedWorkplacesTable,
      where: 'is_active = 1',
      orderBy: 'is_primary DESC, name ASC',
    );
  }

  @override
  Future<List<Map<String, dynamic>>> getCachedHolidays() async {
    final db = await _db;
    return await db.query(
      LocalQueueDatabase.cachedHolidaysTable,
      orderBy: 'holiday_date ASC',
    );
  }

  @override
  Future<List<Map<String, dynamic>>> getCachedLeaveTypes() async {
    final db = await _db;
    return await db.query(
      LocalQueueDatabase.cachedLeaveTypesTable,
      orderBy: 'name ASC',
    );
  }

  @override
  Future<List<Map<String, dynamic>>> getCachedLeaveBalances() async {
    final db = await _db;
    return await db.query(
      LocalQueueDatabase.cachedLeaveBalancesTable,
      orderBy: 'year DESC',
    );
  }

  @override
  Future<List<Map<String, dynamic>>> getCachedLeaveRequests() async {
    final db = await _db;
    return await db.query(
      LocalQueueDatabase.cachedLeaveRequestsTable,
      orderBy: 'start_date DESC',
    );
  }

  @override
  Future<Map<String, dynamic>?> getCachedAttendancePolicy() async {
    final db = await _db;
    final rows = await db.query(
      LocalQueueDatabase.cachedAttendancePolicyTable,
      where: 'is_active = 1',
      orderBy: 'version DESC',
      limit: 1,
    );
    if (rows.isEmpty) return null;
    return rows.first;
  }

  @override
  Future<List<Map<String, dynamic>>> getCachedDirectReports() async {
    final db = await _db;
    return await db.query(
      LocalQueueDatabase.cachedDirectReportsTable,
      orderBy: 'last_name ASC, first_name ASC',
    );
  }

  @override
  Future<void> clearCacheExceptQueue() async {
    final db = await _db;
    await db.transaction((txn) async {
      await txn.delete(LocalQueueDatabase.syncStateTable);
      await txn.delete(LocalQueueDatabase.cachedEmployeeTable);
      await txn.delete(LocalQueueDatabase.cachedShiftsTable);
      await txn.delete(LocalQueueDatabase.cachedWorkplacesTable);
      await txn.delete(LocalQueueDatabase.cachedHolidaysTable);
      await txn.delete(LocalQueueDatabase.cachedLeaveTypesTable);
      await txn.delete(LocalQueueDatabase.cachedLeaveBalancesTable);
      await txn.delete(LocalQueueDatabase.cachedLeaveRequestsTable);
      await txn.delete(LocalQueueDatabase.cachedAttendancePolicyTable);
      await txn.delete(LocalQueueDatabase.cachedDirectReportsTable);
      // NOTE: local_attendance_queue is deliberately NOT deleted!
    });
  }
}

