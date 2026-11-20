import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/errors/app_exception.dart';
import 'package:mobile/features/attendance/data/datasources/attendance_remote_data_source.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_event.dart';
import 'package:mobile/features/sync/data/models/employee_conflict_incident_list_model.dart';
import 'package:mobile/features/sync/data/models/offline_conflict_bundle_submit_request_model.dart';
import 'package:mobile/features/sync/data/models/offline_conflict_incident_model.dart';
import 'package:mobile/features/sync/domain/entities/local_queue_item.dart';
import 'package:mobile/features/sync/domain/entities/offline_sequence_conflict_bundle.dart';
import 'package:mobile/features/sync/domain/entities/sync_queue_summary.dart';
import 'package:mobile/features/sync/domain/entities/sync_result.dart';
import 'package:mobile/features/sync/domain/entities/sync_status.dart';
import 'package:mobile/features/sync/domain/repositories/local_queue_dao.dart';
import 'package:mobile/features/sync/domain/repositories/network_connectivity_service.dart';
import 'package:mobile/features/sync/domain/repositories/sync_worker.dart';
import 'package:mobile/features/sync/presentation/bloc/sync_bloc.dart';
import 'package:mobile/features/sync/presentation/bloc/sync_event.dart';
import 'package:mocktail/mocktail.dart';

class MockLocalQueueDao extends Mock implements LocalQueueDao {}

class MockSyncWorker extends Mock implements SyncWorker {}

class MockNetworkConnectivityService extends Mock
    implements NetworkConnectivityService {}

class MockAttendanceRemoteDataSource extends Mock
    implements AttendanceRemoteDataSource {}

class FakeOfflineConflictBundleSubmitRequestModel extends Fake
    implements OfflineConflictBundleSubmitRequestModel {}

