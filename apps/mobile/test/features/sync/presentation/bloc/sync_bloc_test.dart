import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_event.dart';
import 'package:mobile/features/sync/domain/entities/local_queue_item.dart';
import 'package:mobile/features/sync/domain/entities/sync_queue_summary.dart';
import 'package:mobile/features/sync/domain/entities/sync_result.dart';
import 'package:mobile/features/sync/domain/entities/sync_status.dart';
import 'package:mobile/features/sync/domain/repositories/local_queue_dao.dart';
import 'package:mobile/features/sync/domain/repositories/network_connectivity_service.dart';
import 'package:mobile/features/sync/domain/repositories/sync_worker.dart';
import 'package:mobile/features/sync/presentation/bloc/sync_bloc.dart';
import 'package:mobile/features/sync/presentation/bloc/sync_event.dart';
import 'package:mobile/features/sync/presentation/bloc/sync_state.dart';
import 'package:mocktail/mocktail.dart';

class MockLocalQueueDao extends Mock implements LocalQueueDao {}

class MockSyncWorker extends Mock implements SyncWorker {}

class MockNetworkConnectivityService extends Mock
    implements NetworkConnectivityService {}

void main() {
  late MockLocalQueueDao mockDao;
  late MockSyncWorker mockWorker;
  late MockNetworkConnectivityService mockConnectivity;
  late StreamController<bool> connectivityRestoredController;
  late StreamController<SyncResult> syncResultController;

  const tTenantId = 'tenant-123';
  const tUserId = 'user-456';

  final tQueueItem = LocalQueueItem(
    localId: 'local-1',
    idempotencyKey: 'idemp-1',
    sessionId: 'session-1',
    tenantId: tTenantId,
    employeeId: 'emp-1',
    userId: tUserId,
    eventType: AttendanceEventType.checkIn,
    deviceReportedAt: DateTime.utc(2026, 11, 4, 8, 30),
    timezoneOffsetMinutes: 0,
    monotonicBootTimeMs: 1234567,
    bootSessionId: 'boot-1',
    appliedPolicyVersion: 1,
    appliedPolicyMode: 'NONE',
    sequenceNumber: 1,
    syncStatus: SyncStatus.pendingSync,
    createdAt: DateTime.utc(2026, 11, 4, 8, 30),
    updatedAt: DateTime.utc(2026, 11, 4, 8, 30),
  );

  const tSummary = SyncQueueSummary(
    pendingCount: 2,
    syncingCount: 0,
    syncedCount: 5,
    permanentlyRejectedCount: 1,
    quarantinedCount: 0,
    flaggedCount: 0,
    lastSyncedAt: null,
  );

  setUp(() {
    mockDao = MockLocalQueueDao();
    mockWorker = MockSyncWorker();
    mockConnectivity = MockNetworkConnectivityService();
    connectivityRestoredController = StreamController<bool>.broadcast();
    syncResultController = StreamController<SyncResult>.broadcast();

    when(() => mockConnectivity.isConnected()).thenAnswer((_) async => true);
    when(() => mockConnectivity.onConnectivityRestored)
        .thenAnswer((_) => connectivityRestoredController.stream);
    when(() => mockWorker.syncResults)
        .thenAnswer((_) => syncResultController.stream);
    when(() => mockWorker.isSyncing(any(), any())).thenReturn(false);

    when(() => mockDao.getQueueSummary(
          tenantId: any(named: 'tenantId'),
          userId: any(named: 'userId'),
        )).thenAnswer((_) async => tSummary);

    when(() => mockDao.getHistoryEvents(
          tenantId: any(named: 'tenantId'),
          userId: any(named: 'userId'),
          limit: any(named: 'limit'),
        )).thenAnswer((_) async => [tQueueItem]);
  });

  tearDown(() {
    connectivityRestoredController.close();
    syncResultController.close();
  });

  group('SyncBloc', () {
    test('initial state has default metrics and isConnected true', () async {
      final bloc = SyncBloc(
        localQueueDao: mockDao,
        syncWorker: mockWorker,
        connectivityService: mockConnectivity,
      );

      expect(bloc.state.isLoading, isFalse);
      expect(bloc.state.isSyncing, isFalse);
      await bloc.close();
    });

    test('SyncSummaryRequested loads summary metrics and history events',
        () async {
      final bloc = SyncBloc(
        localQueueDao: mockDao,
        syncWorker: mockWorker,
        connectivityService: mockConnectivity,
      );

      bloc.add(const SyncSummaryRequested(
        tenantId: tTenantId,
        userId: tUserId,
      ));

      await expectLater(
        bloc.stream,
        emitsInOrder([
          predicate<SyncState>((s) => s.isLoading == true),
          predicate<SyncState>((s) =>
              s.isLoading == false &&
              s.pendingCount == 2 &&
              s.syncedCount == 5 &&
              s.unresolvedCount == 2 &&
              s.events.length == 1),
        ]),
      );

      await bloc.close();
    });

    test(
        'SyncNowRequested executes syncWorker and refreshes summary upon success',
        () async {
      when(() => mockWorker.synchronizeQueue(
            tenantId: tTenantId,
            userId: tUserId,
          )).thenAnswer((_) async => const SyncResult(
            syncedCount: 2,
            permanentlyRejectedCount: 0,
            quarantinedCount: 0,
            retryableFailureCount: 0,
            isCompleted: true,
          ));

      final bloc = SyncBloc(
        localQueueDao: mockDao,
        syncWorker: mockWorker,
        connectivityService: mockConnectivity,
      );

      bloc.add(const SyncNowRequested(
        tenantId: tTenantId,
        userId: tUserId,
      ));

      await expectLater(
        bloc.stream,
        emitsThrough(
          predicate<SyncState>((s) =>
              s.isSyncing == false &&
              s.isLoading == false &&
              s.successMessage != null),
        ),
      );

      verify(() => mockWorker.synchronizeQueue(
            tenantId: tTenantId,
            userId: tUserId,
          )).called(1);

      await bloc.close();
    });

    test('SyncNowRequested rejects execution when offline', () async {
      when(() => mockConnectivity.isConnected()).thenAnswer((_) async => false);

      final bloc = SyncBloc(
        localQueueDao: mockDao,
        syncWorker: mockWorker,
        connectivityService: mockConnectivity,
      );

      bloc.add(const SyncNowRequested(
        tenantId: tTenantId,
        userId: tUserId,
      ));

      await expectLater(
        bloc.stream,
        emits(predicate<SyncState>((s) =>
            s.isConnected == false &&
            s.errorMessage == 'Cannot synchronize: No internet connection.')),
      );

      verifyNever(() => mockWorker.synchronizeQueue(
            tenantId: any(named: 'tenantId'),
            userId: any(named: 'userId'),
          ));

      await bloc.close();
    });

    test('SyncNowRequested is mutex protected and does not run concurrently',
        () async {
      final completer = Completer<SyncResult>();
      when(() => mockWorker.synchronizeQueue(
            tenantId: tTenantId,
            userId: tUserId,
          )).thenAnswer((_) => completer.future);

      final bloc = SyncBloc(
        localQueueDao: mockDao,
        syncWorker: mockWorker,
        connectivityService: mockConnectivity,
      );

      // Trigger first sync
      bloc.add(const SyncNowRequested(
        tenantId: tTenantId,
        userId: tUserId,
      ));

      // Immediate second trigger while in-flight
      bloc.add(const SyncNowRequested(
        tenantId: tTenantId,
        userId: tUserId,
      ));

      // Resolve first sync
      completer.complete(const SyncResult(
        syncedCount: 1,
        permanentlyRejectedCount: 0,
        quarantinedCount: 0,
        retryableFailureCount: 0,
        isCompleted: true,
      ));

      // Worker should have been called only once
      await Future<void>.delayed(const Duration(milliseconds: 50));
      verify(() => mockWorker.synchronizeQueue(
            tenantId: tTenantId,
            userId: tUserId,
          )).called(1);

      await bloc.close();
    });

    test(
        'SyncConnectivityChanged updates isConnected and triggers sync if connected',
        () async {
      when(() => mockWorker.synchronizeQueue(
            tenantId: tTenantId,
            userId: tUserId,
          )).thenAnswer((_) async => const SyncResult(
            syncedCount: 1,
            permanentlyRejectedCount: 0,
            quarantinedCount: 0,
            retryableFailureCount: 0,
            isCompleted: true,
          ));

      final bloc = SyncBloc(
        localQueueDao: mockDao,
        syncWorker: mockWorker,
        connectivityService: mockConnectivity,
      );

      // Seed active user
      bloc.add(
          const SyncSummaryRequested(tenantId: tTenantId, userId: tUserId));
      await Future<void>.delayed(const Duration(milliseconds: 50));

      // Connectivity goes down then comes up
      bloc.add(const SyncConnectivityChanged(isConnected: false));
      await Future<void>.delayed(const Duration(milliseconds: 20));
      expect(bloc.state.isConnected, isFalse);

      bloc.add(const SyncConnectivityChanged(isConnected: true));
      await Future<void>.delayed(const Duration(milliseconds: 50));
      expect(bloc.state.isConnected, isTrue);

      await bloc.close();
    });
  });
}
