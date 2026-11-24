import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workmanager/workmanager.dart';

import 'package:mobile/core/errors/app_exception.dart';
import 'package:mobile/features/attendance/data/datasources/attendance_remote_data_source.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_event.dart';
import 'package:mobile/features/sync/data/datasources/downward_sync_dao.dart';
import 'package:mobile/features/sync/data/datasources/downward_sync_remote_data_source.dart';
import 'package:mobile/features/sync/data/models/batch_sync_models.dart';
import 'package:mobile/features/sync/data/models/sync_delta_model.dart';
import 'package:mobile/features/sync/data/services/background_sync_scheduler.dart';
import 'package:mobile/features/sync/data/services/downward_sync_coordinator.dart';
import 'package:mobile/features/sync/data/services/sync_worker_impl.dart';
import 'package:mobile/features/sync/data/services/unified_sync_coordinator.dart';
import 'package:mobile/features/sync/domain/entities/local_queue_item.dart';
import 'package:mobile/features/sync/domain/entities/sync_status.dart';
import 'package:mobile/features/sync/domain/repositories/local_queue_dao.dart';
import 'package:mobile/features/sync/domain/repositories/network_connectivity_service.dart';

class MockLocalQueueDao extends Mock implements LocalQueueDao {}

class MockDownwardSyncDao extends Mock implements DownwardSyncDao {}

class MockAttendanceRemoteDataSource extends Mock
    implements AttendanceRemoteDataSource {}

class MockDownwardSyncRemoteDataSource extends Mock
    implements DownwardSyncRemoteDataSource {}

class MockNetworkConnectivityService extends Mock
    implements NetworkConnectivityService {}

class MockDownwardSyncCoordinator extends Mock
    implements DownwardSyncCoordinator {}

class MockWorkmanager extends Mock implements Workmanager {}

class FakeAttendanceBatchSyncRequestModel extends Fake
    implements AttendanceBatchSyncRequestModel {}

