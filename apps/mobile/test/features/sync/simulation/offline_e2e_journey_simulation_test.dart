import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/features/attendance/data/datasources/attendance_remote_data_source.dart';
import 'package:mobile/features/attendance/data/models/attendance_event_model.dart';
import 'package:mobile/features/attendance/data/models/punch_request_model.dart';
import 'package:mobile/features/attendance/data/models/punch_response_model.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_event.dart';
import 'package:mobile/features/sync/data/services/sync_worker_impl.dart';
import 'package:mobile/features/sync/domain/entities/local_queue_item.dart';
import 'package:mobile/features/sync/domain/entities/sync_queue_summary.dart';
import 'package:mobile/features/sync/domain/entities/sync_status.dart';
import 'package:mobile/features/sync/domain/repositories/local_queue_dao.dart';
import 'package:mobile/features/sync/domain/repositories/network_connectivity_service.dart';
import 'package:mocktail/mocktail.dart';

class MockLocalQueueDao extends Mock implements LocalQueueDao {}

class MockAttendanceRemoteDataSource extends Mock
    implements AttendanceRemoteDataSource {}

class MockNetworkConnectivityService extends Mock
    implements NetworkConnectivityService {}

void main() {
  late MockLocalQueueDao mockDao;
  late MockAttendanceRemoteDataSource mockRemoteDataSource;
  late MockNetworkConnectivityService mockConnectivityService;
  late StreamController<bool> connectivityController;

  const tTenantId = 'tenant-corp-1';
  const tUserId = 'user-emp-42';
  const tEmployeeId = 'EMP-42';

  final Map<String, LocalQueueItem> inMemoryQueue = {};
  final List<PunchRequestModel> dispatchedRequests = [];

  LocalQueueItem createQueueItem({
    required String localId,
    required String idempotencyKey,
    required AttendanceEventType eventType,
    required int sequenceNumber,
    required DateTime deviceReportedAt,
    String? sessionId,
  }) {
    return LocalQueueItem(
      localId: localId,
      idempotencyKey: idempotencyKey,
      sessionId: sessionId ?? 'session-2026-11-04',
      tenantId: tTenantId,
      employeeId: tEmployeeId,
      userId: tUserId,
      eventType: eventType,
      deviceReportedAt: deviceReportedAt,
      timezoneOffsetMinutes: 0,
      monotonicBootTimeMs: 1000000 + sequenceNumber * 60000,
      bootSessionId: 'boot-session-alpha',
      appliedPolicyVersion: 1,
      appliedPolicyMode: 'MANUAL',
      sequenceNumber: sequenceNumber,
      syncStatus: SyncStatus.pendingSync,
      createdAt: deviceReportedAt,
      updatedAt: deviceReportedAt,
    );
  }

  PunchResponseModel createServerPunchResponse(PunchRequestModel request) {
    return PunchResponseModel(
      event: AttendanceEventModel(
        id: 'srv-${request.eventType.toBackendString().toLowerCase()}-${request.idempotencyKey.substring(0, 8)}',
        tenantId: tTenantId,
        employeeId: tEmployeeId,
        eventType: request.eventType,
        eventCategory: 'STANDARD',
        serverReceivedAt: DateTime.now().toUtc(),
        effectiveAt: request.deviceReportedAt ?? DateTime.now().toUtc(),
        source: 'MOBILE_OFFLINE_SYNC',
        timestampVerificationStatus: 'SERVER_AUTHORITATIVE',
        reviewStatus: 'NOT_REQUIRED',
        idempotencyKey: request.idempotencyKey,
        createdAt: DateTime.now().toUtc(),
      ),
      isIdempotentReplay: false,
    );
  }

  setUpAll(() {
    registerFallbackValue(
      const PunchRequestModel(
        eventType: AttendanceEventType.checkIn,
        idempotencyKey: 'fallback-idemp',
      ),
    );
    registerFallbackValue(SyncStatus.pendingSync);
    registerFallbackValue(const Duration(seconds: 120));
  });

  setUp(() {
    mockDao = MockLocalQueueDao();
    mockRemoteDataSource = MockAttendanceRemoteDataSource();
    mockConnectivityService = MockNetworkConnectivityService();
    connectivityController = StreamController<bool>.broadcast();
    inMemoryQueue.clear();
    dispatchedRequests.clear();

    when(() => mockConnectivityService.onConnectivityRestored)
        .thenAnswer((_) => connectivityController.stream);

    when(() => mockDao.resetZombieSyncingItems(
          timeout: any(named: 'timeout'),
        )).thenAnswer((_) async => 0);

    when(() => mockDao.getPendingEventsFifo(
          tenantId: any(named: 'tenantId'),
          userId: any(named: 'userId'),
          limit: any(named: 'limit'),
        )).thenAnswer((inv) async {
      final tId = inv.namedArguments[#tenantId] as String;
      final uId = inv.namedArguments[#userId] as String;
      final list = inMemoryQueue.values
          .where((item) =>
              item.syncStatus == SyncStatus.pendingSync &&
              item.tenantId == tId &&
              item.userId == uId)
          .toList();
      list.sort((a, b) => a.sequenceNumber.compareTo(b.sequenceNumber));
      return list;
    });

    when(() => mockDao.getEventById(any())).thenAnswer((inv) async {
      final id = inv.positionalArguments[0] as String;
      return inMemoryQueue[id];
    });

    when(() => mockDao.updateSyncStatus(
          localId: any(named: 'localId'),
          status: any(named: 'status'),
          serverEventId: any(named: 'serverEventId'),
          errorMessage: any(named: 'errorMessage'),
          statusCode: any(named: 'statusCode'),
        )).thenAnswer((inv) async {
      final id = inv.namedArguments[#localId] as String;
      final status = inv.namedArguments[#status] as SyncStatus;
      final srvId = inv.namedArguments[#serverEventId] as String?;
      final errMsg = inv.namedArguments[#errorMessage] as String?;
      final code = inv.namedArguments[#statusCode] as int?;
      final existing = inMemoryQueue[id];
      if (existing != null) {
        inMemoryQueue[id] = existing.copyWith(
          syncStatus: status,
          serverEventId: srvId,
          lastErrorMessage: errMsg,
          lastErrorStatusCode: code,
        );
      }
    });

    when(() => mockDao.getQueueSummary(
          tenantId: any(named: 'tenantId'),
          userId: any(named: 'userId'),
        )).thenAnswer((inv) async {
      final tId = inv.namedArguments[#tenantId] as String;
      final uId = inv.namedArguments[#userId] as String;
      final items = inMemoryQueue.values
          .where((item) => item.tenantId == tId && item.userId == uId)
          .toList();
      final pending =
          items.where((i) => i.syncStatus == SyncStatus.pendingSync).length;
      final syncing =
          items.where((i) => i.syncStatus == SyncStatus.syncing).length;
      final synced =
          items.where((i) => i.syncStatus == SyncStatus.synced).length;
      final rejected = items
          .where((i) => i.syncStatus == SyncStatus.rejectedPermanent)
          .length;
      final quarantined = items
          .where((i) => i.syncStatus == SyncStatus.quarantinedDependentFailure)
          .length;
      final flagged = items
          .where((i) => i.syncStatus == SyncStatus.flaggedPendingReview)
          .length;

      DateTime? lastSynced;
      final syncedItems =
          items.where((i) => i.syncStatus == SyncStatus.synced).toList();
      if (syncedItems.isNotEmpty) {
        syncedItems
            .sort((a, b) => b.deviceReportedAt.compareTo(a.deviceReportedAt));
        lastSynced = syncedItems.first.deviceReportedAt;
      }

      return SyncQueueSummary(
        pendingCount: pending,
        syncingCount: syncing,
        syncedCount: synced,
        permanentlyRejectedCount: rejected,
        quarantinedCount: quarantined,
        flaggedCount: flagged,
        lastSyncedAt: lastSynced,
      );
    });

    when(() => mockRemoteDataSource.recordPunch(any())).thenAnswer((inv) async {
      final req = inv.positionalArguments[0] as PunchRequestModel;
      dispatchedRequests.add(req);
      return createServerPunchResponse(req);
    });
  });

  tearDown(() {
    connectivityController.close();
  });

  group('Phase 6.5.D — End-to-End Offline Shift Journey Simulation', () {
    test(
        'Simulates complete 4-punch employee journey with offline capture, app restart, and FIFO recovery',
        () async {
      // -----------------------------------------------------------------------
      // Step 1: Employee records 4 punches offline during an 8-hour shift
      // -----------------------------------------------------------------------
      final punch1 = createQueueItem(
        localId: 'loc-punch-001',
        idempotencyKey: 'idemp-001-checkin',
        eventType: AttendanceEventType.checkIn,
        sequenceNumber: 1,
        deviceReportedAt: DateTime.utc(2026, 11, 4, 9, 0, 0),
      );
      final punch2 = createQueueItem(
        localId: 'loc-punch-002',
        idempotencyKey: 'idemp-002-breakstart',
        eventType: AttendanceEventType.breakStart,
        sequenceNumber: 2,
        deviceReportedAt: DateTime.utc(2026, 11, 4, 13, 0, 0),
      );
      final punch3 = createQueueItem(
        localId: 'loc-punch-003',
        idempotencyKey: 'idemp-003-breakend',
        eventType: AttendanceEventType.breakEnd,
        sequenceNumber: 3,
        deviceReportedAt: DateTime.utc(2026, 11, 4, 13, 45, 0),
      );
      final punch4 = createQueueItem(
        localId: 'loc-punch-004',
        idempotencyKey: 'idemp-004-checkout',
        eventType: AttendanceEventType.checkOut,
        sequenceNumber: 4,
        deviceReportedAt: DateTime.utc(2026, 11, 4, 17, 30, 0),
      );

      // Persist all 4 events into offline queue
      inMemoryQueue[punch1.localId] = punch1;
      inMemoryQueue[punch2.localId] = punch2;
      inMemoryQueue[punch3.localId] = punch3;
      inMemoryQueue[punch4.localId] = punch4;

      // Verify pre-sync summary: 4 pending, 0 synced
      var preSummary = await mockDao.getQueueSummary(
        tenantId: tTenantId,
        userId: tUserId,
      );
      expect(preSummary.pendingCount, equals(4));
      expect(preSummary.unresolvedCount, equals(4));
      expect(preSummary.syncedCount, equals(0));

      // -----------------------------------------------------------------------
      // Step 2: Employee closes app & restarts (Simulate process termination)
      // -----------------------------------------------------------------------
      // Instantiating a new SyncWorker instance (simulating app boot)
      final worker = SyncWorkerImpl(
        localQueueDao: mockDao,
        remoteDataSource: mockRemoteDataSource,
        connectivityService: mockConnectivityService,
      );

      // Verify queue survived restart with strict FIFO order
      final pendingAfterRestart = await mockDao.getPendingEventsFifo(
        tenantId: tTenantId,
        userId: tUserId,
      );
      expect(pendingAfterRestart.length, equals(4));
      expect(pendingAfterRestart[0].eventType,
          equals(AttendanceEventType.checkIn));
      expect(pendingAfterRestart[1].eventType,
          equals(AttendanceEventType.breakStart));
      expect(pendingAfterRestart[2].eventType,
          equals(AttendanceEventType.breakEnd));
      expect(pendingAfterRestart[3].eventType,
          equals(AttendanceEventType.checkOut));

      // -----------------------------------------------------------------------
      // Step 3: Network connectivity returns & synchronization executes
      // -----------------------------------------------------------------------
      final syncResult = await worker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );

      // -----------------------------------------------------------------------
      // Step 4: Verify synchronization outcome and strict FIFO order
      // -----------------------------------------------------------------------
      expect(syncResult.isCompleted, isTrue);
      expect(syncResult.syncedCount, equals(4));
      expect(syncResult.permanentlyRejectedCount, equals(0));
      expect(syncResult.quarantinedCount, equals(0));
      expect(syncResult.retryableFailureCount, equals(0));

      // Verify backend received exactly 4 requests in strict chronological FIFO order
      expect(dispatchedRequests.length, equals(4));
      expect(
          dispatchedRequests[0].eventType, equals(AttendanceEventType.checkIn));
      expect(dispatchedRequests[0].idempotencyKey, equals('idemp-001-checkin'));
      expect(dispatchedRequests[1].eventType,
          equals(AttendanceEventType.breakStart));
      expect(
          dispatchedRequests[1].idempotencyKey, equals('idemp-002-breakstart'));
      expect(dispatchedRequests[2].eventType,
          equals(AttendanceEventType.breakEnd));
      expect(
          dispatchedRequests[2].idempotencyKey, equals('idemp-003-breakend'));
      expect(dispatchedRequests[3].eventType,
          equals(AttendanceEventType.checkOut));
      expect(
          dispatchedRequests[3].idempotencyKey, equals('idemp-004-checkout'));

      // Verify all items in database transitioned to SYNCED with server IDs
      for (final item in inMemoryQueue.values) {
        expect(item.syncStatus, equals(SyncStatus.synced));
        expect(item.serverEventId, isNotNull);
        expect(item.serverEventId!.startsWith('srv-'), isTrue);
      }

      // Verify final queue summary: 0 pending, 4 synced, 0 unresolved
      final postSummary = await mockDao.getQueueSummary(
        tenantId: tTenantId,
        userId: tUserId,
      );
      expect(postSummary.pendingCount, equals(0));
      expect(postSummary.unresolvedCount, equals(0));
      expect(postSummary.syncedCount, equals(4));
      expect(postSummary.lastSyncedAt,
          equals(DateTime.utc(2026, 11, 4, 17, 30, 0)));

      worker.dispose();
    });
  });
}
