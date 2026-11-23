import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_event.dart';
import 'package:mobile/features/sync/data/datasources/database_key_provider.dart';
import 'package:mobile/features/sync/data/datasources/downward_sync_dao.dart';
import 'package:mobile/features/sync/data/datasources/local_queue_database.dart';
import 'package:mobile/features/sync/data/datasources/sqflite_local_queue_dao.dart';
import 'package:mobile/features/sync/data/models/sync_delta_model.dart';
import 'package:mobile/features/sync/domain/entities/local_queue_item.dart';
import 'package:mobile/features/sync/domain/entities/sync_status.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

class TestKeyProvider implements DatabaseKeyProvider {
  @override
  Future<String> getEncryptionKey({required bool databaseExists}) async =>
      '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef';

  @override
  Future<String> getOrCreateEncryptionKey() async =>
      '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef';

  @override
  Future<String?> getExistingKey() async =>
      '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef';

  @override
  Future<void> clearKeyForTesting() async {}
}

void main() {
  setUpAll(() {
    sqfliteFfiInit();
  });

  group('SqfliteDownwardSyncDao', () {
    late LocalQueueDatabase dbHelper;
    late SqfliteDownwardSyncDao dao;
    late SqfliteLocalQueueDao queueDao;

    setUp(() async {
      dbHelper = LocalQueueDatabase(
        keyProvider: TestKeyProvider(),
        factory: databaseFactoryFfi,
        customPath: inMemoryDatabasePath,
      );
      await dbHelper.open();
      dao = SqfliteDownwardSyncDao(dbHelper);
      queueDao = SqfliteLocalQueueDao(database: dbHelper);
    });

    tearDown(() async {
      await dbHelper.close();
    });

    test('applies full delta transactionally and retrieves cached entities', () async {
      const delta = SyncDeltaModel(
        syncType: 'FULL',
        serverTime: '2026-11-23T02:00:00Z',
        nextCursor: 'cur_test_001',
        hasMore: false,
        employee: SyncEmployeeModel(
          id: 'emp-uuid-1',
          tenantId: 'tenant-uuid-1',
          employeeId: 'EMP-001',
          firstName: 'Alice',
          lastName: 'Smith',
          workEmail: 'alice@company.com',
          employmentType: 'full_time',
          status: 'active',
          updatedAt: '2026-11-23T01:50:00Z',
        ),
        shifts: [
          SyncShiftModel(
            id: 'shift-assign-1',
            shiftTemplateId: 'tmpl-1',
            name: 'Morning Shift',
            code: 'MORN',
            startTime: '09:00:00',
            endTime: '17:00:00',
            gracePeriodMinutes: 15,
            earlyExitGraceMinutes: 15,
            halfDayThresholdMinutes: 240,
            fullDayThresholdMinutes: 480,
            breakDurationMinutes: 60,
            isOvernight: false,
            isFlexible: false,
            weeklyOffDays: [6, 0],
            effectiveFrom: '2026-11-01',
            updatedAt: '2026-11-23T01:50:00Z',
          ),
        ],
        workplaces: [
          SyncWorkplaceModel(
            id: 'loc-1',
            name: 'Main HQ',
            code: 'HQ-1',
            addressLine1: '100 Core St',
            city: 'Metro',
            latitude: 12.9716,
            longitude: 77.5946,
            radiusMeters: 100,
            timezone: 'Asia/Kolkata',
            wifiBssids: ['00:11:22:33:44:55'],
            isActive: true,
            isAssigned: true,
            isPrimary: true,
            updatedAt: '2026-11-23T01:50:00Z',
          ),
        ],
        holidays: [
          SyncHolidayModel(
            id: 'hol-1',
            calendarId: 'cal-1',
            holidayDate: '2026-12-25',
            name: 'Christmas',
            holidayType: 'PUBLIC',
            isOptional: false,
            updatedAt: '2026-11-23T01:50:00Z',
          ),
        ],
        leaveBalances: [
          SyncLeaveBalanceModel(
            id: 'lb-1',
            leaveTypeId: 'lt-1',
            year: 2026,
            annualAllocation: 15.0,
            used: 3.0,
            availableBalance: 12.0,
            updatedAt: '2026-11-23T01:50:00Z',
          ),
        ],
        attendancePolicy: SyncAttendancePolicyModel(
          id: 'pol-1',
          version: 2,
          isActive: true,
          defaultMode: 'GPS_ONLY',
          allowedMethods: ['GPS_ONLY'],
          requiredMethods: ['GPS_ONLY'],
          combinationRule: 'OR',
          gpsConfig: {'max_accuracy_meters': 100},
          wifiConfig: {},
          updatedAt: '2026-11-23T01:50:00Z',
        ),
      );

      // Apply transactionally
      await dao.applyDeltaTransactionally(delta);

      // 1. Verify committed cursor
      final cursor = await dao.getCommittedCursor();
      expect(cursor, equals('cur_test_001'));

      // 2. Verify cached employee
      final emp = await dao.getCachedEmployee();
      expect(emp, isNotNull);
      expect(emp!['employee_id'], equals('EMP-001'));
      expect(emp['first_name'], equals('Alice'));

      // 3. Verify cached shifts
      final shifts = await dao.getCachedShifts();
      expect(shifts.length, equals(1));
      expect(shifts.first['name'], equals('Morning Shift'));

      // 4. Verify cached workplaces
      final workplaces = await dao.getCachedWorkplaces();
      expect(workplaces.length, equals(1));
      expect(workplaces.first['name'], equals('Main HQ'));
      expect(workplaces.first['is_primary'], equals(1));

      // 5. Verify cached holidays
      final holidays = await dao.getCachedHolidays();
      expect(holidays.length, equals(1));
      expect(holidays.first['name'], equals('Christmas'));

      // 6. Verify cached leave balances
      final balances = await dao.getCachedLeaveBalances();
      expect(balances.length, equals(1));
      expect(balances.first['available_balance'], equals(12.0));

      // 7. Verify cached attendance policy
      final policy = await dao.getCachedAttendancePolicy();
      expect(policy, isNotNull);
      expect(policy!['version'], equals(2));
      expect(policy['default_mode'], equals('GPS_ONLY'));
    });

    test('processes tombstones by deleting deactivated entities', () async {
      // Seed initial workplace
      const initialDelta = SyncDeltaModel(
        syncType: 'FULL',
        serverTime: '2026-11-23T02:00:00Z',
        nextCursor: 'cur_test_001',
        hasMore: false,
        workplaces: [
          SyncWorkplaceModel(
            id: 'loc-to-remove',
            name: 'Temp Branch',
            code: 'TMP-1',
            addressLine1: '99 Side St',
            city: 'Metro',
            latitude: 12.0,
            longitude: 77.0,
            radiusMeters: 50,
            timezone: 'UTC',
            wifiBssids: [],
            isActive: true,
            isAssigned: true,
            isPrimary: false,
            updatedAt: '2026-11-23T02:00:00Z',
          ),
        ],
      );
      await dao.applyDeltaTransactionally(initialDelta);
      expect((await dao.getCachedWorkplaces()).length, equals(1));

      // Delta with tombstone
      const tombstoneDelta = SyncDeltaModel(
        syncType: 'DELTA',
        serverTime: '2026-11-23T02:05:00Z',
        nextCursor: 'cur_test_002',
        hasMore: false,
        tombstones: [
          SyncTombstoneModel(
            entityType: 'workplace',
            entityId: 'loc-to-remove',
            deletedAt: '2026-11-23T02:05:00Z',
          ),
        ],
      );
      await dao.applyDeltaTransactionally(tombstoneDelta);

      // Verify workplace is deleted from local cache
      final workplaces = await dao.getCachedWorkplaces();
      expect(workplaces, isEmpty);
      expect(await dao.getCommittedCursor(), equals('cur_test_002'));
    });

    test('duplicate delta response is idempotent and replaces cache records without duplicates', () async {
      const delta = SyncDeltaModel(
        syncType: 'DELTA',
        serverTime: '2026-11-23T02:00:00Z',
        nextCursor: 'cur_idemp_001',
        hasMore: false,
        shifts: [
          SyncShiftModel(
            id: 'shift-idemp-1',
            shiftTemplateId: 'tmpl-idemp',
            name: 'Idempotent Shift',
            code: 'IDEMP',
            startTime: '09:00:00',
            endTime: '17:00:00',
            gracePeriodMinutes: 15,
            earlyExitGraceMinutes: 15,
            halfDayThresholdMinutes: 240,
            fullDayThresholdMinutes: 480,
            breakDurationMinutes: 60,
            isOvernight: false,
            isFlexible: false,
            weeklyOffDays: [6, 0],
            effectiveFrom: '2026-11-01',
            updatedAt: '2026-11-23T02:00:00Z',
          ),
        ],
      );

      // Apply first time
      await dao.applyDeltaTransactionally(delta);
      expect((await dao.getCachedShifts()).length, equals(1));
      expect(await dao.getCommittedCursor(), equals('cur_idemp_001'));

      // Apply exact duplicate delta second time
      await dao.applyDeltaTransactionally(delta);
      final shifts = await dao.getCachedShifts();
      expect(shifts.length, equals(1));
      expect(shifts.first['id'], equals('shift-idemp-1'));
      expect(shifts.first['name'], equals('Idempotent Shift'));
      expect(await dao.getCommittedCursor(), equals('cur_idemp_001'));
    });

    test('interrupted cache transaction rolls back inserts and leaves cursor unchanged', () async {
      await dao.saveCommittedCursor('cur_stable_before_fail', '2026-11-23T01:00:00Z');

      // Verify transaction rollback semantics on the local database
      final db = dbHelper.database;
      try {
        await db.transaction((txn) async {
          await txn.insert(
            LocalQueueDatabase.syncStateTable,
            {
              'key': 'last_downward_cursor',
              'value': 'cur_should_never_persist',
              'updated_at': DateTime.now().toUtc().toIso8601String(),
            },
            conflictAlgorithm: ConflictAlgorithm.replace,
          );
          await txn.insert(
            LocalQueueDatabase.cachedShiftsTable,
            {
              'id': 'shift-aborted-1',
              'tenant_id': 'tenant-fail',
              'shift_template_id': 'tmpl-fail',
              'name': 'Aborted Shift',
              'code': 'ABORT',
              'start_time': '09:00:00',
              'end_time': '17:00:00',
              'is_overnight': 0,
              'is_flexible': 0,
              'effective_from': '2026-11-01',
              'cached_at': DateTime.now().toUtc().toIso8601String(),
            },
            conflictAlgorithm: ConflictAlgorithm.replace,
          );
          // Simulate sudden crash or uncaught constraint error
          throw Exception('Simulated mid-transaction crash');
        });
      } catch (_) {
        // Exception caught as expected
      }

      // Assert rollback: cursor remains unchanged and shift was not inserted
      expect(await dao.getCommittedCursor(), equals('cur_stable_before_fail'));
      final shifts = await dao.getCachedShifts();
      expect(shifts.where((s) => s['id'] == 'shift-aborted-1'), isEmpty);
    });

    test('clearCacheExceptQueue preserves pending attendance queue completely', () async {
      final now = DateTime.now().toUtc();
      // 1. Insert a pending offline punch into attendance queue
      final queueItem = LocalQueueItem(
        localId: 'punch-local-001',
        idempotencyKey: 'idemp-key-001',
        tenantId: 'tenant-100',
        employeeId: 'emp-100',
        userId: 'user-100',
        eventType: AttendanceEventType.checkIn,
        deviceReportedAt: now,
        timezoneOffsetMinutes: 330,
        monotonicBootTimeMs: 1000000,
        bootSessionId: 'boot-123',
        appliedPolicyVersion: 1,
        appliedPolicyMode: 'MANUAL',
        sequenceNumber: 1,
        syncStatus: SyncStatus.pendingSync,
        createdAt: now,
        updatedAt: now,
      );
      await queueDao.insertPendingEvent(queueItem);

      // 2. Insert cached reference data
      await dao.applyDeltaTransactionally(
        const SyncDeltaModel(
          syncType: 'FULL',
          serverTime: '2026-11-23T02:00:00Z',
          nextCursor: 'cur_preserve_test',
          hasMore: false,
          employee: SyncEmployeeModel(
            id: 'emp-100',
            tenantId: 'tenant-100',
            employeeId: 'EMP-100',
            firstName: 'Preserve',
            lastName: 'Test',
            workEmail: 'preserve@test.com',
            employmentType: 'full_time',
            status: 'active',
            updatedAt: '2026-11-23T02:00:00Z',
          ),
        ),
      );

      expect((await dao.getCachedEmployee()), isNotNull);
      expect((await queueDao.getPendingEventsFifo(tenantId: 'tenant-100', userId: 'user-100')).length, equals(1));

      // 3. Clear cache
      await dao.clearCacheExceptQueue();

      // 4. Verify cached employee is cleared, BUT queue item remains 100% intact
      expect(await dao.getCachedEmployee(), isNull);
      final pendingQueue = await queueDao.getPendingEventsFifo(tenantId: 'tenant-100', userId: 'user-100');
      expect(pendingQueue.length, equals(1));
      expect(pendingQueue.first.localId, equals('punch-local-001'));
    });

    test('database migration to v2 creates cache tables without touching queue', () async {
      // 1. Check schema_version in metadata table
      final db = dbHelper.database;
      final metaRows = await db.query(
        LocalQueueDatabase.metadataTable,
        where: 'key = ?',
        whereArgs: ['schema_version'],
      );
      expect(metaRows, isNotEmpty);
      expect(metaRows.first['value'], equals('2'));

      // 2. Verify all new cache tables exist
      final tables = await db.rawQuery(
        "SELECT name FROM sqlite_master WHERE type='table';",
      );
      final tableNames = tables.map((t) => t['name'] as String).toSet();
      expect(tableNames.contains(LocalQueueDatabase.queueTable), isTrue);
      expect(tableNames.contains(LocalQueueDatabase.syncStateTable), isTrue);
      expect(tableNames.contains(LocalQueueDatabase.cachedEmployeeTable), isTrue);
      expect(tableNames.contains(LocalQueueDatabase.cachedShiftsTable), isTrue);
      expect(tableNames.contains(LocalQueueDatabase.cachedWorkplacesTable), isTrue);
      expect(tableNames.contains(LocalQueueDatabase.cachedHolidaysTable), isTrue);
      expect(tableNames.contains(LocalQueueDatabase.cachedLeaveTypesTable), isTrue);
      expect(tableNames.contains(LocalQueueDatabase.cachedLeaveBalancesTable), isTrue);
      expect(tableNames.contains(LocalQueueDatabase.cachedLeaveRequestsTable), isTrue);
      expect(tableNames.contains(LocalQueueDatabase.cachedAttendancePolicyTable), isTrue);
      expect(tableNames.contains(LocalQueueDatabase.cachedDirectReportsTable), isTrue);
    });
  });
}