class FakeConstraints extends Fake implements Constraints {}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() {
    sqfliteFfiInit();
    registerFallbackValue(FakeAttendanceBatchSyncRequestModel());
    registerFallbackValue(SyncStatus.pendingSync);
    registerFallbackValue(const Duration(seconds: 120));
    registerFallbackValue(ExistingPeriodicWorkPolicy.keep);
    registerFallbackValue(BackoffPolicy.exponential);
    registerFallbackValue(FakeConstraints());
    registerFallbackValue(const SyncDeltaModel(
      syncType: 'FULL',
      serverTime: '2026-11-24T12:00:00Z',
      nextCursor: 'cur_test',
      hasMore: false,
    ));
  });

  const tTenantId = 'tenant-e2e-11-7';
  const tUserId = 'user-e2e-11-7';
  const tEmployeeId = 'emp-e2e-11-7';

  LocalQueueItem makeQueueItem({
    required String localId,
    required String idempotencyKey,
    required int sequenceNumber,
    AttendanceEventType eventType = AttendanceEventType.checkIn,
    String sessionId = 'session-e2e-1',
    SyncStatus status = SyncStatus.pendingSync,
    int retryCount = 0,
  }) {
    final now = DateTime.utc(2026, 11, 24, 8, 0, 0);
    return LocalQueueItem(
      localId: localId,
      idempotencyKey: idempotencyKey,
      sessionId: sessionId,
      tenantId: tTenantId,
      employeeId: tEmployeeId,
      userId: tUserId,
      eventType: eventType,
      deviceReportedAt: now.add(Duration(hours: sequenceNumber - 1)),
      timezoneOffsetMinutes: 0,
      monotonicBootTimeMs: 1000000 + sequenceNumber * 1000,
      bootSessionId: 'boot-session-e2e',
      isRebootDetected: false,
      sequenceNumber: sequenceNumber,
      syncStatus: status,
      retryCount: retryCount,
      appliedPolicyVersion: 1,
      appliedPolicyMode: 'STRICT',
      metadataJson: '{}',
      createdAt: now,
      updatedAt: now,
    );
  }

  group('Phase 11.7 Mobile — End-to-End Sync & Chaos Verification', () {
    late MockLocalQueueDao mockDao;
    late MockAttendanceRemoteDataSource mockRemoteDataSource;
    late MockNetworkConnectivityService mockConnectivityService;
    late MockDownwardSyncDao mockDownwardDao;
    late MockDownwardSyncCoordinator mockDownwardCoord;
    late SyncWorkerImpl syncWorker;
    late UnifiedSyncCoordinator unifiedCoord;
    final Map<String, LocalQueueItem> inMemoryQueue = {};

    setUp(() {
      mockDao = MockLocalQueueDao();
      mockRemoteDataSource = MockAttendanceRemoteDataSource();
      mockConnectivityService = MockNetworkConnectivityService();
      mockDownwardDao = MockDownwardSyncDao();
      mockDownwardCoord = MockDownwardSyncCoordinator();
      inMemoryQueue.clear();

      when(() => mockConnectivityService.isConnected())
          .thenAnswer((_) async => true);
      when(() => mockConnectivityService.onConnectivityRestored)
          .thenAnswer((_) => const Stream.empty());
      when(() => mockDao.resetZombieSyncingItems(
            timeout: any(named: 'timeout'),
          )).thenAnswer((_) async => 0);
      when(() => mockDao.getPendingCount(
            tenantId: any(named: 'tenantId'),
            userId: any(named: 'userId'),
          )).thenAnswer((_) async => inMemoryQueue.values
          .where((i) => i.syncStatus == SyncStatus.pendingSync)
          .length);

      when(() => mockDao.getEventById(any())).thenAnswer((inv) async {
        final id = inv.positionalArguments.first as String;
        return inMemoryQueue[id];
      });

      when(() => mockDao.getPendingEventsFifo(
            tenantId: any(named: 'tenantId'),
            userId: any(named: 'userId'),
            limit: any(named: 'limit'),
          )).thenAnswer((_) async {
        return inMemoryQueue.values
            .where((i) => i.syncStatus == SyncStatus.pendingSync)
            .toList()
          ..sort((a, b) => a.sequenceNumber.compareTo(b.sequenceNumber));
      });

      when(() => mockDao.updateSyncStatus(
            localId: any(named: 'localId'),
            status: any(named: 'status'),
            serverEventId: any(named: 'serverEventId'),
            errorMessage: any(named: 'errorMessage'),
            statusCode: any(named: 'statusCode'),
          )).thenAnswer((inv) async {
        final localId = inv.namedArguments[#localId] as String;
        final status = inv.namedArguments[#status] as SyncStatus;
        final old = inMemoryQueue[localId];
        if (old != null) {
          inMemoryQueue[localId] = old.copyWith(
            syncStatus: status,
            serverEventId: inv.namedArguments[#serverEventId] as String?,
            lastErrorMessage: inv.namedArguments[#errorMessage] as String?,
            lastErrorStatusCode: inv.namedArguments[#statusCode] as int?,
            retryCount: status == SyncStatus.pendingSync
                ? old.retryCount + 1
                : old.retryCount,
          );
        }
      });

      when(() => mockDao.markPermanentlyRejected(
            localId: any(named: 'localId'),
            errorMessage: any(named: 'errorMessage'),
            statusCode: any(named: 'statusCode'),
          )).thenAnswer((inv) async {
        final localId = inv.namedArguments[#localId] as String;
        final old = inMemoryQueue[localId];
        if (old != null) {
          inMemoryQueue[localId] = old.copyWith(
            syncStatus: SyncStatus.rejectedPermanent,
            lastErrorMessage: inv.namedArguments[#errorMessage] as String?,
            lastErrorStatusCode: inv.namedArguments[#statusCode] as int?,
          );
        }
      });

      when(() => mockDao.quarantineDependentEvents(
            tenantId: any(named: 'tenantId'),
            userId: any(named: 'userId'),
            conflictBundleId: any(named: 'conflictBundleId'),
            fromLocalId: any(named: 'fromLocalId'),
          )).thenAnswer((inv) async => 0);

      syncWorker = SyncWorkerImpl(
        localQueueDao: mockDao,
        remoteDataSource: mockRemoteDataSource,
        connectivityService: mockConnectivityService,
      );

      unifiedCoord = UnifiedSyncCoordinator(
        syncWorker: syncWorker,
        downwardCoordinator: mockDownwardCoord,
        localQueueDao: mockDao,
        downwardDao: mockDownwardDao,
        connectivityService: mockConnectivityService,
      );
    });

    tearDown(() {
      unifiedCoord.dispose();
      syncWorker.dispose();
    });

    test('Scenario 1: Complete offline workday punches upload on reconnect',
        () async {
      final p1 = makeQueueItem(
          localId: 'q-1',
          idempotencyKey: 'idemp-1-uuid',
          sequenceNumber: 1,
          eventType: AttendanceEventType.checkIn);
      final p2 = makeQueueItem(
          localId: 'q-2',
          idempotencyKey: 'idemp-2-uuid',
          sequenceNumber: 2,
          eventType: AttendanceEventType.breakStart);
      final p3 = makeQueueItem(
          localId: 'q-3',
          idempotencyKey: 'idemp-3-uuid',
          sequenceNumber: 3,
          eventType: AttendanceEventType.breakEnd);
      final p4 = makeQueueItem(
          localId: 'q-4',
          idempotencyKey: 'idemp-4-uuid',
          sequenceNumber: 4,
          eventType: AttendanceEventType.checkOut);

      inMemoryQueue['q-1'] = p1;
      inMemoryQueue['q-2'] = p2;
      inMemoryQueue['q-3'] = p3;
      inMemoryQueue['q-4'] = p4;

      when(() => mockRemoteDataSource.syncBatch(any()))
          .thenAnswer((_) async => const AttendanceBatchSyncResponseModel(
                totalItems: 4,
                acceptedCount: 4,
                duplicateCount: 0,
                requiresReviewCount: 0,
                rejectedCount: 0,
                retryableCount: 0,
                receipts: [
                  BatchSyncReceiptItemModel(
                    localId: 'q-1',
                    idempotencyKey: 'idemp-1-uuid',
                    status: 'ACCEPTED',
                    eventType: 'CHECK_IN',
                    serverEventId: 'evt-1',
                  ),
                  BatchSyncReceiptItemModel(
                    localId: 'q-2',
                    idempotencyKey: 'idemp-2-uuid',
                    status: 'ACCEPTED',
                    eventType: 'BREAK_START',
                    serverEventId: 'evt-2',
                  ),
                  BatchSyncReceiptItemModel(
                    localId: 'q-3',
                    idempotencyKey: 'idemp-3-uuid',
                    status: 'ACCEPTED',
                    eventType: 'BREAK_END',
                    serverEventId: 'evt-3',
                  ),
                  BatchSyncReceiptItemModel(
                    localId: 'q-4',
                    idempotencyKey: 'idemp-4-uuid',
                    status: 'ACCEPTED',
                    eventType: 'CHECK_OUT',
                    serverEventId: 'evt-4',
                  ),
                ],
              ));

      final result = await syncWorker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
        useBatch: true,
      );

      expect(result.syncedCount, equals(4));
      expect(result.retryableFailureCount, equals(0));
      expect(result.permanentlyRejectedCount, equals(0));
      expect(inMemoryQueue['q-1']!.syncStatus, equals(SyncStatus.synced));
      expect(inMemoryQueue['q-2']!.syncStatus, equals(SyncStatus.synced));
      expect(inMemoryQueue['q-3']!.syncStatus, equals(SyncStatus.synced));
      expect(inMemoryQueue['q-4']!.syncStatus, equals(SyncStatus.synced));
    });

    test('Scenario 2: Network drop or 503 triggers retry and backoff',
        () async {
      final p1 = makeQueueItem(
          localId: 'q-err-1',
          idempotencyKey: 'idemp-err-1',
          sequenceNumber: 1);
      inMemoryQueue['q-err-1'] = p1;

      when(() => mockRemoteDataSource.syncBatch(any())).thenThrow(
        const ServerException(
          'Backend service unavailable (503)',
          statusCode: 503,
        ),
      );

      final result = await syncWorker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
        useBatch: true,
      );

      expect(result.hasErrors, isTrue);
      expect(result.retryableFailureCount, equals(1));
      expect(result.errorMessage, contains('503'));
      // Item remained in queue and retry count was incremented
      expect(inMemoryQueue['q-err-1']!.syncStatus, equals(SyncStatus.pendingSync));
      expect(inMemoryQueue['q-err-1']!.retryCount, greaterThanOrEqualTo(1));
    });

    test('Scenario 3: Duplicate punch receipt is reconciled cleanly', () async {
      final p1 = makeQueueItem(
          localId: 'q-dup-1',
          idempotencyKey: 'idemp-dup-1',
          sequenceNumber: 1);
      inMemoryQueue['q-dup-1'] = p1;

      when(() => mockRemoteDataSource.syncBatch(any()))
          .thenAnswer((_) async => const AttendanceBatchSyncResponseModel(
                totalItems: 1,
                acceptedCount: 0,
                duplicateCount: 1,
                requiresReviewCount: 0,
                rejectedCount: 0,
                retryableCount: 0,
                receipts: [
                  BatchSyncReceiptItemModel(
                    localId: 'q-dup-1',
                    idempotencyKey: 'idemp-dup-1',
                    status: 'DUPLICATE',
                    eventType: 'CHECK_IN',
                    serverEventId: 'evt-dup-server-1',
                    idempotentReplay: true,
                  ),
                ],
              ));

      final result = await syncWorker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
        useBatch: true,
      );

      expect(result.syncedCount, equals(1));
      expect(inMemoryQueue['q-dup-1']!.syncStatus, equals(SyncStatus.synced));
      expect(inMemoryQueue['q-dup-1']!.serverEventId, equals('evt-dup-server-1'));
    });

    test('Scenario 4: BackgroundSyncScheduler registers periodic task correctly',
        () async {
      final mockWm = MockWorkmanager();
      when(() => mockWm.registerPeriodicTask(
            any(),
            any(),
            frequency: any(named: 'frequency'),
            existingWorkPolicy: any(named: 'existingWorkPolicy'),
            backoffPolicy: any(named: 'backoffPolicy'),
            backoffPolicyDelay: any(named: 'backoffPolicyDelay'),
            constraints: any(named: 'constraints'),
            inputData: any(named: 'inputData'),
          )).thenAnswer((_) async {});
      when(() => mockWm.cancelByUniqueName(any())).thenAnswer((_) async {});

      final scheduler = DefaultBackgroundSyncScheduler(
        unifiedCoordinator: unifiedCoord,
        connectivityService: mockConnectivityService,
        workmanager: mockWm,
      );

      await scheduler.schedulePeriodicSync(
        tenantId: tTenantId,
        userId: tUserId,
        interval: const Duration(minutes: 15),
      );

      verify(() => mockWm.registerPeriodicTask(
            kBackgroundSyncPeriodicUniqueName,
            kBackgroundSyncPeriodicTask,
            frequency: const Duration(minutes: 15),
            existingWorkPolicy: ExistingPeriodicWorkPolicy.keep,
            backoffPolicy: BackoffPolicy.exponential,
            backoffPolicyDelay: const Duration(seconds: 30),
            constraints: any(named: 'constraints'),
            inputData: any(named: 'inputData'),
          )).called(1);

      await scheduler.cancelPeriodicSync();
      verify(() => mockWm.cancelByUniqueName(kBackgroundSyncPeriodicUniqueName))
          .called(1);

      scheduler.dispose();
    });
  });
}
