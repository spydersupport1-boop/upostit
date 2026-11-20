import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/errors/app_exception.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_event.dart';
import 'package:mobile/features/sync/data/datasources/database_key_provider.dart';
import 'package:mobile/features/sync/data/datasources/local_queue_database.dart';
import 'package:mobile/features/sync/data/datasources/sqflite_local_queue_dao.dart';
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

LocalQueueItem createTestItem({
  required String localId,
  required String idempotencyKey,
  String? sessionId,
  String tenantId = 'tenant-100',
  String employeeId = 'emp-100',
  String userId = 'user-100',
  AttendanceEventType eventType = AttendanceEventType.checkIn,
  DateTime? deviceReportedAt,
  int timezoneOffsetMinutes = 330,
  int monotonicBootTimeMs = 5400000,
  String bootSessionId = 'boot-session-abc',
  bool isRebootDetected = false,
  double? latitude = 12.9716,
  double? longitude = 77.5946,
  double? accuracyMeters = 14.5,
  String? wifiBssid = '00:11:22:33:44:55',
  String? wifiSsid = 'Office_Secure_WiFi',
  String wifiSignalStatus = 'AVAILABLE',
  int appliedPolicyVersion = 1,
  String appliedPolicyMode = 'COMBINED',
  int sequenceNumber = 0,
  SyncStatus syncStatus = SyncStatus.pendingSync,
}) {
  final now = DateTime.now().toUtc();
  return LocalQueueItem(
    localId: localId,
    idempotencyKey: idempotencyKey,
    sessionId: sessionId,
    tenantId: tenantId,
    employeeId: employeeId,
    userId: userId,
    eventType: eventType,
    deviceReportedAt: deviceReportedAt ?? now,
    timezoneOffsetMinutes: timezoneOffsetMinutes,
    monotonicBootTimeMs: monotonicBootTimeMs,
    bootSessionId: bootSessionId,
    isRebootDetected: isRebootDetected,
    latitude: latitude,
    longitude: longitude,
    accuracyMeters: accuracyMeters,
    wifiBssid: wifiBssid,
    wifiSsid: wifiSsid,
    wifiSignalStatus: wifiSignalStatus,
    appliedPolicyVersion: appliedPolicyVersion,
    appliedPolicyMode: appliedPolicyMode,
    sequenceNumber: sequenceNumber,
    syncStatus: syncStatus,
    createdAt: now,
    updatedAt: now,
  );
}

