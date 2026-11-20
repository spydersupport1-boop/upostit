import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/features/attendance/data/datasources/attendance_remote_data_source.dart';
import 'package:mobile/features/attendance/data/models/attendance_event_model.dart';
import 'package:mobile/features/attendance/data/models/punch_request_model.dart';
import 'package:mobile/features/attendance/data/models/punch_response_model.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_event.dart';
import 'package:mobile/features/sync/data/datasources/database_key_provider.dart';
import 'package:mobile/features/sync/data/datasources/local_queue_database.dart';
import 'package:mobile/features/sync/data/datasources/sqflite_local_queue_dao.dart';
import 'package:mobile/features/sync/data/services/sync_worker_impl.dart';
import 'package:mobile/features/sync/domain/entities/local_queue_item.dart';
import 'package:mobile/features/sync/domain/entities/sync_status.dart';
import 'package:mocktail/mocktail.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

class MockAttendanceRemoteDataSource extends Mock
    implements AttendanceRemoteDataSource {}

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
  late LocalQueueDatabase db;
  late SqfliteLocalQueueDao dao;
  late MockAttendanceRemoteDataSource mockRemoteDataSource;
  late SyncWorkerImpl syncWorker;

  const tTenantAlpha = 'tenant-alpha';
  const tUserA = 'user-a';
  const tEmpA = 'emp-a';

  const tTenantBeta = 'tenant-beta';
  const tUserB = 'user-b';
  const tEmpB = 'emp-b';

  LocalQueueItem buildItem({
    required String localId,
    required String idempotencyKey,
    required String tenantId,
    required String userId,
    required String employeeId,
    required AttendanceEventType eventType,
    int sequenceNumber = 0,
    String sessionId = 'session-1',
  }) {
    return LocalQueueItem(
      localId: localId,
      idempotencyKey: idempotencyKey,
      sessionId: sessionId,
      tenantId: tenantId,
      employeeId: employeeId,
      userId: userId,
      eventType: eventType,
      deviceReportedAt: DateTime.utc(2026, 11, 5, 8, sequenceNumber),
      timezoneOffsetMinutes: 0,
      monotonicBootTimeMs: 1000000 + sequenceNumber * 1000,
      bootSessionId: 'boot-shared-device-1',
      appliedPolicyVersion: 1,
      appliedPolicyMode: 'MANUAL',
      sequenceNumber: sequenceNumber,
      syncStatus: SyncStatus.pendingSync,
      createdAt: DateTime.utc(2026, 11, 5, 8, sequenceNumber),
      updatedAt: DateTime.utc(2026, 11, 5, 8, sequenceNumber),
    );
  }

  setUpAll(() {
    sqfliteFfiInit();
    registerFallbackValue(
      const PunchRequestModel(
        eventType: AttendanceEventType.checkIn,
        idempotencyKey: 'fallback-key',
      ),
    );
  });

  setUp(() async {
    db = LocalQueueDatabase(
      keyProvider: TestKeyProvider(),
      factory: databaseFactoryFfi,
      customPath: inMemoryDatabasePath,
    );
    await db.open();
    dao = SqfliteLocalQueueDao(database: db);
    mockRemoteDataSource = MockAttendanceRemoteDataSource();
    syncWorker = SyncWorkerImpl(
      localQueueDao: dao,
      remoteDataSource: mockRemoteDataSource,
    );
  });

  tearDown(() async {
    await db.close();
  });

  group('Phase 6.5.D — Account Switching & Tenant Isolation Simulation', () {
    test(
        'Scenario 1: User A queues punches, logs out -> User B logs in on same device -> '
        'User B sees zero records -> User B logs out -> User A logs back in -> '
        'User A records are fully intact and sync to Tenant Alpha only',
        () async {
      // ---------------------------------------------------------
      // Step 1: User A logs in (Tenant Alpha) and creates 4 offline punches
      // ---------------------------------------------------------
      final itemA1 = await dao.insertPendingEvent(
        buildItem(
          localId: 'loc-a1',
          idempotencyKey: 'idem-a1',
          tenantId: tTenantAlpha,
          userId: tUserA,
          employeeId: tEmpA,
          eventType: AttendanceEventType.checkIn,
        ),
      );
      expect(itemA1.sequenceNumber, equals(1));

      final itemA2 = await dao.insertPendingEvent(
        buildItem(
          localId: 'loc-a2',
          idempotencyKey: 'idem-a2',
          tenantId: tTenantAlpha,
          userId: tUserA,
          employeeId: tEmpA,
          eventType: AttendanceEventType.breakStart,
        ),
      );
      expect(itemA2.sequenceNumber, equals(2));

      final itemA3 = await dao.insertPendingEvent(
        buildItem(
          localId: 'loc-a3',
          idempotencyKey: 'idem-a3',
          tenantId: tTenantAlpha,
          userId: tUserA,
          employeeId: tEmpA,
          eventType: AttendanceEventType.breakEnd,
        ),
      );
      expect(itemA3.sequenceNumber, equals(3));

      final itemA4 = await dao.insertPendingEvent(
        buildItem(
          localId: 'loc-a4',
          idempotencyKey: 'idem-a4',
          tenantId: tTenantAlpha,
          userId: tUserA,
          employeeId: tEmpA,
          eventType: AttendanceEventType.checkOut,
        ),
      );
      expect(itemA4.sequenceNumber, equals(4));

      // Verify User A has 4 pending records
      final summaryA1 = await dao.getQueueSummary(
        tenantId: tTenantAlpha,
        userId: tUserA,
      );
      expect(summaryA1.pendingCount, equals(4));
      expect(summaryA1.unresolvedCount, equals(4));

      // ---------------------------------------------------------
      // Step 2: User A logs out. User B (Tenant Beta) logs in on same phone.
      // ---------------------------------------------------------
      final summaryB = await dao.getQueueSummary(
        tenantId: tTenantBeta,
        userId: tUserB,
      );
      expect(summaryB.pendingCount, equals(0));
      expect(summaryB.syncingCount, equals(0));
      expect(summaryB.quarantinedCount, equals(0));
      expect(summaryB.syncedCount, equals(0));
      expect(summaryB.totalCount, equals(0));
      expect(summaryB.unresolvedCount, equals(0));

      final itemsB = await dao.getPendingEventsFifo(
        tenantId: tTenantBeta,
        userId: tUserB,
      );
      expect(itemsB, isEmpty);

      // Attempting to run sync for User B syncs 0 records
      final resultB = await syncWorker.synchronizeQueue(
        tenantId: tTenantBeta,
        userId: tUserB,
      );
      expect(resultB.syncedCount, equals(0));
      expect(resultB.quarantinedCount, equals(0));
      expect(resultB.retryableFailureCount, equals(0));
      expect(resultB.permanentlyRejectedCount, equals(0));
      expect(resultB.hasErrors, isFalse);

      // User B inserts a punch: sequence number must start fresh at 1 for (tenant-beta, user-b)
      final itemB1 = await dao.insertPendingEvent(
        buildItem(
          localId: 'loc-b1',
          idempotencyKey: 'idem-b1',
          tenantId: tTenantBeta,
          userId: tUserB,
          employeeId: tEmpB,
          eventType: AttendanceEventType.checkIn,
        ),
      );
      expect(itemB1.sequenceNumber, equals(1));

      // ---------------------------------------------------------
      // Step 3: User B logs out. User A logs back in.
      // ---------------------------------------------------------
      final summaryA2 = await dao.getQueueSummary(
        tenantId: tTenantAlpha,
        userId: tUserA,
      );
      expect(summaryA2.pendingCount, equals(4));
      expect(summaryA2.unresolvedCount, equals(4));

      final pendingA = await dao.getPendingEventsFifo(
        tenantId: tTenantAlpha,
        userId: tUserA,
      );
      expect(pendingA.length, equals(4));
      expect(pendingA[0].idempotencyKey, equals('idem-a1'));
      expect(pendingA[1].idempotencyKey, equals('idem-a2'));
      expect(pendingA[2].idempotencyKey, equals('idem-a3'));
      expect(pendingA[3].idempotencyKey, equals('idem-a4'));
      expect(pendingA[0].sequenceNumber, equals(1));
      expect(pendingA[1].sequenceNumber, equals(2));
      expect(pendingA[2].sequenceNumber, equals(3));
      expect(pendingA[3].sequenceNumber, equals(4));

      // ---------------------------------------------------------
      // Step 4: Network reconnects. SyncWorker runs for User A.
      // ---------------------------------------------------------
      final List<String> receivedIdempotencyKeys = [];

      when(() => mockRemoteDataSource.recordPunch(any()))
          .thenAnswer((invocation) async {
        final req = invocation.positionalArguments[0] as PunchRequestModel;
        receivedIdempotencyKeys.add(req.idempotencyKey);
        final now = DateTime.utc(2026, 11, 5, 9);
        return PunchResponseModel(
          event: AttendanceEventModel(
            id: 'server-${req.idempotencyKey}',
            tenantId: tTenantAlpha,
            employeeId: tEmpA,
            eventType: req.eventType,
            eventCategory: 'STANDARD',
            effectiveAt: req.deviceReportedAt ?? DateTime.utc(2026, 11, 5, 8),
            deviceReportedAt:
                req.deviceReportedAt ?? DateTime.utc(2026, 11, 5, 8),
            serverReceivedAt: now,
            source: 'MOBILE',
            timestampVerificationStatus: 'SERVER_AUTHORITATIVE',
            reviewStatus: 'NOT_REQUIRED',
            idempotencyKey: req.idempotencyKey,
            createdAt: now,
          ),
          isIdempotentReplay: false,
        );
      });

      final resultA = await syncWorker.synchronizeQueue(
        tenantId: tTenantAlpha,
        userId: tUserA,
      );

      expect(resultA.syncedCount, equals(4));
      expect(resultA.hasErrors, isFalse);
      expect(receivedIdempotencyKeys,
          equals(['idem-a1', 'idem-a2', 'idem-a3', 'idem-a4']));

      // All User A items are SYNCED
      final summaryA3 = await dao.getQueueSummary(
        tenantId: tTenantAlpha,
        userId: tUserA,
      );
      expect(summaryA3.pendingCount, equals(0));
      expect(summaryA3.syncedCount, equals(4));

      // User B's record (loc-b1) remains completely untouched and pending in tenant-beta
      final summaryBFinal = await dao.getQueueSummary(
        tenantId: tTenantBeta,
        userId: tUserB,
      );
      expect(summaryBFinal.pendingCount, equals(1));
      expect(summaryBFinal.syncedCount, equals(0));
    });

    test('Scenario 2: Cross-tenant query isolation and SQL injection immunity',
        () async {
      // Seed User A in Tenant Alpha
      await dao.insertPendingEvent(
        buildItem(
          localId: 'loc-a1',
          idempotencyKey: 'idem-a1',
          tenantId: tTenantAlpha,
          userId: tUserA,
          employeeId: tEmpA,
          eventType: AttendanceEventType.checkIn,
        ),
      );

      // Attempt cross-tenant lookup with Tenant Beta and User A
      final crossItems1 = await dao.getPendingEventsFifo(
        tenantId: tTenantBeta,
        userId: tUserA,
      );
      expect(crossItems1, isEmpty);

      // Attempt cross-user lookup with Tenant Alpha and User B
      final crossItems2 = await dao.getPendingEventsFifo(
        tenantId: tTenantAlpha,
        userId: tUserB,
      );
      expect(crossItems2, isEmpty);

      // Attempt SQL injection via tenantId parameter
      final injectedItems = await dao.getPendingEventsFifo(
        tenantId: "tenant-alpha' OR '1'='1",
        userId: tUserA,
      );
      expect(injectedItems, isEmpty);
    });
  });
}
