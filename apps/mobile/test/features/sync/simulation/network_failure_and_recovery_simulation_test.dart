import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/errors/app_exception.dart';
import 'package:mobile/features/attendance/data/datasources/attendance_remote_data_source.dart';
import 'package:mobile/features/attendance/data/models/attendance_event_model.dart';
import 'package:mobile/features/attendance/data/models/punch_request_model.dart';
import 'package:mobile/features/attendance/data/models/punch_response_model.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_event.dart';
import 'package:mobile/features/sync/data/services/sync_worker_impl.dart';
import 'package:mobile/features/sync/domain/entities/local_queue_item.dart';
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

  const tTenantId = 'tenant-net-1';
  const tUserId = 'user-net-1';
  const tEmployeeId = 'emp-net-1';

  final Map<String, LocalQueueItem> inMemoryQueue = {};
  final List<PunchRequestModel> dispatchedRequests = [];

  LocalQueueItem createQueueItem({
    required String localId,
    required String idempotencyKey,
    required AttendanceEventType eventType,
    required int sequenceNumber,
    int retryCount = 0,
  }) {
    return LocalQueueItem(
      localId: localId,
      idempotencyKey: idempotencyKey,
      sessionId: 'session-net',
      tenantId: tTenantId,
      employeeId: tEmployeeId,
      userId: tUserId,
      eventType: eventType,
      deviceReportedAt: DateTime.utc(2026, 11, 4, 10, sequenceNumber),
      timezoneOffsetMinutes: 0,
      monotonicBootTimeMs: 2000000 + sequenceNumber * 1000,
      bootSessionId: 'boot-net',
      appliedPolicyVersion: 1,
      appliedPolicyMode: 'MANUAL',
      sequenceNumber: sequenceNumber,
      syncStatus: SyncStatus.pendingSync,
      retryCount: retryCount,
      createdAt: DateTime.utc(2026, 11, 4, 10, sequenceNumber),
      updatedAt: DateTime.utc(2026, 11, 4, 10, sequenceNumber),
    );
  }

  setUpAll(() {
    registerFallbackValue(
      const PunchRequestModel(
        eventType: AttendanceEventType.checkIn,
        idempotencyKey: 'fallback-net-key',
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
      final list = inMemoryQueue.values
          .where((item) =>
              item.syncStatus == SyncStatus.pendingSync &&
              item.tenantId == tTenantId &&
              item.userId == tUserId)
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
          retryCount: status == SyncStatus.syncing
              ? existing.retryCount + 1
              : existing.retryCount,
        );
      }
    });
  });

  tearDown(() {
    connectivityController.close();
  });

  group('Phase 6.5.D — Network Failure & Recovery Simulation', () {
    test(
        'Scenario 1: Network drops mid-batch — completed punches remain synced, dropped punch resets to pending, retry resumes from dropped punch',
        () async {
      final p1 = createQueueItem(
        localId: 'p1',
        idempotencyKey: 'idemp-p1',
        eventType: AttendanceEventType.checkIn,
        sequenceNumber: 1,
      );
      final p2 = createQueueItem(
        localId: 'p2',
        idempotencyKey: 'idemp-p2',
        eventType: AttendanceEventType.breakStart,
        sequenceNumber: 2,
      );
      final p3 = createQueueItem(
        localId: 'p3',
        idempotencyKey: 'idemp-p3',
        eventType: AttendanceEventType.breakEnd,
        sequenceNumber: 3,
      );
      final p4 = createQueueItem(
        localId: 'p4',
        idempotencyKey: 'idemp-p4',
        eventType: AttendanceEventType.checkOut,
        sequenceNumber: 4,
      );

      inMemoryQueue['p1'] = p1;
      inMemoryQueue['p2'] = p2;
      inMemoryQueue['p3'] = p3;
      inMemoryQueue['p4'] = p4;

      // P1 and P2 succeed, P3 throws NetworkException
      when(() => mockRemoteDataSource.recordPunch(any()))
          .thenAnswer((inv) async {
        final req = inv.positionalArguments[0] as PunchRequestModel;
        dispatchedRequests.add(req);

        if (req.idempotencyKey == 'idemp-p3') {
          throw const NetworkException(
              'Connection aborted by peer: Wi-Fi dropped');
        }

        return PunchResponseModel(
          event: AttendanceEventModel(
            id: 'srv-${req.idempotencyKey}',
            tenantId: tTenantId,
            employeeId: tEmployeeId,
            eventType: req.eventType,
            eventCategory: 'STANDARD',
            serverReceivedAt: DateTime.now().toUtc(),
            effectiveAt: DateTime.now().toUtc(),
            source: 'MOBILE_OFFLINE_SYNC',
            timestampVerificationStatus: 'SERVER_AUTHORITATIVE',
            reviewStatus: 'NOT_REQUIRED',
            idempotencyKey: req.idempotencyKey,
            createdAt: DateTime.now().toUtc(),
          ),
          isIdempotentReplay: false,
        );
      });

      final worker = SyncWorkerImpl(
        localQueueDao: mockDao,
        remoteDataSource: mockRemoteDataSource,
        connectivityService: mockConnectivityService,
      );

      // Run 1: Fails at P3
      final result1 = await worker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );

      expect(result1.isCompleted, isFalse);
      expect(result1.syncedCount, equals(2));
      expect(result1.retryableFailureCount, equals(1));
      expect(result1.errorMessage, contains('Connection aborted'));

      // Check queue states after drop:
      expect(inMemoryQueue['p1']!.syncStatus, equals(SyncStatus.synced));
      expect(inMemoryQueue['p2']!.syncStatus, equals(SyncStatus.synced));
      // P3 safely reset back to pending with error message
      expect(inMemoryQueue['p3']!.syncStatus, equals(SyncStatus.pendingSync));
      expect(inMemoryQueue['p3']!.lastErrorMessage,
          contains('Connection aborted'));
      // P4 was never dispatched yet and remains pending
      expect(inMemoryQueue['p4']!.syncStatus, equals(SyncStatus.pendingSync));

      // Network restored: P3 now succeeds
      when(() => mockRemoteDataSource.recordPunch(any()))
          .thenAnswer((inv) async {
        final req = inv.positionalArguments[0] as PunchRequestModel;
        dispatchedRequests.add(req);
        return PunchResponseModel(
          event: AttendanceEventModel(
            id: 'srv-${req.idempotencyKey}',
            tenantId: tTenantId,
            employeeId: tEmployeeId,
            eventType: req.eventType,
            eventCategory: 'STANDARD',
            serverReceivedAt: DateTime.now().toUtc(),
            effectiveAt: DateTime.now().toUtc(),
            source: 'MOBILE_OFFLINE_SYNC',
            timestampVerificationStatus: 'SERVER_AUTHORITATIVE',
            reviewStatus: 'NOT_REQUIRED',
            idempotencyKey: req.idempotencyKey,
            createdAt: DateTime.now().toUtc(),
          ),
          isIdempotentReplay: false,
        );
      });

      // Run 2: Resume sync
      final result2 = await worker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );

      expect(result2.isCompleted, isTrue);
      expect(result2.syncedCount, equals(2)); // P3 and P4

      // All 4 are now synced
      expect(inMemoryQueue['p3']!.syncStatus, equals(SyncStatus.synced));
      expect(inMemoryQueue['p4']!.syncStatus, equals(SyncStatus.synced));

      worker.dispose();
    });

    test(
        'Scenario 2: Lost response after server acceptance — client replays identical idempotency key, server returns original event, client marks synced without duplicate',
        () async {
      final p1 = createQueueItem(
        localId: 'p-lost-response',
        idempotencyKey: 'idemp-server-accepted-lost-ack',
        eventType: AttendanceEventType.checkIn,
        sequenceNumber: 1,
      );
      inMemoryQueue[p1.localId] = p1;

      int attemptCount = 0;

      when(() => mockRemoteDataSource.recordPunch(any()))
          .thenAnswer((inv) async {
        final req = inv.positionalArguments[0] as PunchRequestModel;
        attemptCount++;

        if (attemptCount == 1) {
          // Server accepted the punch in database, but connection severed before ACK reaches client
          throw const NetworkException(
              'Connection reset by peer after transmission');
        }

        // On attempt 2, server recognizes duplicate idempotency key and returns original event
        expect(req.idempotencyKey, equals('idemp-server-accepted-lost-ack'));
        return PunchResponseModel(
          event: AttendanceEventModel(
            id: 'srv-original-event-100',
            tenantId: tTenantId,
            employeeId: tEmployeeId,
            eventType: req.eventType,
            eventCategory: 'STANDARD',
            serverReceivedAt: DateTime.utc(2026, 11, 4, 10, 0, 0),
            effectiveAt: DateTime.utc(2026, 11, 4, 10, 0, 0),
            source: 'MOBILE_OFFLINE_SYNC',
            timestampVerificationStatus: 'SERVER_AUTHORITATIVE',
            reviewStatus: 'NOT_REQUIRED',
            idempotencyKey: req.idempotencyKey,
            createdAt: DateTime.utc(2026, 11, 4, 10, 0, 0),
          ),
          isIdempotentReplay: true, // Server recognized replay!
        );
      });

      final worker = SyncWorkerImpl(
        localQueueDao: mockDao,
        remoteDataSource: mockRemoteDataSource,
        connectivityService: mockConnectivityService,
      );

      // Attempt 1 fails due to network drop during response
      final res1 =
          await worker.synchronizeQueue(tenantId: tTenantId, userId: tUserId);
      expect(res1.isCompleted, isFalse);
      expect(inMemoryQueue['p-lost-response']!.syncStatus,
          equals(SyncStatus.pendingSync));

      // Attempt 2 replays with the EXACT same idempotency key
      final res2 =
          await worker.synchronizeQueue(tenantId: tTenantId, userId: tUserId);
      expect(res2.isCompleted, isTrue);
      expect(res2.syncedCount, equals(1));

      // Local item transitioned to SYNCED with original server ID
      final item = inMemoryQueue['p-lost-response']!;
      expect(item.syncStatus, equals(SyncStatus.synced));
      expect(item.serverEventId, equals('srv-original-event-100'));

      worker.dispose();
    });

    test(
        'Scenario 3: HTTP 429 Rate Limiting — parses Retry-After header and respects backoff',
        () async {
      final p1 = createQueueItem(
        localId: 'p-429',
        idempotencyKey: 'idemp-429',
        eventType: AttendanceEventType.checkIn,
        sequenceNumber: 1,
      );
      inMemoryQueue[p1.localId] = p1;

      when(() => mockRemoteDataSource.recordPunch(any())).thenThrow(
        const ServerException(
          'Rate limit exceeded. Try again in 25 seconds.',
          statusCode: 429,
          details: {'retry_after': 25},
        ),
      );

      final worker = SyncWorkerImpl(
        localQueueDao: mockDao,
        remoteDataSource: mockRemoteDataSource,
        connectivityService: mockConnectivityService,
      );

      final result =
          await worker.synchronizeQueue(tenantId: tTenantId, userId: tUserId);

      expect(result.isCompleted, isFalse);
      expect(result.retryableFailureCount, equals(1));
      expect(result.retryAfterSeconds, equals(25));
      expect(
          inMemoryQueue['p-429']!.syncStatus, equals(SyncStatus.pendingSync));

      worker.dispose();
    });
  });
}