void main() {
  late MockLocalQueueDao mockDao;
  late MockSyncWorker mockWorker;
  late MockNetworkConnectivityService mockConnectivity;
  late MockAttendanceRemoteDataSource mockRemoteDataSource;
  late StreamController<bool> connectivityController;
  late StreamController<SyncResult> syncResultController;

  const tTenantId = 'tenant-corp-1';
  const tUserId = 'user-emp-1';
  const tBundleId = 'bundle-123';
  const tSessionId = 'session-456';

  final tPrimary = LocalQueueItem(
    localId: 'loc-1',
    idempotencyKey: 'idemp-1',
    sessionId: tSessionId,
    tenantId: tTenantId,
    employeeId: 'emp-1',
    userId: tUserId,
    eventType: AttendanceEventType.checkIn,
    deviceReportedAt: DateTime.utc(2026, 11, 10, 8, 0),
    timezoneOffsetMinutes: 0,
    monotonicBootTimeMs: 1000,
    bootSessionId: 'boot-1',
    appliedPolicyVersion: 1,
    appliedPolicyMode: 'NONE',
    sequenceNumber: 1,
    syncStatus: SyncStatus.rejectedPermanent,
    conflictBundleId: tBundleId,
    lastErrorMessage: 'Clock drift exceeded maximum window',
    lastErrorStatusCode: 422,
    createdAt: DateTime.utc(2026, 11, 10, 8, 0),
    updatedAt: DateTime.utc(2026, 11, 10, 8, 0),
  );

  final tDependent = LocalQueueItem(
    localId: 'loc-2',
    idempotencyKey: 'idemp-2',
    sessionId: tSessionId,
    tenantId: tTenantId,
    employeeId: 'emp-1',
    userId: tUserId,
    eventType: AttendanceEventType.checkOut,
    deviceReportedAt: DateTime.utc(2026, 11, 10, 17, 0),
    timezoneOffsetMinutes: 0,
    monotonicBootTimeMs: 10000,
    bootSessionId: 'boot-1',
    appliedPolicyVersion: 1,
    appliedPolicyMode: 'NONE',
    sequenceNumber: 2,
    syncStatus: SyncStatus.quarantinedDependentFailure,
    conflictBundleId: tBundleId,
    lastErrorMessage: 'Quarantined due to earlier failure in session',
    createdAt: DateTime.utc(2026, 11, 10, 17, 0),
    updatedAt: DateTime.utc(2026, 11, 10, 17, 0),
  );

  final tBundle = OfflineSequenceConflictBundle(
    bundleId: tBundleId,
    sessionId: tSessionId,
    tenantId: tTenantId,
    userId: tUserId,
    primaryRejectedEvent: tPrimary,
    dependentEvents: [tDependent],
  );

  const tSummary = SyncQueueSummary(
    pendingCount: 0,
    syncingCount: 0,
    syncedCount: 2,
    permanentlyRejectedCount: 1,
    quarantinedCount: 1,
    flaggedCount: 0,
  );

  setUpAll(() {
    registerFallbackValue(SyncStatus.synced);
    registerFallbackValue(FakeOfflineConflictBundleSubmitRequestModel());
  });

  setUp(() {
    mockDao = MockLocalQueueDao();
    mockWorker = MockSyncWorker();
    mockConnectivity = MockNetworkConnectivityService();
    mockRemoteDataSource = MockAttendanceRemoteDataSource();
    connectivityController = StreamController<bool>.broadcast();
    syncResultController = StreamController<SyncResult>.broadcast();

    when(() => mockConnectivity.isConnected()).thenAnswer((_) async => true);
    when(() => mockConnectivity.onConnectivityRestored)
        .thenAnswer((_) => connectivityController.stream);
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
        )).thenAnswer((_) async => [tPrimary, tDependent]);

    when(() => mockDao.getConflictBundles(
          tenantId: any(named: 'tenantId'),
          userId: any(named: 'userId'),
        )).thenAnswer((_) async => [tBundle]);
  });

  tearDown(() {
    connectivityController.close();
    syncResultController.close();
  });

  SyncBloc buildBloc({bool withConnectivity = false}) {
    return SyncBloc(
      localQueueDao: mockDao,
      syncWorker: mockWorker,
      connectivityService: withConnectivity ? mockConnectivity : null,
      remoteDataSource: mockRemoteDataSource,
    );
  }

  group('SyncBloc Conflict Bundles Integration Tests', () {
    test('loads conflict bundles when SyncSummaryRequested is emitted',
        () async {
      final bloc = buildBloc();

      bloc.add(const SyncSummaryRequested(
        tenantId: tTenantId,
        userId: tUserId,
      ));

      await expectLater(
        bloc.stream,
        emitsInOrder([
          predicate((state) => (state as dynamic).isLoading == true),
          predicate((state) {
            final s = state as dynamic;
            return s.isLoading == false &&
                s.conflictBundles.length == 1 &&
                s.conflictBundles.first.bundleId == tBundleId &&
                s.conflictBundles.first.totalEventsCount == 2;
          }),
        ]),
      );

      verify(() => mockDao.getConflictBundles(
            tenantId: tTenantId,
            userId: tUserId,
          )).called(1);
    });

    test('loads conflict bundles when SyncConflictBundlesRequested is emitted',
        () async {
      final bloc = buildBloc();

      bloc.add(const SyncConflictBundlesRequested(
        tenantId: tTenantId,
        userId: tUserId,
      ));

      await expectLater(
        bloc.stream,
        emitsInOrder([
          predicate((state) {
            final s = state as dynamic;
            return s.conflictBundles.length == 1 &&
                s.conflictBundles.first.bundleId == tBundleId;
          }),
        ]),
      );
    });

    test('submits conflict bundle successfully and stores metadata in DAO',
        () async {
      final tIncidentResponse = OfflineConflictIncidentModel(
        id: 'inc-001',
        tenantId: tTenantId,
        employeeId: 'emp-1',
        userId: tUserId,
        bundleId: tBundleId,
        sessionId: tSessionId,
        status: 'PENDING_REVIEW',
        totalEventsCount: 2,
        rejectionSummary: 'Clock drift error',
        employeeNotes: 'Phone clock corrected',
        submittedAt: DateTime.utc(2026, 11, 10, 9, 0),
      );

      when(() => mockRemoteDataSource.submitConflictBundle(any()))
          .thenAnswer((_) async => tIncidentResponse);

      when(() => mockDao.saveConflictBundleSubmission(
            bundleId: any(named: 'bundleId'),
            incidentId: any(named: 'incidentId'),
            status: any(named: 'status'),
            decision: any(named: 'decision'),
            decisionReason: any(named: 'decisionReason'),
            submittedAt: any(named: 'submittedAt'),
            decidedAt: any(named: 'decidedAt'),
            employeeNotes: any(named: 'employeeNotes'),
          )).thenAnswer((_) async {});

      final bloc = buildBloc();

      // First populate summary and active session
      bloc.add(const SyncSummaryRequested(
        tenantId: tTenantId,
        userId: tUserId,
      ));
      await bloc.stream.firstWhere((s) => !s.isLoading);

      // Now submit conflict bundle
      bloc.add(const SyncSubmitConflictBundleRequested(
        bundleId: tBundleId,
        employeeNotes: 'Phone clock corrected',
      ));

      await expectLater(
        bloc.stream,
        emitsInOrder([
          predicate((s) =>
              (s as dynamic).isSubmittingConflict == true &&
              s.submittingBundleId == tBundleId),
          predicate((s) {
            final st = s as dynamic;
            return st.isSubmittingConflict == false &&
                st.submittingBundleId == null &&
                st.conflictActionSuccess != null &&
                st.conflictActionSuccess!.contains('submitted');
          }),
        ]),
      );

      verify(() => mockRemoteDataSource.submitConflictBundle(any())).called(1);
      verify(() => mockDao.saveConflictBundleSubmission(
            bundleId: tBundleId,
            incidentId: 'inc-001',
            status: 'PENDING_REVIEW',
            decision: null,
            decisionReason: null,
            submittedAt: any(named: 'submittedAt'),
            decidedAt: null,
            employeeNotes: 'Phone clock corrected',
          )).called(1);
    });

    test(
        'marks local items resolved if submission response is already APPROVED',
        () async {
      final tApprovedResponse = OfflineConflictIncidentModel(
        id: 'inc-002',
        tenantId: tTenantId,
        employeeId: 'emp-1',
        userId: tUserId,
        bundleId: tBundleId,
        sessionId: tSessionId,
        status: 'APPROVED',
        totalEventsCount: 2,
        decision: 'APPROVE',
        decisionReason: 'Pre-approved exception',
        submittedAt: DateTime.utc(2026, 11, 10, 9, 0),
        decidedAt: DateTime.utc(2026, 11, 10, 9, 5),
      );

      when(() => mockRemoteDataSource.submitConflictBundle(any()))
          .thenAnswer((_) async => tApprovedResponse);

      when(() => mockDao.saveConflictBundleSubmission(
            bundleId: any(named: 'bundleId'),
            incidentId: any(named: 'incidentId'),
            status: any(named: 'status'),
            decision: any(named: 'decision'),
            decisionReason: any(named: 'decisionReason'),
            submittedAt: any(named: 'submittedAt'),
            decidedAt: any(named: 'decidedAt'),
            employeeNotes: any(named: 'employeeNotes'),
          )).thenAnswer((_) async {});

      when(() => mockDao.markConflictBundleResolved(
            bundleId: any(named: 'bundleId'),
            status: any(named: 'status'),
          )).thenAnswer((_) async {});

      final bloc = buildBloc();
      bloc.add(
          const SyncSummaryRequested(tenantId: tTenantId, userId: tUserId));
      await bloc.stream.firstWhere((s) => !s.isLoading);

      bloc.add(const SyncSubmitConflictBundleRequested(bundleId: tBundleId));

      await expectLater(
        bloc.stream,
        emitsInOrder([
          predicate((s) => (s as dynamic).isSubmittingConflict == true),
          predicate((s) => (s as dynamic).isSubmittingConflict == false),
        ]),
      );

      verify(() => mockDao.markConflictBundleResolved(
            bundleId: tBundleId,
            status: SyncStatus.synced,
          )).called(1);
    });

    test('handles 409 ServerException gracefully without throwing', () async {
      when(() => mockRemoteDataSource.submitConflictBundle(any()))
          .thenThrow(const ServerException(
        'Conflict bundle bundle-123 is already under supervisor review.',
        statusCode: 409,
      ));

      final bloc = buildBloc();
      bloc.add(
          const SyncSummaryRequested(tenantId: tTenantId, userId: tUserId));
      await bloc.stream.firstWhere((s) => !s.isLoading);

      bloc.add(const SyncSubmitConflictBundleRequested(bundleId: tBundleId));

      await expectLater(
        bloc.stream,
        emitsInOrder([
          predicate((s) => (s as dynamic).isSubmittingConflict == true),
          predicate((s) {
            final st = s as dynamic;
            return st.isSubmittingConflict == false &&
                st.conflictActionError != null &&
                st.conflictActionError!
                    .contains('already under supervisor review');
          }),
        ]),
      );
    });

    test('refreshes conflict statuses from GET /offline-conflicts/my',
        () async {
      final tListModel = EmployeeConflictIncidentListModel(
        items: [
          EmployeeConflictIncidentItemModel(
            id: 'inc-003',
            bundleId: tBundleId,
            sessionId: tSessionId,
            status: 'APPROVED',
            totalEventsCount: 2,
            primaryEventType: 'CHECK_IN',
            primaryEventTimestamp: DateTime.utc(2026, 11, 10, 8, 0),
            submittedAt: DateTime.utc(2026, 11, 10, 9, 0),
            decision: 'APPROVE',
            decisionReason: 'Verified by manager',
            decidedAt: DateTime.utc(2026, 11, 10, 10, 0),
            resolvedEventsCount: 2,
          )
        ],
        total: 1,
        limit: 50,
      );

      when(() => mockRemoteDataSource.getMyConflictIncidents(
          limit: any(named: 'limit'))).thenAnswer((_) async => tListModel);

      when(() => mockDao.saveConflictBundleSubmission(
            bundleId: any(named: 'bundleId'),
            incidentId: any(named: 'incidentId'),
            status: any(named: 'status'),
            decision: any(named: 'decision'),
            decisionReason: any(named: 'decisionReason'),
            submittedAt: any(named: 'submittedAt'),
            decidedAt: any(named: 'decidedAt'),
            employeeNotes: any(named: 'employeeNotes'),
          )).thenAnswer((_) async {});

      when(() => mockDao.markConflictBundleResolved(
            bundleId: any(named: 'bundleId'),
            status: any(named: 'status'),
          )).thenAnswer((_) async {});

      final bloc = buildBloc();
      bloc.add(
          const SyncSummaryRequested(tenantId: tTenantId, userId: tUserId));
      await bloc.stream.firstWhere((s) => !s.isLoading);

      bloc.add(const SyncRefreshConflictStatusRequested(
        tenantId: tTenantId,
        userId: tUserId,
      ));

      await expectLater(
        bloc.stream,
        emitsInOrder([
          predicate((s) {
            final st = s as dynamic;
            return st.conflictActionSuccess != null &&
                st.conflictActionSuccess!.contains('updated from server');
          }),
        ]),
      );

      verify(() => mockDao.saveConflictBundleSubmission(
            bundleId: tBundleId,
            incidentId: 'inc-003',
            status: 'APPROVED',
            decision: 'APPROVE',
            decisionReason: 'Verified by manager',
            submittedAt: any(named: 'submittedAt'),
            decidedAt: any(named: 'decidedAt'),
            employeeNotes: null,
          )).called(1);

      verify(() => mockDao.markConflictBundleResolved(
            bundleId: tBundleId,
            status: SyncStatus.synced,
          )).called(1);
    });
  });
}