void main() {
  setUpAll(() {
    sqfliteFfiInit();
  });

  group('SqfliteLocalQueueDao', () {
    late LocalQueueDatabase dbHelper;
    late SqfliteLocalQueueDao dao;

    setUp(() async {
      dbHelper = LocalQueueDatabase(
        keyProvider: TestKeyProvider(),
        factory: databaseFactoryFfi,
        customPath: inMemoryDatabasePath,
      );
      await dbHelper.open();
      dao = SqfliteLocalQueueDao(database: dbHelper);
    });

    tearDown(() async {
      await dbHelper.close();
    });

    test('assigns strictly monotonic sequence numbers per user session',
        () async {
      final punch1 = await dao.insertPendingEvent(
        createTestItem(localId: 'p1', idempotencyKey: 'idemp-1'),
      );
      final punch2 = await dao.insertPendingEvent(
        createTestItem(localId: 'p2', idempotencyKey: 'idemp-2'),
      );
      final punch3 = await dao.insertPendingEvent(
        createTestItem(localId: 'p3', idempotencyKey: 'idemp-3'),
      );

      expect(punch1.sequenceNumber, equals(1));
      expect(punch2.sequenceNumber, equals(2));
      expect(punch3.sequenceNumber, equals(3));
    });

    test('isolates sequence numbering between distinct users/tenants',
        () async {
      final userAPunch1 = await dao.insertPendingEvent(
        createTestItem(
            localId: 'ua-1', idempotencyKey: 'idemp-ua1', userId: 'user-A'),
      );
      final userBPunch1 = await dao.insertPendingEvent(
        createTestItem(
            localId: 'ub-1', idempotencyKey: 'idemp-ub1', userId: 'user-B'),
      );
      final userAPunch2 = await dao.insertPendingEvent(
        createTestItem(
            localId: 'ua-2', idempotencyKey: 'idemp-ua2', userId: 'user-A'),
      );

      expect(userAPunch1.sequenceNumber, equals(1));
      expect(userBPunch1.sequenceNumber, equals(1));
      expect(userAPunch2.sequenceNumber, equals(2));
    });

    test('retrieves pending events in strict chronological FIFO order',
        () async {
      final t1 = DateTime.utc(2026, 11, 16, 9, 0, 0);
      final t2 = DateTime.utc(2026, 11, 16, 13, 0, 0);
      final t3 = DateTime.utc(2026, 11, 16, 18, 0, 0);

      await dao.insertPendingEvent(
        createTestItem(
          localId: 'p1',
          idempotencyKey: 'idemp-1',
          eventType: AttendanceEventType.checkIn,
          deviceReportedAt: t1,
        ),
      );
      await dao.insertPendingEvent(
        createTestItem(
          localId: 'p2',
          idempotencyKey: 'idemp-2',
          eventType: AttendanceEventType.breakStart,
          deviceReportedAt: t2,
        ),
      );
      await dao.insertPendingEvent(
        createTestItem(
          localId: 'p3',
          idempotencyKey: 'idemp-3',
          eventType: AttendanceEventType.checkOut,
          deviceReportedAt: t3,
        ),
      );

      final fifoList = await dao.getPendingEventsFifo(
        tenantId: 'tenant-100',
        userId: 'user-100',
      );

      expect(fifoList.length, equals(3));
      expect(fifoList[0].localId, equals('p1'));
      expect(fifoList[0].sequenceNumber, equals(1));
      expect(fifoList[0].eventType, equals(AttendanceEventType.checkIn));

      expect(fifoList[1].localId, equals('p2'));
      expect(fifoList[1].sequenceNumber, equals(2));
      expect(fifoList[1].eventType, equals(AttendanceEventType.breakStart));

      expect(fifoList[2].localId, equals('p3'));
      expect(fifoList[2].sequenceNumber, equals(3));
      expect(fifoList[2].eventType, equals(AttendanceEventType.checkOut));
    });

    test('preserves full attendance evidence and fields immutably', () async {
      final item = createTestItem(
        localId: 'p-full',
        idempotencyKey: 'idemp-full',
        sessionId: 'sess-full-1',
        latitude: 12.971598,
        longitude: 77.594562,
        accuracyMeters: 8.2,
        wifiBssid: 'aa:bb:cc:dd:ee:ff',
        wifiSsid: 'Corporate_WiFi',
        wifiSignalStatus: 'AVAILABLE',
        monotonicBootTimeMs: 7891234,
        bootSessionId: 'boot-session-unique-99',
        isRebootDetected: true,
        appliedPolicyVersion: 2,
        appliedPolicyMode: 'COMBINED',
      );

      await dao.insertPendingEvent(item);
      final fetched = await dao.getEventById('p-full');

      expect(fetched, isNotNull);
      expect(fetched!.localId, equals('p-full'));
      expect(fetched.idempotencyKey, equals('idemp-full'));
      expect(fetched.sessionId, equals('sess-full-1'));
      expect(fetched.latitude, equals(12.971598));
      expect(fetched.longitude, equals(77.594562));
      expect(fetched.accuracyMeters, equals(8.2));
      expect(fetched.wifiBssid, equals('aa:bb:cc:dd:ee:ff'));
      expect(fetched.wifiSsid, equals('Corporate_WiFi'));
      expect(fetched.wifiSignalStatus, equals('AVAILABLE'));
      expect(fetched.monotonicBootTimeMs, equals(7891234));
      expect(fetched.bootSessionId, equals('boot-session-unique-99'));
      expect(fetched.isRebootDetected, isTrue);
      expect(fetched.appliedPolicyVersion, equals(2));
      expect(fetched.appliedPolicyMode, equals('COMBINED'));
      expect(fetched.sequenceNumber, equals(1));
      expect(fetched.syncStatus, equals(SyncStatus.pendingSync));
    });

    test(
        'enforces 500-event offline capacity threshold across pending, syncing, and quarantined records',
        () async {
      final db = dbHelper.database;
      final batch = db.batch();
      final nowStr = DateTime.now().toUtc().toIso8601String();

      // Populate queue with 200 PENDING_SYNC, 100 SYNCING, and 200 QUARANTINED_DEPENDENT_FAILURE (= 500 unresolved)
      for (var i = 1; i <= 200; i++) {
        batch.insert(LocalQueueDatabase.queueTable, {
          'local_id': 'pending-$i',
          'idempotency_key': 'idemp-pending-$i',
          'session_id': 'sess-1',
          'tenant_id': 'tenant-capacity',
          'employee_id': 'emp-capacity',
          'user_id': 'user-capacity',
          'event_type': 'CHECK_IN',
          'device_reported_at': nowStr,
          'timezone_offset_minutes': 0,
          'monotonic_boot_time_ms': 1000 + i,
          'boot_session_id': 'boot-cap',
          'is_reboot_detected': 0,
          'wifi_signal_status': 'AVAILABLE',
          'applied_policy_version': 1,
          'applied_policy_mode': 'MANUAL',
          'metadata_json': '{}',
          'sequence_number': i,
          'sync_status': 'PENDING_SYNC',
          'retry_count': 0,
          'created_at': nowStr,
          'updated_at': nowStr,
        });
      }
      for (var i = 201; i <= 300; i++) {
        batch.insert(LocalQueueDatabase.queueTable, {
          'local_id': 'syncing-$i',
          'idempotency_key': 'idemp-syncing-$i',
          'session_id': 'sess-1',
          'tenant_id': 'tenant-capacity',
          'employee_id': 'emp-capacity',
          'user_id': 'user-capacity',
          'event_type': 'CHECK_IN',
          'device_reported_at': nowStr,
          'timezone_offset_minutes': 0,
          'monotonic_boot_time_ms': 1000 + i,
          'boot_session_id': 'boot-cap',
          'is_reboot_detected': 0,
          'wifi_signal_status': 'AVAILABLE',
          'applied_policy_version': 1,
          'applied_policy_mode': 'MANUAL',
          'metadata_json': '{}',
          'sequence_number': i,
          'sync_status': 'SYNCING',
          'retry_count': 1,
          'created_at': nowStr,
          'updated_at': nowStr,
        });
      }
      for (var i = 301; i <= 500; i++) {
        batch.insert(LocalQueueDatabase.queueTable, {
          'local_id': 'quarantined-$i',
          'idempotency_key': 'idemp-quarantined-$i',
          'session_id': 'sess-1',
          'tenant_id': 'tenant-capacity',
          'employee_id': 'emp-capacity',
          'user_id': 'user-capacity',
          'event_type': 'CHECK_IN',
          'device_reported_at': nowStr,
          'timezone_offset_minutes': 0,
          'monotonic_boot_time_ms': 1000 + i,
          'boot_session_id': 'boot-cap',
          'is_reboot_detected': 0,
          'wifi_signal_status': 'AVAILABLE',
          'applied_policy_version': 1,
          'applied_policy_mode': 'MANUAL',
          'metadata_json': '{}',
          'sequence_number': i,
          'sync_status': 'QUARANTINED_DEPENDENT_FAILURE',
          'retry_count': 0,
          'created_at': nowStr,
          'updated_at': nowStr,
        });
      }
      await batch.commit(noResult: true);

      final unresolvedCount = await dao.getUnresolvedCount(
        tenantId: 'tenant-capacity',
        userId: 'user-capacity',
      );
      expect(unresolvedCount, equals(500));

      // Attempting to insert 501st item must throw QueueCapacityExceededException
      final overflowItem = createTestItem(
        localId: 'overflow-501',
        idempotencyKey: 'idemp-overflow-501',
        tenantId: 'tenant-capacity',
        userId: 'user-capacity',
      );

      await expectLater(
        dao.insertPendingEvent(overflowItem),
        throwsA(
          isA<QueueCapacityExceededException>().having(
            (e) => e.message,
            'message',
            contains('Existing records are preserved'),
          ),
        ),
      );

      // Verify NO unresolved records were deleted to satisfy capacity
      expect(
        await dao.getUnresolvedCount(
          tenantId: 'tenant-capacity',
          userId: 'user-capacity',
        ),
        equals(500),
      );
    });

    test('synced and rejected punches do not count towards 500 capacity',
        () async {
      final db = dbHelper.database;
      final batch = db.batch();
      final nowStr = DateTime.now().toUtc().toIso8601String();

      // Insert 300 SYNCED, 200 REJECTED_PERMANENT, and 499 PENDING_SYNC
      for (var i = 1; i <= 300; i++) {
        batch.insert(LocalQueueDatabase.queueTable, {
          'local_id': 'synced-$i',
          'idempotency_key': 'synced-idemp-$i',
          'session_id': 'sess-old',
          'tenant_id': 'tenant-test',
          'employee_id': 'emp-test',
          'user_id': 'user-test',
          'event_type': 'CHECK_IN',
          'device_reported_at': nowStr,
          'timezone_offset_minutes': 0,
          'monotonic_boot_time_ms': 1000 + i,
          'boot_session_id': 'boot-test',
          'sequence_number': i,
          'sync_status': 'SYNCED',
          'created_at': nowStr,
          'updated_at': nowStr,
        });
      }
      for (var i = 301; i <= 500; i++) {
        batch.insert(LocalQueueDatabase.queueTable, {
          'local_id': 'rejected-$i',
          'idempotency_key': 'rejected-idemp-$i',
          'session_id': 'sess-old',
          'tenant_id': 'tenant-test',
          'employee_id': 'emp-test',
          'user_id': 'user-test',
          'event_type': 'CHECK_IN',
          'device_reported_at': nowStr,
          'timezone_offset_minutes': 0,
          'monotonic_boot_time_ms': 1000 + i,
          'boot_session_id': 'boot-test',
          'sequence_number': i,
          'sync_status': 'REJECTED_PERMANENT',
          'created_at': nowStr,
          'updated_at': nowStr,
        });
      }
      // Insert 499 pending
      for (var i = 501; i <= 999; i++) {
        batch.insert(LocalQueueDatabase.queueTable, {
          'local_id': 'pending-$i',
          'idempotency_key': 'pending-idemp-$i',
          'session_id': 'sess-active',
          'tenant_id': 'tenant-test',
          'employee_id': 'emp-test',
          'user_id': 'user-test',
          'event_type': 'CHECK_IN',
          'device_reported_at': nowStr,
          'timezone_offset_minutes': 0,
          'monotonic_boot_time_ms': 1000 + i,
          'boot_session_id': 'boot-test',
          'sequence_number': i,
          'sync_status': 'PENDING_SYNC',
          'created_at': nowStr,
          'updated_at': nowStr,
        });
      }
      await batch.commit(noResult: true);

      expect(
        await dao.getUnresolvedCount(
            tenantId: 'tenant-test', userId: 'user-test'),
        equals(499),
      );

      // Inserting 500th unresolved item must succeed
      final punch500 = await dao.insertPendingEvent(
        createTestItem(
          localId: 'punch-500th',
          idempotencyKey: 'idemp-500th',
          tenantId: 'tenant-test',
          userId: 'user-test',
        ),
      );
      expect(punch500.sequenceNumber, equals(1000));
      expect(
        await dao.getUnresolvedCount(
            tenantId: 'tenant-test', userId: 'user-test'),
        equals(500),
      );

      // 501st item fails
      await expectLater(
        dao.insertPendingEvent(
          createTestItem(
            localId: 'punch-501st',
            idempotencyKey: 'idemp-501st',
            tenantId: 'tenant-test',
            userId: 'user-test',
          ),
        ),
        throwsA(isA<QueueCapacityExceededException>()),
      );
    });

    test('updateSyncStatus transitions state and records retry count',
        () async {
      await dao.insertPendingEvent(
        createTestItem(localId: 'trans-1', idempotencyKey: 'idemp-t1'),
      );

      // Transition to SYNCING: increments retry_count and sets last_attempted_at
      await dao.updateSyncStatus(
        localId: 'trans-1',
        status: SyncStatus.syncing,
      );

      var item = await dao.getEventById('trans-1');
      expect(item!.syncStatus, equals(SyncStatus.syncing));
      expect(item.retryCount, equals(1));
      expect(item.lastAttemptedAt, isNotNull);

      // Transition to SYNCED: records server_event_id
      await dao.updateSyncStatus(
        localId: 'trans-1',
        status: SyncStatus.synced,
        serverEventId: 'srv-event-uuid-1234',
      );

      item = await dao.getEventById('trans-1');
      expect(item!.syncStatus, equals(SyncStatus.synced));
      expect(item.serverEventId, equals('srv-event-uuid-1234'));
    });

    test('markPermanentlyRejected transitions to REJECTED_PERMANENT with error',
        () async {
      await dao.insertPendingEvent(
        createTestItem(localId: 'rej-1', idempotencyKey: 'idemp-r1'),
      );

      await dao.markPermanentlyRejected(
        localId: 'rej-1',
        errorMessage: 'GPS spoofing detected by server policy',
        statusCode: 422,
      );

      final item = await dao.getEventById('rej-1');
      expect(item!.syncStatus, equals(SyncStatus.rejectedPermanent));
      expect(item.lastErrorMessage,
          equals('GPS spoofing detected by server policy'));
      expect(item.lastErrorStatusCode, equals(422));
    });

    test(
        'session-aware quarantine: rejected CHECK_IN quarantines only its session, future shift remains eligible',
        () async {
      // 1. Employee records Monday Shift (Session 1):
      // - p1: CHECK_IN (fails permanently)
      // - p2: BREAK_START (dependent on p1)
      // - p3: BREAK_END (dependent on p1)
      // - p4: CHECK_OUT (closes session 1)
      await dao.insertPendingEvent(
        createTestItem(
          localId: 'p1',
          idempotencyKey: 'idemp-p1',
          eventType: AttendanceEventType.checkIn,
          deviceReportedAt: DateTime.utc(2026, 11, 16, 9, 0, 0),
        ),
      );
      await dao.insertPendingEvent(
        createTestItem(
          localId: 'p2',
          idempotencyKey: 'idemp-p2',
          eventType: AttendanceEventType.breakStart,
          deviceReportedAt: DateTime.utc(2026, 11, 16, 13, 0, 0),
        ),
      );
      await dao.insertPendingEvent(
        createTestItem(
          localId: 'p3',
          idempotencyKey: 'idemp-p3',
          eventType: AttendanceEventType.breakEnd,
          deviceReportedAt: DateTime.utc(2026, 11, 16, 13, 30, 0),
        ),
      );
      await dao.insertPendingEvent(
        createTestItem(
          localId: 'p4',
          idempotencyKey: 'idemp-p4',
          eventType: AttendanceEventType.checkOut,
          deviceReportedAt: DateTime.utc(2026, 11, 16, 18, 0, 0),
        ),
      );

      // 2. Employee records Tuesday Shift (Session 2 - Future Shift):
      // - p5: CHECK_IN
      // - p6: CHECK_OUT
      await dao.insertPendingEvent(
        createTestItem(
          localId: 'p5',
          idempotencyKey: 'idemp-p5',
          eventType: AttendanceEventType.checkIn,
          deviceReportedAt: DateTime.utc(2026, 11, 17, 9, 0, 0),
        ),
      );
      await dao.insertPendingEvent(
        createTestItem(
          localId: 'p6',
          idempotencyKey: 'idemp-p6',
          eventType: AttendanceEventType.checkOut,
          deviceReportedAt: DateTime.utc(2026, 11, 17, 18, 0, 0),
        ),
      );

      // Verify session grouping
      final itemP1 = await dao.getEventById('p1');
      final itemP2 = await dao.getEventById('p2');
      final itemP4 = await dao.getEventById('p4');
      final itemP5 = await dao.getEventById('p5');
      final itemP6 = await dao.getEventById('p6');

      expect(itemP1!.sessionId, equals('sess_p1'));
      expect(itemP2!.sessionId, equals('sess_p1'));
      expect(itemP4!.sessionId, equals('sess_p1'));
      expect(itemP5!.sessionId, equals('sess_p5'));
      expect(itemP6!.sessionId, equals('sess_p5'));

      // 3. Backend rejects Monday Check-In (p1) permanently
      await dao.markPermanentlyRejected(
        localId: 'p1',
        errorMessage: 'Workplace assignment inactive during shift 1',
        statusCode: 403,
      );

      // 4. Cascade quarantine for Monday Shift
      const conflictBundleId = 'bundle-monday-shift-conflict';
      final quarantinedCount = await dao.quarantineDependentEvents(
        tenantId: 'tenant-100',
        userId: 'user-100',
        conflictBundleId: conflictBundleId,
        fromLocalId: 'p1',
      );

      // Quarantined exactly 3 items from Monday Shift (p2, p3, p4)
      expect(quarantinedCount, equals(3));

      // 5. Verify Session 1 events are quarantined
      final p1 = await dao.getEventById('p1');
      final p2 = await dao.getEventById('p2');
      final p3 = await dao.getEventById('p3');
      final p4 = await dao.getEventById('p4');

      expect(p1!.syncStatus, equals(SyncStatus.rejectedPermanent));
      expect(p2!.syncStatus, equals(SyncStatus.quarantinedDependentFailure));
      expect(p2.conflictBundleId, equals(conflictBundleId));
      expect(p3!.syncStatus, equals(SyncStatus.quarantinedDependentFailure));
      expect(p3.conflictBundleId, equals(conflictBundleId));
      expect(p4!.syncStatus, equals(SyncStatus.quarantinedDependentFailure));
      expect(p4.conflictBundleId, equals(conflictBundleId));

      // 6. VERIFY FUTURE SHIFT (Session 2: p5, p6) REMAINS PENDING AND SYNCHRONIZABLE!
      final p5 = await dao.getEventById('p5');
      final p6 = await dao.getEventById('p6');

      expect(p5!.syncStatus, equals(SyncStatus.pendingSync));
      expect(p5.conflictBundleId, isNull);
      expect(p6!.syncStatus, equals(SyncStatus.pendingSync));
      expect(p6.conflictBundleId, isNull);

      // FIFO pending retrieval returns ONLY the eligible future shift!
      final eligiblePending = await dao.getPendingEventsFifo(
        tenantId: 'tenant-100',
        userId: 'user-100',
      );
      expect(eligiblePending.length, equals(2));
      expect(eligiblePending[0].localId, equals('p5'));
      expect(eligiblePending[1].localId, equals('p6'));
    });

    test('deleteSyncedEventsOlderThan purges only old synced records',
        () async {
      final db = dbHelper.database;
      final oldTime = DateTime.now()
          .toUtc()
          .subtract(const Duration(days: 40))
          .toIso8601String();
      final recentTime = DateTime.now()
          .toUtc()
          .subtract(const Duration(days: 2))
          .toIso8601String();

      // Old SYNCED
      await db.insert(LocalQueueDatabase.queueTable, {
        'local_id': 'synced-old',
        'idempotency_key': 'idemp-synced-old',
        'session_id': 'sess-1',
        'tenant_id': 'tenant-100',
        'employee_id': 'emp-100',
        'user_id': 'user-100',
        'event_type': 'CHECK_IN',
        'device_reported_at': oldTime,
        'timezone_offset_minutes': 0,
        'monotonic_boot_time_ms': 1000,
        'boot_session_id': 'boot-1',
        'sequence_number': 1,
        'sync_status': 'SYNCED',
        'created_at': oldTime,
        'updated_at': oldTime,
      });

      // Recent SYNCED
      await db.insert(LocalQueueDatabase.queueTable, {
        'local_id': 'synced-recent',
        'idempotency_key': 'idemp-synced-recent',
        'session_id': 'sess-2',
        'tenant_id': 'tenant-100',
        'employee_id': 'emp-100',
        'user_id': 'user-100',
        'event_type': 'CHECK_IN',
        'device_reported_at': recentTime,
        'timezone_offset_minutes': 0,
        'monotonic_boot_time_ms': 2000,
        'boot_session_id': 'boot-1',
        'sequence_number': 2,
        'sync_status': 'SYNCED',
        'created_at': recentTime,
        'updated_at': recentTime,
      });

      // Old PENDING_SYNC (must NOT be deleted)
      await db.insert(LocalQueueDatabase.queueTable, {
        'local_id': 'pending-old',
        'idempotency_key': 'idemp-pending-old',
        'session_id': 'sess-3',
        'tenant_id': 'tenant-100',
        'employee_id': 'emp-100',
        'user_id': 'user-100',
        'event_type': 'CHECK_IN',
        'device_reported_at': oldTime,
        'timezone_offset_minutes': 0,
        'monotonic_boot_time_ms': 3000,
        'boot_session_id': 'boot-1',
        'sequence_number': 3,
        'sync_status': 'PENDING_SYNC',
        'created_at': oldTime,
        'updated_at': oldTime,
      });

      // Old QUARANTINED (must NOT be deleted)
      await db.insert(LocalQueueDatabase.queueTable, {
        'local_id': 'quarantined-old',
        'idempotency_key': 'idemp-quarantined-old',
        'session_id': 'sess-4',
        'tenant_id': 'tenant-100',
        'employee_id': 'emp-100',
        'user_id': 'user-100',
        'event_type': 'CHECK_IN',
        'device_reported_at': oldTime,
        'timezone_offset_minutes': 0,
        'monotonic_boot_time_ms': 4000,
        'boot_session_id': 'boot-1',
        'sequence_number': 4,
        'sync_status': 'QUARANTINED_DEPENDENT_FAILURE',
        'created_at': oldTime,
        'updated_at': oldTime,
      });

      // Purge older than 30 days
      final deleted = await dao.deleteSyncedEventsOlderThan(
        age: const Duration(days: 30),
      );

      expect(deleted, equals(1));
      expect(await dao.getEventById('synced-old'), isNull);
      expect(await dao.getEventById('synced-recent'), isNotNull);
      expect(await dao.getEventById('pending-old'), isNotNull);
      expect(await dao.getEventById('quarantined-old'), isNotNull);
    });

    test('resetZombieSyncingItems resets stranded syncing punches to pending',
        () async {
      final db = dbHelper.database;
      final oldAttempt = DateTime.now()
          .toUtc()
          .subtract(const Duration(minutes: 5))
          .toIso8601String();
      final freshAttempt = DateTime.now()
          .toUtc()
          .subtract(const Duration(seconds: 10))
          .toIso8601String();

      // Zombie syncing item
      await db.insert(LocalQueueDatabase.queueTable, {
        'local_id': 'zombie-1',
        'idempotency_key': 'idemp-z1',
        'session_id': 'sess-z',
        'tenant_id': 'tenant-100',
        'employee_id': 'emp-100',
        'user_id': 'user-100',
        'event_type': 'CHECK_IN',
        'device_reported_at': oldAttempt,
        'timezone_offset_minutes': 0,
        'monotonic_boot_time_ms': 1000,
        'boot_session_id': 'boot-1',
        'sequence_number': 1,
        'sync_status': 'SYNCING',
        'last_attempted_at': oldAttempt,
        'created_at': oldAttempt,
        'updated_at': oldAttempt,
      });

      // Fresh actively syncing item
      await db.insert(LocalQueueDatabase.queueTable, {
        'local_id': 'active-syncing',
        'idempotency_key': 'idemp-act',
        'session_id': 'sess-act',
        'tenant_id': 'tenant-100',
        'employee_id': 'emp-100',
        'user_id': 'user-100',
        'event_type': 'CHECK_OUT',
        'device_reported_at': freshAttempt,
        'timezone_offset_minutes': 0,
        'monotonic_boot_time_ms': 2000,
        'boot_session_id': 'boot-1',
        'sequence_number': 2,
        'sync_status': 'SYNCING',
        'last_attempted_at': freshAttempt,
        'created_at': freshAttempt,
        'updated_at': freshAttempt,
      });

      final resetCount = await dao.resetZombieSyncingItems(
        timeout: const Duration(seconds: 120),
      );

      expect(resetCount, equals(1));
      final zombie = await dao.getEventById('zombie-1');
      final active = await dao.getEventById('active-syncing');

      expect(zombie!.syncStatus, equals(SyncStatus.pendingSync));
      expect(active!.syncStatus, equals(SyncStatus.syncing));
    });

    test(
        'getConflictBundles groups rejected and quarantined session events with stable bundle ID',
        () async {
      await dao.insertPendingEvent(
        createTestItem(
          localId: 'rej-1',
          idempotencyKey: 'idemp-r1',
          sessionId: 'sess-conflict-a',
          eventType: AttendanceEventType.checkIn,
        ),
      );
      await dao.markPermanentlyRejected(
        localId: 'rej-1',
        errorMessage: 'Maximum offline drift exceeded',
        statusCode: 422,
      );

      await dao.insertPendingEvent(
        createTestItem(
          localId: 'quar-1',
          idempotencyKey: 'idemp-q1',
          sessionId: 'sess-conflict-a',
          eventType: AttendanceEventType.checkOut,
        ),
      );
      await dao.updateSyncStatus(
        localId: 'quar-1',
        status: SyncStatus.quarantinedDependentFailure,
        errorMessage: 'Quarantined due to earlier rejection',
      );

      // Extract bundles
      final bundles = await dao.getConflictBundles(
        tenantId: 'tenant-100',
        userId: 'user-100',
      );

      expect(bundles.length, equals(1));
      final bundle = bundles.first;
      expect(bundle.sessionId, equals('sess-conflict-a'));
      expect(bundle.primaryRejectedEvent.localId, equals('rej-1'));
      expect(bundle.dependentEvents.length, equals(1));
      expect(bundle.dependentEvents.first.localId, equals('quar-1'));
      expect(bundle.bundleId, isNotEmpty);

      // Verify stable bundle ID on subsequent call
      final bundles2 = await dao.getConflictBundles(
        tenantId: 'tenant-100',
        userId: 'user-100',
      );
      expect(bundles2.first.bundleId, equals(bundle.bundleId));
    });

    test(
        'saveConflictBundleSubmission stores metadata and resolves events on APPROVE',
        () async {
      await dao.insertPendingEvent(
        createTestItem(
          localId: 'rej-app',
          idempotencyKey: 'idemp-app-1',
          sessionId: 'sess-app',
        ),
      );
      await dao.markPermanentlyRejected(
        localId: 'rej-app',
        errorMessage: 'Test rejection',
      );

      final bundles = await dao.getConflictBundles(
        tenantId: 'tenant-100',
        userId: 'user-100',
      );
      expect(bundles.length, equals(1));
      final bundleId = bundles.first.bundleId;

      // Save submission as PENDING_REVIEW
      await dao.saveConflictBundleSubmission(
        bundleId: bundleId,
        incidentId: 'inc-pending-1',
        status: 'PENDING_REVIEW',
        employeeNotes: 'Please review',
      );

      final metadata = await dao.getConflictBundleSubmission(bundleId);
      expect(metadata, isNotNull);
      expect(metadata!['incident_id'], equals('inc-pending-1'));
      expect(metadata['status'], equals('PENDING_REVIEW'));

      // Now save update as APPROVED
      await dao.saveConflictBundleSubmission(
        bundleId: bundleId,
        incidentId: 'inc-pending-1',
        status: 'APPROVED',
        decision: 'APPROVE',
        decisionReason: 'Verified on-site',
      );

      final updatedItem = await dao.getEventById('rej-app');
      expect(updatedItem!.syncStatus, equals(SyncStatus.synced));
    });
  });
}
