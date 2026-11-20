import 'dart:async';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/errors/app_exception.dart';
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

  const tTenantId = 'tenant-corp-e2e';
  const tUserId = 'user-emp-e2e';
  const tEmployeeId = 'emp-e2e-77';
  const tDeviceId = 'install-device-uuid-9999';

  final Map<String, LocalQueueItem> inMemoryQueue = {};
  final List<PunchRequestModel> dispatchedRequests = [];

  LocalQueueItem createQueueItem({
    required String localId,
    required String idempotencyKey,
    required AttendanceEventType eventType,
    required int sequenceNumber,
    required DateTime deviceReportedAt,
    String? sessionId,
    String? deviceId = tDeviceId,
    bool? isMockLocation,
    DateTime? locationCapturedAt,
    double? latitude,
    double? longitude,
  }) {
    final metadata = <String, dynamic>{
      'client_captured': true,
      if (isMockLocation != null) 'is_mock_location': isMockLocation,
      if (locationCapturedAt != null)
        'location_captured_at': locationCapturedAt.toUtc().toIso8601String(),
    };

    return LocalQueueItem(
      localId: localId,
      idempotencyKey: idempotencyKey,
      sessionId: sessionId ?? 'session-2026-11-19',
      tenantId: tTenantId,
      employeeId: tEmployeeId,
      userId: tUserId,
      eventType: eventType,
      deviceReportedAt: deviceReportedAt,
      timezoneOffsetMinutes: 0,
      monotonicBootTimeMs: 1000000 + sequenceNumber * 60000,
      bootSessionId: 'boot-session-p7',
      appliedPolicyVersion: 1,
      appliedPolicyMode: 'GPS_ONLY',
      deviceId: deviceId,
      metadataJson: jsonEncode(metadata),
      latitude: latitude ?? 37.7749,
      longitude: longitude ?? -122.4194,
      accuracyMeters: 12.0,
      sequenceNumber: sequenceNumber,
      syncStatus: SyncStatus.pendingSync,
      createdAt: deviceReportedAt,
      updatedAt: deviceReportedAt,
    );
  }

  PunchResponseModel createServerPunchResponse(
    PunchRequestModel request, {
    String reviewStatus = 'NOT_REQUIRED',
    bool isReplay = false,
  }) {
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
        reviewStatus: reviewStatus,
        idempotencyKey: request.idempotencyKey,
        createdAt: DateTime.now().toUtc(),
      ),
      isIdempotentReplay: isReplay,
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
          lastAttemptedAt: DateTime.now().toUtc(),
          retryCount: status == SyncStatus.syncing
              ? existing.retryCount + 1
              : existing.retryCount,
        );
      }
    });

    when(() => mockDao.markPermanentlyRejected(
          localId: any(named: 'localId'),
          errorMessage: any(named: 'errorMessage'),
          statusCode: any(named: 'statusCode'),
        )).thenAnswer((inv) async {
      final id = inv.namedArguments[#localId] as String;
      final errMsg = inv.namedArguments[#errorMessage] as String;
      final code = inv.namedArguments[#statusCode] as int?;
      final existing = inMemoryQueue[id];
      if (existing != null) {
        inMemoryQueue[id] = existing.copyWith(
          syncStatus: SyncStatus.rejectedPermanent,
          lastErrorMessage: errMsg,
          lastErrorStatusCode: code,
          lastAttemptedAt: DateTime.now().toUtc(),
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
      final target = inMemoryQueue[fromId];
      if (target == null) return 0;

      int count = 0;
      for (final item in inMemoryQueue.values.toList()) {
        if (item.sessionId == target.sessionId &&
            item.sequenceNumber > target.sequenceNumber &&
            item.syncStatus == SyncStatus.pendingSync) {
          inMemoryQueue[item.localId] = item.copyWith(
            syncStatus: SyncStatus.quarantinedDependentFailure,
            conflictBundleId: inv.namedArguments[#conflictBundleId] as String,
          );
          count++;
        }
      }
      return count;
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
      return SyncQueueSummary(
        pendingCount:
            items.where((i) => i.syncStatus == SyncStatus.pendingSync).length,
        syncingCount:
            items.where((i) => i.syncStatus == SyncStatus.syncing).length,
        syncedCount:
            items.where((i) => i.syncStatus == SyncStatus.synced).length,
        permanentlyRejectedCount: items
            .where((i) => i.syncStatus == SyncStatus.rejectedPermanent)
            .length,
        quarantinedCount: items
            .where(
                (i) => i.syncStatus == SyncStatus.quarantinedDependentFailure)
            .length,
        flaggedCount: items
            .where((i) => i.syncStatus == SyncStatus.flaggedPendingReview)
            .length,
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

  group('Scenario A — Normal Offline Shift Journey with Device Telemetry', () {
    test(
        '4-punch journey offline capture preserves deviceId, timestamps, telemetry, and syncs in strict FIFO order',
        () async {
      final syncWorker = SyncWorkerImpl(
        localQueueDao: mockDao,
        remoteDataSource: mockRemoteDataSource,
        connectivityService: mockConnectivityService,
      );

      final checkInTime = DateTime.utc(2026, 11, 19, 8, 0, 0);
      final breakStartTime = DateTime.utc(2026, 11, 19, 12, 0, 0);
      final breakEndTime = DateTime.utc(2026, 11, 19, 12, 45, 0);
      final checkOutTime = DateTime.utc(2026, 11, 19, 17, 0, 0);

      final p1 = createQueueItem(
        localId: 'q-p1',
        idempotencyKey: 'idemp-p1-checkin',
        eventType: AttendanceEventType.checkIn,
        sequenceNumber: 1,
        deviceReportedAt: checkInTime,
        isMockLocation: false,
        locationCapturedAt: checkInTime,
      );
      final p2 = createQueueItem(
        localId: 'q-p2',
        idempotencyKey: 'idemp-p2-breakstart',
        eventType: AttendanceEventType.breakStart,
        sequenceNumber: 2,
        deviceReportedAt: breakStartTime,
        isMockLocation: false,
        locationCapturedAt: breakStartTime,
      );
      final p3 = createQueueItem(
        localId: 'q-p3',
        idempotencyKey: 'idemp-p3-breakend',
        eventType: AttendanceEventType.breakEnd,
        sequenceNumber: 3,
        deviceReportedAt: breakEndTime,
        isMockLocation: false,
        locationCapturedAt: breakEndTime,
      );
      final p4 = createQueueItem(
        localId: 'q-p4',
        idempotencyKey: 'idemp-p4-checkout',
        eventType: AttendanceEventType.checkOut,
        sequenceNumber: 4,
        deviceReportedAt: checkOutTime,
        isMockLocation: false,
        locationCapturedAt: checkOutTime,
      );

      inMemoryQueue['q-p1'] = p1;
      inMemoryQueue['q-p2'] = p2;
      inMemoryQueue['q-p3'] = p3;
      inMemoryQueue['q-p4'] = p4;

      final result = await syncWorker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );

      expect(result.syncedCount, equals(4));
      expect(result.permanentlyRejectedCount, equals(0));
      expect(result.quarantinedCount, equals(0));
      expect(result.isCompleted, isTrue);

      expect(dispatchedRequests.length, equals(4));
      expect(
          dispatchedRequests[0].eventType, equals(AttendanceEventType.checkIn));
      expect(dispatchedRequests[1].eventType,
          equals(AttendanceEventType.breakStart));
      expect(dispatchedRequests[2].eventType,
          equals(AttendanceEventType.breakEnd));
      expect(dispatchedRequests[3].eventType,
          equals(AttendanceEventType.checkOut));

      for (final req in dispatchedRequests) {
        expect(req.deviceId, equals(tDeviceId));
        expect(req.isMockLocation, isFalse);
        expect(req.locationCapturedAt, isNotNull);
        expect(req.metadata['offline_queued'], isTrue);
      }

      for (final id in ['q-p1', 'q-p2', 'q-p3', 'q-p4']) {
        expect(inMemoryQueue[id]?.syncStatus, equals(SyncStatus.synced));
        expect(inMemoryQueue[id]?.serverEventId, isNotNull);
      }
    });
  });

  group('Scenario B — App Termination & Restart Simulation', () {
    test(
        'Queue items survive termination and re-synchronize safely with unchanged device identity',
        () async {
      // 1. Initial run creates offline punch
      final p1 = createQueueItem(
        localId: 'q-survive-1',
        idempotencyKey: 'idemp-survive-1',
        eventType: AttendanceEventType.checkIn,
        sequenceNumber: 1,
        deviceReportedAt: DateTime.utc(2026, 11, 19, 8, 30, 0),
        deviceId: tDeviceId,
      );
      inMemoryQueue['q-survive-1'] = p1;

      // 2. Simulate force-stop and cold restart (create completely new SyncWorker instance)
      final restartedSyncWorker = SyncWorkerImpl(
        localQueueDao: mockDao,
        remoteDataSource: mockRemoteDataSource,
        connectivityService: mockConnectivityService,
      );

      // Verify records are intact before sync
      final summaryBefore = await mockDao.getQueueSummary(
        tenantId: tTenantId,
        userId: tUserId,
      );
      expect(summaryBefore.pendingCount, equals(1));
      expect(inMemoryQueue['q-survive-1']?.deviceId, equals(tDeviceId));

      // Verify no sensitive tokens are stored in the queue item
      final rawMetadata = inMemoryQueue['q-survive-1']!.metadataJson;
      expect(rawMetadata.contains('access_token'), isFalse);
      expect(rawMetadata.contains('refresh_token'), isFalse);
      expect(rawMetadata.contains('password'), isFalse);

      // 3. Resume sync on restored session
      final result = await restartedSyncWorker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );

      expect(result.syncedCount, equals(1));
      expect(dispatchedRequests.first.deviceId, equals(tDeviceId));
      expect(
          inMemoryQueue['q-survive-1']?.syncStatus, equals(SyncStatus.synced));
    });
  });

  group(
      'Scenario C — Network Loss During Sync (Acceptance/Response-Loss Boundary)',
      () {
    test(
        'Replays identical idempotency key on lost response and reconciles local queue via server replay response',
        () async {
      final syncWorker = SyncWorkerImpl(
        localQueueDao: mockDao,
        remoteDataSource: mockRemoteDataSource,
        connectivityService: mockConnectivityService,
      );

      final p1 = createQueueItem(
        localId: 'q-net-drop-1',
        idempotencyKey: 'idemp-net-drop-999',
        eventType: AttendanceEventType.checkIn,
        sequenceNumber: 1,
        deviceReportedAt: DateTime.utc(2026, 11, 19, 9, 0, 0),
      );
      inMemoryQueue['q-net-drop-1'] = p1;

      // First attempt: Backend accepts and commits, but socket disconnects before client gets response
      bool networkDropped = false;
      when(() => mockRemoteDataSource.recordPunch(any()))
          .thenAnswer((inv) async {
        if (!networkDropped) {
          networkDropped = true;
          throw const NetworkException(
              'Connection reset by peer during response transfer');
        }
        // Second attempt: Backend returns cached response with isIdempotentReplay: true
        final req = inv.positionalArguments[0] as PunchRequestModel;
        return createServerPunchResponse(req, isReplay: true);
      });

      // Attempt 1: Fails with retryable network error
      final result1 = await syncWorker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );
      expect(result1.retryableFailureCount, equals(1));
      expect(result1.syncedCount, equals(0));
      expect(inMemoryQueue['q-net-drop-1']?.syncStatus,
          equals(SyncStatus.pendingSync));
      expect(inMemoryQueue['q-net-drop-1']?.retryCount, equals(1));

      // Attempt 2: Reconnection triggers retry with exact same idempotency key
      final result2 = await syncWorker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );

      expect(result2.syncedCount, equals(1));
      expect(result2.retryableFailureCount, equals(0));
      expect(
          inMemoryQueue['q-net-drop-1']?.syncStatus, equals(SyncStatus.synced));
      expect(inMemoryQueue['q-net-drop-1']?.serverEventId, isNotNull);
    });
  });

  group('Scenario D — Device Revoked While Offline Events Pending', () {
    test(
        'Backend HTTP 403 device revoked causes permanent local rejection, cascades session quarantine, and halts endless retries',
        () async {
      final syncWorker = SyncWorkerImpl(
        localQueueDao: mockDao,
        remoteDataSource: mockRemoteDataSource,
        connectivityService: mockConnectivityService,
      );

      final p1 = createQueueItem(
        localId: 'q-rev-1',
        idempotencyKey: 'idemp-rev-1',
        eventType: AttendanceEventType.checkIn,
        sequenceNumber: 1,
        deviceReportedAt: DateTime.utc(2026, 11, 19, 8, 0, 0),
        sessionId: 'session-revoked-dept',
      );
      final p2 = createQueueItem(
        localId: 'q-rev-2',
        idempotencyKey: 'idemp-rev-2',
        eventType: AttendanceEventType.checkOut,
        sequenceNumber: 2,
        deviceReportedAt: DateTime.utc(2026, 11, 19, 17, 0, 0),
        sessionId: 'session-revoked-dept',
      );

      inMemoryQueue['q-rev-1'] = p1;
      inMemoryQueue['q-rev-2'] = p2;

      // Backend rejects with HTTP 403 device revoked
      when(() => mockRemoteDataSource.recordPunch(any())).thenThrow(
        const ServerException(
          'Device registration has been revoked. Attendance punches are not authorized from this device.',
          statusCode: 403,
        ),
      );

      final result = await syncWorker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );

      // p1 is permanently rejected; p2 is quarantined
      expect(result.permanentlyRejectedCount, equals(1));
      expect(result.quarantinedCount, equals(1));
      expect(result.syncedCount, equals(0));
      expect(result.retryableFailureCount, equals(0));

      expect(inMemoryQueue['q-rev-1']?.syncStatus,
          equals(SyncStatus.rejectedPermanent));
      expect(
        inMemoryQueue['q-rev-1']?.lastErrorMessage,
        contains('Device registration has been revoked'),
      );
      expect(inMemoryQueue['q-rev-2']?.syncStatus,
          equals(SyncStatus.quarantinedDependentFailure));

      // Subsequent sync run does NOT retry either record
      final secondSync = await syncWorker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );
      expect(secondSync.syncedCount, equals(0));
      expect(secondSync.permanentlyRejectedCount, equals(0));
      expect(secondSync.quarantinedCount, equals(0));
    });
  });

  group('Scenario E — Fraud Telemetry Propagation (Mock GPS & Review Flags)',
      () {
    test(
        'Propagates is_mock_location: true and maps server PENDING_REVIEW response to flaggedPendingReview',
        () async {
      final syncWorker = SyncWorkerImpl(
        localQueueDao: mockDao,
        remoteDataSource: mockRemoteDataSource,
        connectivityService: mockConnectivityService,
      );

      final pMock = createQueueItem(
        localId: 'q-mock-1',
        idempotencyKey: 'idemp-mock-gps-1',
        eventType: AttendanceEventType.checkIn,
        sequenceNumber: 1,
        deviceReportedAt: DateTime.utc(2026, 11, 19, 10, 0, 0),
        isMockLocation: true,
        locationCapturedAt: DateTime.utc(2026, 11, 19, 10, 0, 0),
      );
      inMemoryQueue['q-mock-1'] = pMock;

      // Server evaluates mock location and flags for review
      when(() => mockRemoteDataSource.recordPunch(any()))
          .thenAnswer((inv) async {
        final req = inv.positionalArguments[0] as PunchRequestModel;
        dispatchedRequests.add(req);
        return createServerPunchResponse(req, reviewStatus: 'PENDING_REVIEW');
      });

      final result = await syncWorker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );

      expect(result.syncedCount, equals(1));
      expect(dispatchedRequests.first.isMockLocation, isTrue);

      // Status in queue is flaggedPendingReview, preserving forensic integrity
      expect(inMemoryQueue['q-mock-1']?.syncStatus,
          equals(SyncStatus.flaggedPendingReview));
      expect(inMemoryQueue['q-mock-1']?.serverEventId, isNotNull);
    });
  });

  group(
      'Scenario F & H — Server Status Codes & Exponential Backoff Progression',
      () {
    test('Calculates exponential backoff progression accurately up to 60s cap',
        () {
      final syncWorker = SyncWorkerImpl(
        localQueueDao: mockDao,
        remoteDataSource: mockRemoteDataSource,
        connectivityService: mockConnectivityService,
      );

      expect(syncWorker.calculateBackoff(0).inSeconds, equals(2));
      expect(syncWorker.calculateBackoff(1).inSeconds, equals(2));
      expect(syncWorker.calculateBackoff(2).inSeconds, equals(4));
      expect(syncWorker.calculateBackoff(3).inSeconds, equals(8));
      expect(syncWorker.calculateBackoff(4).inSeconds, equals(16));
      expect(syncWorker.calculateBackoff(5).inSeconds, equals(32));
      expect(syncWorker.calculateBackoff(6).inSeconds, equals(60));
      expect(syncWorker.calculateBackoff(10).inSeconds, equals(60));
    });

    test('HTTP 429 rate limit respects server retry_after parameter', () async {
      final syncWorker = SyncWorkerImpl(
        localQueueDao: mockDao,
        remoteDataSource: mockRemoteDataSource,
        connectivityService: mockConnectivityService,
      );

      final p = createQueueItem(
        localId: 'q-rate-1',
        idempotencyKey: 'idemp-rate-1',
        eventType: AttendanceEventType.checkIn,
        sequenceNumber: 1,
        deviceReportedAt: DateTime.utc(2026, 11, 19, 11, 0, 0),
      );
      inMemoryQueue['q-rate-1'] = p;

      when(() => mockRemoteDataSource.recordPunch(any())).thenThrow(
        const ServerException(
          'Too many punch requests',
          statusCode: 429,
          details: {'retry_after': 45},
        ),
      );

      final result = await syncWorker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );

      expect(result.retryableFailureCount, equals(1));
      expect(result.retryAfterSeconds, equals(45));
      expect(inMemoryQueue['q-rate-1']?.syncStatus,
          equals(SyncStatus.pendingSync));
    });

    test('HTTP 422 timestamp expired rejects permanently and does not retry',
        () async {
      final syncWorker = SyncWorkerImpl(
        localQueueDao: mockDao,
        remoteDataSource: mockRemoteDataSource,
        connectivityService: mockConnectivityService,
      );

      final p = createQueueItem(
        localId: 'q-expired-1',
        idempotencyKey: 'idemp-expired-1',
        eventType: AttendanceEventType.checkIn,
        sequenceNumber: 1,
        deviceReportedAt: DateTime.utc(2026, 11, 1, 8, 0, 0),
      );
      inMemoryQueue['q-expired-1'] = p;

      when(() => mockRemoteDataSource.recordPunch(any())).thenThrow(
        const ServerException(
          'Device reported timestamp is older than allowable limit of 7 days.',
          statusCode: 422,
        ),
      );

      final result = await syncWorker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );

      expect(result.permanentlyRejectedCount, equals(1));
      expect(result.retryableFailureCount, equals(0));
      expect(inMemoryQueue['q-expired-1']?.syncStatus,
          equals(SyncStatus.rejectedPermanent));
    });
  });

  group('Scenario G — Dependent Session Quarantine vs Independent Session', () {
    test(
        'Permanent failure in Session 1 quarantines its dependent events but allows independent Session 2 to sync cleanly',
        () async {
      final syncWorker = SyncWorkerImpl(
        localQueueDao: mockDao,
        remoteDataSource: mockRemoteDataSource,
        connectivityService: mockConnectivityService,
      );

      // Session 1: Check-in & Break
      final s1CheckIn = createQueueItem(
        localId: 's1-checkin',
        idempotencyKey: 'idemp-s1-in',
        eventType: AttendanceEventType.checkIn,
        sequenceNumber: 1,
        deviceReportedAt: DateTime.utc(2026, 11, 19, 8, 0, 0),
        sessionId: 'shift-morning',
      );
      final s1Break = createQueueItem(
        localId: 's1-break',
        idempotencyKey: 'idemp-s1-brk',
        eventType: AttendanceEventType.breakStart,
        sequenceNumber: 2,
        deviceReportedAt: DateTime.utc(2026, 11, 19, 12, 0, 0),
        sessionId: 'shift-morning',
      );

      // Session 2 (Independent): Later shift Check-in & Check-out
      final s2CheckIn = createQueueItem(
        localId: 's2-checkin',
        idempotencyKey: 'idemp-s2-in',
        eventType: AttendanceEventType.checkIn,
        sequenceNumber: 3,
        deviceReportedAt: DateTime.utc(2026, 11, 19, 14, 0, 0),
        sessionId: 'shift-evening',
      );
      final s2CheckOut = createQueueItem(
        localId: 's2-checkout',
        idempotencyKey: 'idemp-s2-out',
        eventType: AttendanceEventType.checkOut,
        sequenceNumber: 4,
        deviceReportedAt: DateTime.utc(2026, 11, 19, 20, 0, 0),
        sessionId: 'shift-evening',
      );

      inMemoryQueue['s1-checkin'] = s1CheckIn;
      inMemoryQueue['s1-break'] = s1Break;
      inMemoryQueue['s2-checkin'] = s2CheckIn;
      inMemoryQueue['s2-checkout'] = s2CheckOut;

      when(() => mockRemoteDataSource.recordPunch(any()))
          .thenAnswer((inv) async {
        final req = inv.positionalArguments[0] as PunchRequestModel;
        if (req.idempotencyKey == 'idemp-s1-in') {
          throw const ServerException(
              'Geofence perimeter boundary permanently violated',
              statusCode: 400);
        }
        return createServerPunchResponse(req);
      });

      final result = await syncWorker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );

      // s1CheckIn is permanently rejected; s1Break is quarantined
      expect(result.permanentlyRejectedCount, equals(1));
      expect(result.quarantinedCount, equals(1));

      // s2CheckIn and s2CheckOut in independent session are successfully synced!
      expect(result.syncedCount, equals(2));

      expect(inMemoryQueue['s1-checkin']?.syncStatus,
          equals(SyncStatus.rejectedPermanent));
      expect(inMemoryQueue['s1-break']?.syncStatus,
          equals(SyncStatus.quarantinedDependentFailure));
      expect(
          inMemoryQueue['s2-checkin']?.syncStatus, equals(SyncStatus.synced));
      expect(
          inMemoryQueue['s2-checkout']?.syncStatus, equals(SyncStatus.synced));
    });
  });
}
