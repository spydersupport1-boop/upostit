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

  @override
  Future<void> applyDeltaTransactionally(SyncDeltaModel delta) async {
    final db = await _db;

    await db.transaction((txn) async {
      final nowIso = DateTime.now().toUtc().toIso8601String();
      String tenantId = '';
      String employeeId = '';

      // 1. Employee Profile Upsert
      if (delta.employee != null) {
        tenantId = delta.employee!.tenantId;
        employeeId = delta.employee!.id;
        await txn.insert(
          LocalQueueDatabase.cachedEmployeeTable,
          delta.employee!.toMap(),
          conflictAlgorithm: ConflictAlgorithm.replace,
        );
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

      // 2. Shifts Upsert
      for (final shift in delta.shifts) {
        await txn.insert(
          LocalQueueDatabase.cachedShiftsTable,
          shift.toMap(tenantId),
          conflictAlgorithm: ConflictAlgorithm.replace,
        );
      }

      // 3. Workplaces & Geofences Upsert
      for (final wp in delta.workplaces) {
        await txn.insert(
          LocalQueueDatabase.cachedWorkplacesTable,
          wp.toMap(tenantId),
          conflictAlgorithm: ConflictAlgorithm.replace,
        );
      }

      // 4. Holidays Upsert
      for (final hol in delta.holidays) {
        await txn.insert(
          LocalQueueDatabase.cachedHolidaysTable,
          hol.toMap(tenantId),
          conflictAlgorithm: ConflictAlgorithm.replace,
        );
      }

      // 5. Leave Types Upsert
      for (final lt in delta.leaveTypes) {
        await txn.insert(
          LocalQueueDatabase.cachedLeaveTypesTable,
          lt.toMap(tenantId),
          conflictAlgorithm: ConflictAlgorithm.replace,
        );
      }

      // 6. Leave Balances Upsert
      for (final lb in delta.leaveBalances) {
        await txn.insert(
          LocalQueueDatabase.cachedLeaveBalancesTable,
          lb.toMap(tenantId, employeeId),
          conflictAlgorithm: ConflictAlgorithm.replace,
        );
      }

      // 7. Leave Requests Upsert
      for (final lr in delta.leaveRequests) {
        await txn.insert(
          LocalQueueDatabase.cachedLeaveRequestsTable,
          lr.toMap(tenantId, employeeId),
          conflictAlgorithm: ConflictAlgorithm.replace,
        );
      }

      // 8. Attendance Policy Upsert
      if (delta.attendancePolicy != null) {
        await txn.insert(
          LocalQueueDatabase.cachedAttendancePolicyTable,
          delta.attendancePolicy!.toMap(tenantId),
          conflictAlgorithm: ConflictAlgorithm.replace,
        );
      }

      // 9. Direct Reports Upsert
      if (delta.reportingHierarchy != null) {
        for (final dr in delta.reportingHierarchy!.directReports) {
          await txn.insert(
            LocalQueueDatabase.cachedDirectReportsTable,
            dr.toMap(tenantId),
            conflictAlgorithm: ConflictAlgorithm.replace,
          );
        }
      }

      // 10. Process Tombstones
      for (final tomb in delta.tombstones) {
        switch (tomb.entityType) {
          case 'shift':
            await txn.delete(
              LocalQueueDatabase.cachedShiftsTable,
              where: 'id = ?',
              whereArgs: [tomb.entityId],
            );
            break;
          case 'workplace':
            await txn.delete(
              LocalQueueDatabase.cachedWorkplacesTable,
              where: 'id = ?',
              whereArgs: [tomb.entityId],
            );
            break;
          case 'holiday':
            await txn.delete(
              LocalQueueDatabase.cachedHolidaysTable,
              where: 'id = ?',
              whereArgs: [tomb.entityId],
            );
            break;
          case 'leave_request':
            await txn.delete(
              LocalQueueDatabase.cachedLeaveRequestsTable,
              where: 'id = ?',
              whereArgs: [tomb.entityId],
            );
            break;
          case 'leave_balance':
            await txn.delete(
              LocalQueueDatabase.cachedLeaveBalancesTable,
              where: 'id = ?',
              whereArgs: [tomb.entityId],
            );
            break;
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

