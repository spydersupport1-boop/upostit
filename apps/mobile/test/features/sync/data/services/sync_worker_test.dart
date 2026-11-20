import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
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

class MockLocalQueueDao extends Mock implements LocalQueueDao {}

class MockAttendanceRemoteDataSource extends Mock
    implements AttendanceRemoteDataSource {}

class MockNetworkConnectivityService extends Mock
    implements NetworkConnectivityService {}

void main() {
  late MockLocalQueueDao mockDao;
  late MockAttendanceRemoteDataSource mockRemoteDataSource;
  late MockNetworkConnectivityService mockConnectivityService;
  late SyncWorkerImpl syncWorker;
  late StreamController<bool> connectivityController;
  final deactivatedCalls = <String>[];
  final Map<String, LocalQueueItem> inMemoryQueue = {};

  const tTenantId = 'tenant-xyz';
  const tUserId = 'user-123';
  const tEmployeeId = 'emp-456';
  final tTimestamp1 = DateTime.utc(2026, 11, 4, 8, 30, 0);
  final tTimestamp2 = DateTime.utc(2026, 11, 4, 9, 0, 0);

  LocalQueueItem createQueueItem({
    required String localId,
    required String idempotencyKey,
    required int sequenceNumber,
    AttendanceEventType eventType = AttendanceEventType.checkIn,
    String? sessionId,
    DateTime? deviceReportedAt,
    SyncStatus syncStatus = SyncStatus.pendingSync,
    int retryCount = 0,
    String? wifiBssid = '00:11:22:33:44:55',
    String? wifiSsid = 'Office_Secure_WiFi',
  }) {
    return LocalQueueItem(
      localId: localId,
      idempotencyKey: idempotencyKey,
      sessionId: sessionId ?? 'sess-1',
      tenantId: tTenantId,
      employeeId: tEmployeeId,
      userId: tUserId,
      eventType: eventType,
      deviceReportedAt: deviceReportedAt ?? tTimestamp1,
      timezoneOffsetMinutes: 0,
      monotonicBootTimeMs: 1234567,
      bootSessionId: 'boot-abc',
      isRebootDetected: false,
      locationId: 'loc-1',
      latitude: 37.7749,
      longitude: -122.4194,
      accuracyMeters: 5.0,
      wifiBssid: wifiBssid,
      wifiSsid: wifiSsid,
      wifiSignalStatus: 'AVAILABLE',
      appliedPolicyVersion: 1,
      appliedPolicyMode: 'WIFI_ONLY',
      deviceId: 'dev-1',
      metadataJson: '{"test_key":"val"}',
      sequenceNumber: sequenceNumber,
      syncStatus: syncStatus,
      retryCount: retryCount,
      createdAt: DateTime.utc(2026, 11, 4, 8, 30, 0),
      updatedAt: DateTime.utc(2026, 11, 4, 8, 30, 0),
    );
  }

  void seedQueue(List<LocalQueueItem> items) {
    inMemoryQueue.clear();
    for (final item in items) {
      inMemoryQueue[item.localId] = item;
    }
  }

  PunchResponseModel createPunchResponse({
    required String eventId,
    required String idempotencyKey,
    AttendanceEventType eventType = AttendanceEventType.checkIn,
    String reviewStatus = 'NOT_REQUIRED',
    bool isIdempotentReplay = false,
  }) {
    return PunchResponseModel(
      event: AttendanceEventModel(
        id: eventId,
        tenantId: tTenantId,
        employeeId: tEmployeeId,
        eventType: eventType,
        eventCategory: 'STANDARD',
        serverReceivedAt: DateTime.utc(2026, 11, 4, 9, 0, 0),
        effectiveAt: DateTime.utc(2026, 11, 4, 9, 0, 0),
        source: 'MOBILE_OFFLINE_SYNC',
        timestampVerificationStatus: 'SERVER_AUTHORITATIVE',
        reviewStatus: reviewStatus,
        idempotencyKey: idempotencyKey,
        createdAt: DateTime.utc(2026, 11, 4, 9, 0, 0),
      ),
      isIdempotentReplay: isIdempotentReplay,
    );
  }

  setUpAll(() {
    registerFallbackValue(
      const PunchRequestModel(
        eventType: AttendanceEventType.checkIn,
        idempotencyKey: 'fallback-key',
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
    deactivatedCalls.clear();
    inMemoryQueue.clear();

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

    when(() => mockDao.markPermanentlyRejected(
          localId: any(named: 'localId'),
          errorMessage: any(named: 'errorMessage'),
          statusCode: any(named: 'statusCode'),
        )).thenAnswer((inv) async {
      final id = inv.namedArguments[#localId] as String;
      final errMsg = inv.namedArguments[#errorMessage] as String?;
      final code = inv.namedArguments[#statusCode] as int?;
      final existing = inMemoryQueue[id];
      if (existing != null) {
        inMemoryQueue[id] = existing.copyWith(
          syncStatus: SyncStatus.rejectedPermanent,
          lastErrorMessage: errMsg,
          lastErrorStatusCode: code,
        );
      }
    });

    when(() => mockDao.quarantineDependentEvents(
          tenantId: any(named: 'tenantId'),
          userId: any(named: 'userId'),
          conflictBundleId: any(named: 'conflictBundleId'),
          fromLocalId: any(named: 'fromLocalId'),
        )).thenAnswer((inv) async {
      final fromId = inv.namedArguments[#fromLocalId] as String;
      final conflictBundleId = inv.namedArguments[#conflictBundleId] as String;
      final failedItem = inMemoryQueue[fromId];
      if (failedItem == null || failedItem.sessionId == null) return 0;
      int count = 0;
      for (final key in inMemoryQueue.keys) {
        final item = inMemoryQueue[key]!;
        if (item.sessionId == failedItem.sessionId &&
            item.sequenceNumber > failedItem.sequenceNumber &&
            item.syncStatus == SyncStatus.pendingSync) {
          inMemoryQueue[key] = item.copyWith(
            syncStatus: SyncStatus.quarantinedDependentFailure,
            conflictBundleId: conflictBundleId,
          );
          count++;
        }
      }
      return count;
    });

    syncWorker = SyncWorkerImpl(
      localQueueDao: mockDao,
      remoteDataSource: mockRemoteDataSource,
      connectivityService: mockConnectivityService,
      onAccountDeactivated: (msg) => deactivatedCalls.add(msg),
      initialBackoff: const Duration(seconds: 2),
      maxBackoff: const Duration(seconds: 60),
    );
  });

  tearDown(() {
    syncWorker.dispose();
    connectivityController.close();
  });

  group('SyncWorkerImpl - FIFO Synchronization', () {
    test('executes FIFO processing order and crash recovery of zombie records',
        () async {
      final item1 = createQueueItem(
        localId: 'loc-1',
        idempotencyKey: 'idem-1',
        sequenceNumber: 1,
        eventType: AttendanceEventType.checkIn,
        deviceReportedAt: tTimestamp1,
      );
      final item2 = createQueueItem(
        localId: 'loc-2',
        idempotencyKey: 'idem-2',
        sequenceNumber: 2,
        eventType: AttendanceEventType.checkOut,
        deviceReportedAt: tTimestamp2,
      );
      seedQueue([item1, item2]);

      final capturedRequests = <PunchRequestModel>[];
      when(() => mockRemoteDataSource.recordPunch(any()))
          .thenAnswer((invocation) async {
        final req = invocation.positionalArguments[0] as PunchRequestModel;
        capturedRequests.add(req);
        return createPunchResponse(
          eventId: 'srv-${req.idempotencyKey}',
          idempotencyKey: req.idempotencyKey,
          eventType: req.eventType,
        );
      });

      final result = await syncWorker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );

      // Verify zombie reset called first
      verify(() => mockDao.resetZombieSyncingItems(
            timeout: const Duration(seconds: 120),
          )).called(1);

      // Verify FIFO order execution
      expect(capturedRequests.length, equals(2));
      expect(capturedRequests[0].idempotencyKey, equals('idem-1'));
      expect(
          capturedRequests[0].eventType, equals(AttendanceEventType.checkIn));
      expect(capturedRequests[1].idempotencyKey, equals('idem-2'));
      expect(
          capturedRequests[1].eventType, equals(AttendanceEventType.checkOut));

      // Verify status updates
      verify(() => mockDao.updateSyncStatus(
            localId: 'loc-1',
            status: SyncStatus.syncing,
          )).called(1);
      verify(() => mockDao.updateSyncStatus(
            localId: 'loc-1',
            status: SyncStatus.synced,
            serverEventId: 'srv-idem-1',
          )).called(1);

      verify(() => mockDao.updateSyncStatus(
            localId: 'loc-2',
            status: SyncStatus.syncing,
          )).called(1);
      verify(() => mockDao.updateSyncStatus(
            localId: 'loc-2',
            status: SyncStatus.synced,
            serverEventId: 'srv-idem-2',
          )).called(1);

      expect(result.syncedCount, equals(2));
      expect(result.isCompleted, isTrue);
    });

    test('enforces single-worker mutex per account and rejects concurrent sync',
        () async {
      final item = createQueueItem(
        localId: 'loc-1',
        idempotencyKey: 'idem-1',
        sequenceNumber: 1,
      );
      seedQueue([item]);

      final completer = Completer<PunchResponseModel>();

      when(() => mockRemoteDataSource.recordPunch(any()))
          .thenAnswer((_) => completer.future);

      // Start first sync
      final future1 = syncWorker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );

      expect(syncWorker.isSyncing(tTenantId, tUserId), isTrue);

      // Attempt concurrent sync for same account
      final concurrentResult = await syncWorker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );

      expect(concurrentResult.isCompleted, isFalse);
      expect(concurrentResult.errorMessage,
          contains('Synchronization is already active for this account'));

      // Release first sync
      completer.complete(createPunchResponse(
        eventId: 'srv-1',
        idempotencyKey: 'idem-1',
      ));

      final result1 = await future1;
      expect(result1.syncedCount, equals(1));
      expect(syncWorker.isSyncing(tTenantId, tUserId), isFalse);
    });

    test('preserves exact original timestamps and metadata in punch request',
        () async {
      final item = createQueueItem(
        localId: 'loc-orig',
        idempotencyKey: 'idem-orig-uuid',
        sequenceNumber: 10,
        deviceReportedAt: DateTime.utc(2026, 11, 4, 7, 15, 30),
      );
      seedQueue([item]);

      PunchRequestModel? captured;
      when(() => mockRemoteDataSource.recordPunch(any()))
          .thenAnswer((invocation) async {
        captured = invocation.positionalArguments[0] as PunchRequestModel;
        return createPunchResponse(
          eventId: 'srv-orig',
          idempotencyKey: captured!.idempotencyKey,
        );
      });

      await syncWorker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );

      expect(captured, isNotNull);
      final req = captured!;
      expect(req.idempotencyKey, equals('idem-orig-uuid'));
      expect(
          req.deviceReportedAt, equals(DateTime.utc(2026, 11, 4, 7, 15, 30)));
      expect(req.metadata['offline_queued'], isTrue);
      expect(req.metadata['offline_sequence_number'], equals(10));
      expect(req.metadata['monotonic_boot_time_ms'], equals(1234567));
      expect(req.metadata['boot_session_id'], equals('boot-abc'));
      expect(req.metadata['session_id'], equals('sess-1'));
    });
  });

  group('SyncWorkerImpl - Retry and Error Classification', () {
    test(
        'handles NetworkException: updates status to pending, breaks loop, and computes backoff',
        () async {
      final item = createQueueItem(
        localId: 'loc-net',
        idempotencyKey: 'idem-net',
        sequenceNumber: 1,
        retryCount: 2,
      );
      seedQueue([item]);

      when(() => mockRemoteDataSource.recordPunch(any())).thenThrow(
          const NetworkException('SocketException: Connection refused'));

      final result = await syncWorker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );

      expect(result.isCompleted, isFalse);
      expect(result.retryableFailureCount, equals(1));
      expect(result.errorMessage, contains('Connection refused'));
      expect(result.retryAfterSeconds, equals(4)); // 2s * 2^(2-1) = 4s

      verify(() => mockDao.updateSyncStatus(
            localId: 'loc-net',
            status: SyncStatus.pendingSync,
            errorMessage: 'SocketException: Connection refused',
          )).called(1);
    });

    test('handles HTTP 429 with retry_after header detail', () async {
      final item = createQueueItem(
        localId: 'loc-429',
        idempotencyKey: 'idem-429',
        sequenceNumber: 1,
      );
      seedQueue([item]);

      when(() => mockRemoteDataSource.recordPunch(any())).thenThrow(
        const ServerException(
          'Too Many Requests',
          statusCode: 429,
          details: {'retry_after': 30},
        ),
      );

      final result = await syncWorker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );

      expect(result.isCompleted, isFalse);
      expect(result.retryableFailureCount, equals(1));
      expect(result.retryAfterSeconds, equals(30));
    });

    test('handles HTTP 5xx retryable server error', () async {
      final item = createQueueItem(
        localId: 'loc-503',
        idempotencyKey: 'idem-503',
        sequenceNumber: 1,
      );
      seedQueue([item]);

      when(() => mockRemoteDataSource.recordPunch(any())).thenThrow(
        const ServerException(
          'Service Unavailable',
          statusCode: 503,
        ),
      );

      final result = await syncWorker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );

      expect(result.isCompleted, isFalse);
      expect(result.retryableFailureCount, equals(1));
    });

    test('calculates exponential backoff capped at maxBackoff', () {
      expect(
          syncWorker.calculateBackoff(0), equals(const Duration(seconds: 2)));
      expect(
          syncWorker.calculateBackoff(1), equals(const Duration(seconds: 2)));
      expect(
          syncWorker.calculateBackoff(2), equals(const Duration(seconds: 4)));
      expect(
          syncWorker.calculateBackoff(3), equals(const Duration(seconds: 8)));
      expect(
          syncWorker.calculateBackoff(4), equals(const Duration(seconds: 16)));
      expect(
          syncWorker.calculateBackoff(5), equals(const Duration(seconds: 32)));
      expect(syncWorker.calculateBackoff(6),
          equals(const Duration(seconds: 60))); // Capped at 60s
      expect(
          syncWorker.calculateBackoff(10), equals(const Duration(seconds: 60)));
    });
  });

  group('SyncWorkerImpl - Permanent Domain Rejections & Session Quarantine',
      () {
    test(
        'marks permanent rejection on 422, cascades session quarantine, and continues next session',
        () async {
      // Shift 1: Check-in fails, Break-start should be quarantined
      final shift1CheckIn = createQueueItem(
        localId: 's1-checkin',
        idempotencyKey: 'idem-s1-1',
        sequenceNumber: 1,
        sessionId: 'session-shift-1',
      );
      final shift1BreakStart = createQueueItem(
        localId: 's1-break',
        idempotencyKey: 'idem-s1-2',
        sequenceNumber: 2,
        sessionId: 'session-shift-1',
      );

      // Shift 2: Independent session, should succeed
      final shift2CheckIn = createQueueItem(
        localId: 's2-checkin',
        idempotencyKey: 'idem-s2-1',
        sequenceNumber: 3,
        sessionId: 'session-shift-2',
      );

      seedQueue([shift1CheckIn, shift1BreakStart, shift2CheckIn]);

      when(() => mockRemoteDataSource.recordPunch(any()))
          .thenAnswer((invocation) async {
        final req = invocation.positionalArguments[0] as PunchRequestModel;
        if (req.idempotencyKey == 'idem-s1-1') {
          throw const ServerException(
            'Unprocessable Entity: Outside geofence',
            statusCode: 422,
          );
        }
        return createPunchResponse(
          eventId: 'srv-${req.idempotencyKey}',
          idempotencyKey: req.idempotencyKey,
        );
      });

      final result = await syncWorker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );

      expect(result.permanentlyRejectedCount, equals(1));
      expect(result.quarantinedCount, equals(1));
      expect(result.syncedCount, equals(1)); // Shift 2 succeeded!
      expect(result.isCompleted, isTrue);

      verify(() => mockDao.markPermanentlyRejected(
            localId: 's1-checkin',
            errorMessage: 'Unprocessable Entity: Outside geofence',
            statusCode: 422,
          )).called(1);

      verify(() => mockDao.quarantineDependentEvents(
            tenantId: tTenantId,
            userId: tUserId,
            conflictBundleId: any(named: 'conflictBundleId'),
            fromLocalId: 's1-checkin',
          )).called(1);

      // Verify Shift 2 CheckIn was synced
      verify(() => mockDao.updateSyncStatus(
            localId: 's2-checkin',
            status: SyncStatus.synced,
            serverEventId: 'srv-idem-s2-1',
          )).called(1);
    });

    test('handles idempotent replay from server without duplicate side effects',
        () async {
      final item = createQueueItem(
        localId: 'loc-replay',
        idempotencyKey: 'idem-replay',
        sequenceNumber: 1,
      );
      seedQueue([item]);

      when(() => mockRemoteDataSource.recordPunch(any())).thenAnswer(
        (_) async => createPunchResponse(
          eventId: 'srv-existing-replay',
          idempotencyKey: 'idem-replay',
          isIdempotentReplay: true,
        ),
      );

      final result = await syncWorker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );

      expect(result.syncedCount, equals(1));
      verify(() => mockDao.updateSyncStatus(
            localId: 'loc-replay',
            status: SyncStatus.synced,
            serverEventId: 'srv-existing-replay',
          )).called(1);
    });

    test('maps server review status PENDING_REVIEW to flaggedPendingReview',
        () async {
      final item = createQueueItem(
        localId: 'loc-flag',
        idempotencyKey: 'idem-flag',
        sequenceNumber: 1,
      );
      seedQueue([item]);

      when(() => mockRemoteDataSource.recordPunch(any())).thenAnswer(
        (_) async => createPunchResponse(
          eventId: 'srv-flagged',
          idempotencyKey: 'idem-flag',
          reviewStatus: 'PENDING_REVIEW',
        ),
      );

      final result = await syncWorker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );

      expect(result.syncedCount, equals(1));
      verify(() => mockDao.updateSyncStatus(
            localId: 'loc-flag',
            status: SyncStatus.flaggedPendingReview,
            serverEventId: 'srv-flagged',
          )).called(1);
    });
  });

  group('SyncWorkerImpl - Auth & Account Deactivation', () {
    test('pauses sync on AuthException and preserves local records intact',
        () async {
      final item = createQueueItem(
        localId: 'loc-auth',
        idempotencyKey: 'idem-auth',
        sequenceNumber: 1,
      );
      seedQueue([item]);

      when(() => mockRemoteDataSource.recordPunch(any())).thenThrow(
        const AuthException('Token expired and refresh failed',
            statusCode: 401),
      );

      final result = await syncWorker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );

      expect(result.isCompleted, isFalse);
      expect(result.errorMessage, contains('Token expired and refresh failed'));

      // Verified item is put back to pending, NOT deleted or rejected
      verify(() => mockDao.updateSyncStatus(
            localId: 'loc-auth',
            status: SyncStatus.pendingSync,
            errorMessage: 'Token expired and refresh failed',
            statusCode: 401,
          )).called(1);

      verifyNever(() => mockDao.markPermanentlyRejected(
            localId: any(named: 'localId'),
            errorMessage: any(named: 'errorMessage'),
          ));
    });

    test('invokes onAccountDeactivated callback when account is deactivated',
        () async {
      final item = createQueueItem(
        localId: 'loc-deact',
        idempotencyKey: 'idem-deact',
        sequenceNumber: 1,
      );
      seedQueue([item]);

      when(() => mockRemoteDataSource.recordPunch(any())).thenThrow(
        const ServerException('User account has been deactivated',
            statusCode: 403),
      );

      final result = await syncWorker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );

      expect(result.isCompleted, isFalse);
      expect(deactivatedCalls.length, equals(1));
      expect(
          deactivatedCalls[0], contains('User account has been deactivated'));
    });
  });

  group('SyncWorkerImpl - Auto Sync & Lifecycle', () {
    test('triggers sync when connectivity is restored', () async {
      final item = createQueueItem(
        localId: 'loc-auto',
        idempotencyKey: 'idem-auto',
        sequenceNumber: 1,
      );
      seedQueue([item]);

      when(() => mockRemoteDataSource.recordPunch(any())).thenAnswer(
        (_) async => createPunchResponse(
          eventId: 'srv-auto',
          idempotencyKey: 'idem-auto',
        ),
      );

      syncWorker.startAutoSync(
        tenantId: tTenantId,
        userId: tUserId,
      );

      // Emit connectivity restored
      connectivityController.add(true);
      await pumpEventQueue();

      verify(() => mockDao.getPendingEventsFifo(
            tenantId: tTenantId,
            userId: tUserId,
            limit: any(named: 'limit'),
          )).called(greaterThanOrEqualTo(1));
    });

    test('stopAutoSync cancels connectivity subscription', () async {
      syncWorker.startAutoSync(
        tenantId: tTenantId,
        userId: tUserId,
      );
      syncWorker.stopAutoSync();

      connectivityController.add(true);
      await pumpEventQueue();

      verifyNever(() => mockDao.getPendingEventsFifo(
            tenantId: any(named: 'tenantId'),
            userId: any(named: 'userId'),
          ));
    });

    test(
        'onAppForegrounded triggers sync when connected and auto-sync is configured',
        () async {
      when(() => mockConnectivityService.isConnected())
          .thenAnswer((_) async => true);

      final item = createQueueItem(
        localId: 'loc-foreground',
        idempotencyKey: 'idem-foreground',
        sequenceNumber: 1,
      );
      seedQueue([item]);

      when(() => mockRemoteDataSource.recordPunch(any())).thenAnswer(
        (_) async => createPunchResponse(
          eventId: 'srv-foreground',
          idempotencyKey: 'idem-foreground',
        ),
      );

      syncWorker.startAutoSync(
        tenantId: tTenantId,
        userId: tUserId,
      );

      final result = await syncWorker.onAppForegrounded();

      expect(result, isNotNull);
      expect(result!.syncedCount, equals(1));
    });

    test('onAppForegrounded does nothing when network is disconnected',
        () async {
      when(() => mockConnectivityService.isConnected())
          .thenAnswer((_) async => false);

      syncWorker.startAutoSync(
        tenantId: tTenantId,
        userId: tUserId,
      );

      final result = await syncWorker.onAppForegrounded();
      expect(result, isNull);

      verifyNever(() => mockRemoteDataSource.recordPunch(any()));
    });
  });

  group('SyncWorkerImpl - Isolation, Recovery & Token Scenarios', () {
    test('enforces strict tenant and user isolation in queue queries',
        () async {
      const otherTenant = 'tenant-other';
      const otherUser = 'user-other';

      final userItem = createQueueItem(
        localId: 'loc-my-item',
        idempotencyKey: 'idem-my-user',
        sequenceNumber: 1,
      );
      seedQueue([userItem]);

      when(() => mockRemoteDataSource.recordPunch(any())).thenAnswer(
        (_) async => createPunchResponse(
          eventId: 'srv-my-user',
          idempotencyKey: 'idem-my-user',
        ),
      );

      // Synchronize for other tenant/user (which has empty queue)
      final otherResult = await syncWorker.synchronizeQueue(
        tenantId: otherTenant,
        userId: otherUser,
      );

      expect(otherResult.syncedCount, equals(0));
      expect(otherResult.isCompleted, isTrue);

      // Verify that my user's item remains untouched and still pending
      expect(inMemoryQueue['loc-my-item']!.syncStatus,
          equals(SyncStatus.pendingSync));
    });

    test(
        'handles account switching cleanly without cross-account state pollution',
        () async {
      const userA = 'user-A';
      const userB = 'user-B';

      syncWorker.startAutoSync(
        tenantId: tTenantId,
        userId: userA,
      );

      // Switch to User B
      syncWorker.startAutoSync(
        tenantId: tTenantId,
        userId: userB,
      );

      when(() => mockConnectivityService.isConnected())
          .thenAnswer((_) async => true);

      await syncWorker.onAppForegrounded();

      // Verify getPendingEventsFifo was queried for userB, NOT userA
      verify(() => mockDao.getPendingEventsFifo(
            tenantId: tTenantId,
            userId: userB,
            limit: any(named: 'limit'),
          )).called(1);

      verifyNever(() => mockDao.getPendingEventsFifo(
            tenantId: tTenantId,
            userId: userA,
            limit: any(named: 'limit'),
          ));
    });

    test('handles HTTP 400 permanent domain rejection without infinite retries',
        () async {
      final item = createQueueItem(
        localId: 'loc-400',
        idempotencyKey: 'idem-400',
        sequenceNumber: 1,
      );
      seedQueue([item]);

      when(() => mockRemoteDataSource.recordPunch(any())).thenThrow(
        const ServerException('Bad Request: Invalid state transition',
            statusCode: 400),
      );

      final result = await syncWorker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );

      expect(result.isCompleted, isTrue);
      expect(result.permanentlyRejectedCount, equals(1));
      expect(result.retryableFailureCount, equals(0));

      verify(() => mockDao.markPermanentlyRejected(
            localId: 'loc-400',
            errorMessage: 'Bad Request: Invalid state transition',
            statusCode: 400,
          )).called(1);
    });

    test('recovers from stranded syncing state via crash recovery zombie reset',
        () async {
      when(() => mockDao.resetZombieSyncingItems(
            timeout: const Duration(seconds: 120),
          )).thenAnswer((_) async => 2); // 2 zombies reset

      final result = await syncWorker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );

      expect(result.isCompleted, isTrue);
      verify(() => mockDao.resetZombieSyncingItems(
            timeout: const Duration(seconds: 120),
          )).called(1);
    });

    test(
        'resumes synchronization on subsequent run after token refresh recovery',
        () async {
      final item = createQueueItem(
        localId: 'loc-refresh-recover',
        idempotencyKey: 'idem-refresh-recover',
        sequenceNumber: 1,
      );
      seedQueue([item]);

      // Run 1: Fails with AuthException
      when(() => mockRemoteDataSource.recordPunch(any())).thenThrow(
        const AuthException('Token expired', statusCode: 401),
      );

      final result1 = await syncWorker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );

      expect(result1.isCompleted, isFalse);
      expect(inMemoryQueue['loc-refresh-recover']!.syncStatus,
          equals(SyncStatus.pendingSync));

      // Token refreshed! Run 2 succeeds:
      when(() => mockRemoteDataSource.recordPunch(any())).thenAnswer(
        (_) async => createPunchResponse(
          eventId: 'srv-recovered',
          idempotencyKey: 'idem-refresh-recover',
        ),
      );

      final result2 = await syncWorker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );

      expect(result2.isCompleted, isTrue);
      expect(result2.syncedCount, equals(1));
      expect(inMemoryQueue['loc-refresh-recover']!.syncStatus,
          equals(SyncStatus.synced));
    });
  });
}
