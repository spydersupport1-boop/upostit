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

  const tTenantId = 'tenant-corp-e2e';
  const tUserId = 'user-emp-e2e';
  const tEmployeeId = 'emp-e2e-001';
  const tSessionId = 'sess-sim-999';
  const tBundleId = 'bundle-sim-888';
  const tDeviceId = 'device-hardware-uuid-1234';

  final tBaseTime = DateTime.utc(2026, 11, 20, 8, 0, 0);

  final tPrimary = LocalQueueItem(
    localId: 'loc-checkin',
    idempotencyKey: 'idemp-p1',
    sessionId: tSessionId,
    tenantId: tTenantId,
    employeeId: tEmployeeId,
    userId: tUserId,
    eventType: AttendanceEventType.checkIn,
    deviceReportedAt: tBaseTime,
    timezoneOffsetMinutes: 0,
    monotonicBootTimeMs: 1000000,
    bootSessionId: 'boot-session-alpha',
    appliedPolicyVersion: 1,
    appliedPolicyMode: 'NONE',
    sequenceNumber: 1,
    syncStatus: SyncStatus.rejectedPermanent,
    conflictBundleId: tBundleId,
    lastErrorMessage:
        'Reported GPS location was outside authorized workplace geofence',
    lastErrorStatusCode: 422,
    createdAt: tBaseTime,
    updatedAt: tBaseTime,
    encryptedPayloadBlob: 'ENCRYPTED_BLOB_loc-checkin',
    latitude: 40.7128,
    longitude: -74.0060,
    accuracyMeters: 12.0,
    deviceId: tDeviceId,
  );

  final tDependentBreakStart = LocalQueueItem(
    localId: 'loc-breakstart',
    idempotencyKey: 'idemp-p2',
    sessionId: tSessionId,
    tenantId: tTenantId,
    employeeId: tEmployeeId,
    userId: tUserId,
    eventType: AttendanceEventType.breakStart,
    deviceReportedAt: tBaseTime.add(const Duration(hours: 4)),
    timezoneOffsetMinutes: 0,
    monotonicBootTimeMs: 1014400,
    bootSessionId: 'boot-session-alpha',
    appliedPolicyVersion: 1,
    appliedPolicyMode: 'NONE',
    sequenceNumber: 2,
    syncStatus: SyncStatus.quarantinedDependentFailure,
    conflictBundleId: tBundleId,
    lastErrorMessage: 'Quarantined due to earlier rejection in session',
    createdAt: tBaseTime.add(const Duration(hours: 4)),
    updatedAt: tBaseTime.add(const Duration(hours: 4)),
    encryptedPayloadBlob: 'ENCRYPTED_BLOB_loc-breakstart',
    latitude: 40.7128,
    longitude: -74.0060,
    accuracyMeters: 10.0,
    deviceId: tDeviceId,
  );

  final tDependentBreakEnd = LocalQueueItem(
    localId: 'loc-breakend',
    idempotencyKey: 'idemp-p3',
    sessionId: tSessionId,
    tenantId: tTenantId,
    employeeId: tEmployeeId,
    userId: tUserId,
    eventType: AttendanceEventType.breakEnd,
    deviceReportedAt: tBaseTime.add(const Duration(hours: 4, minutes: 30)),
    timezoneOffsetMinutes: 0,
    monotonicBootTimeMs: 1016200,
    bootSessionId: 'boot-session-alpha',
    appliedPolicyVersion: 1,
    appliedPolicyMode: 'NONE',
    sequenceNumber: 3,
    syncStatus: SyncStatus.quarantinedDependentFailure,
    conflictBundleId: tBundleId,
    lastErrorMessage: 'Quarantined due to earlier rejection in session',
    createdAt: tBaseTime.add(const Duration(hours: 4, minutes: 30)),
    updatedAt: tBaseTime.add(const Duration(hours: 4, minutes: 30)),
    encryptedPayloadBlob: 'ENCRYPTED_BLOB_loc-breakend',
    latitude: 40.7128,
    longitude: -74.0060,
    accuracyMeters: 10.0,
    deviceId: tDeviceId,
  );

  final tDependentCheckOut = LocalQueueItem(
    localId: 'loc-checkout',
    idempotencyKey: 'idemp-p4',
    sessionId: tSessionId,
    tenantId: tTenantId,
    employeeId: tEmployeeId,
    userId: tUserId,
    eventType: AttendanceEventType.checkOut,
    deviceReportedAt: tBaseTime.add(const Duration(hours: 9)),
    timezoneOffsetMinutes: 0,
    monotonicBootTimeMs: 1032400,
    bootSessionId: 'boot-session-alpha',
    appliedPolicyVersion: 1,
    appliedPolicyMode: 'NONE',
    sequenceNumber: 4,
    syncStatus: SyncStatus.quarantinedDependentFailure,
    conflictBundleId: tBundleId,
    lastErrorMessage: 'Quarantined due to earlier rejection in session',
    createdAt: tBaseTime.add(const Duration(hours: 9)),
    updatedAt: tBaseTime.add(const Duration(hours: 9)),
    encryptedPayloadBlob: 'ENCRYPTED_BLOB_loc-checkout',
    latitude: 40.7128,
    longitude: -74.0060,
    accuracyMeters: 11.2,
    deviceId: tDeviceId,
  );

  final tBundle = OfflineSequenceConflictBundle(
    bundleId: tBundleId,
    sessionId: tSessionId,
    tenantId: tTenantId,
    userId: tUserId,
    primaryRejectedEvent: tPrimary,
    dependentEvents: [
      tDependentBreakStart,
      tDependentBreakEnd,
      tDependentCheckOut,
    ],
    submissionStatus: ConflictSubmissionStatus.notSubmitted,
  );

  const tSummaryInitial = SyncQueueSummary(
    pendingCount: 0,
    syncingCount: 0,
    syncedCount: 0,
    permanentlyRejectedCount: 1,
    quarantinedCount: 3,
    flaggedCount: 0,
  );

  const tSummaryResolved = SyncQueueSummary(
    pendingCount: 0,
    syncingCount: 0,
    syncedCount: 4,
    permanentlyRejectedCount: 0,
    quarantinedCount: 0,
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
        )).thenAnswer((_) async => tSummaryInitial);

    when(() => mockDao.getHistoryEvents(
          tenantId: any(named: 'tenantId'),
          userId: any(named: 'userId'),
          limit: any(named: 'limit'),
        )).thenAnswer((_) async => [
          tPrimary,
          tDependentBreakStart,
          tDependentBreakEnd,
          tDependentCheckOut,
        ]);

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

  group('Phase 8 Milestone 8.6 — Flutter Offline Conflict E2E Journey', () {
    test(
        'Complete Success Lifecycle: Offline Punch -> Permanent 422 Rejection -> Quarantine -> Bundle Extraction -> Submit -> Approve -> Resolution',
        () async {
      const tIncidentId = 'inc-uuid-9999';

      final submitResponse = OfflineConflictIncidentModel(
        id: tIncidentId,
        tenantId: tTenantId,
        employeeId: tEmployeeId,
        userId: tUserId,
        bundleId: tBundleId,
        sessionId: tSessionId,
        status: 'PENDING_REVIEW',
        totalEventsCount: 4,
        rejectionSummary:
            'Reported GPS location was outside authorized workplace geofence',
        employeeNotes: 'Attended client meeting at external site',
        submittedAt: DateTime.now().toUtc(),
      );

      when(() => mockRemoteDataSource.submitConflictBundle(any()))
          .thenAnswer((_) async => submitResponse);

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

      final syncBloc = buildBloc(withConnectivity: true);

      // Step 1: Initialize BLoC with existing queue and conflict bundle
      syncBloc.add(const SyncSummaryRequested(
        tenantId: tTenantId,
        userId: tUserId,
      ));
      await syncBloc.stream.firstWhere((s) => !s.isLoading);

      expect(syncBloc.state.conflictBundles.length, 1);
      expect(syncBloc.state.conflictBundles.first.bundleId, tBundleId);
      expect(syncBloc.state.conflictBundles.first.dependentEvents.length, 3);

      // Step 2: Employee taps Submit on mobile UI
      syncBloc.add(const SyncSubmitConflictBundleRequested(
        bundleId: tBundleId,
        employeeNotes: 'Attended client meeting at external site',
      ));

      await expectLater(
        syncBloc.stream,
        emitsInOrder([
          predicate((s) => (s as dynamic).isSubmittingConflict == true),
          predicate((s) {
            final st = s as dynamic;
            return st.isSubmittingConflict == false &&
                st.conflictActionSuccess != null &&
                st.conflictActionSuccess!.contains('submitted successfully');
          }),
        ]),
      );

      verify(() => mockRemoteDataSource.submitConflictBundle(any())).called(1);
      verify(() => mockDao.saveConflictBundleSubmission(
            bundleId: tBundleId,
            incidentId: tIncidentId,
            status: 'PENDING_REVIEW',
            decision: null,
            decisionReason: null,
            submittedAt: any(named: 'submittedAt'),
            decidedAt: null,
            employeeNotes: 'Attended client meeting at external site',
          )).called(1);

      // Step 3: Supervisor approves incident on Web. Mobile polls /my endpoint
      final approvedIncidentItem = EmployeeConflictIncidentItemModel(
        id: tIncidentId,
        bundleId: tBundleId,
        sessionId: tSessionId,
        status: 'APPROVED',
        totalEventsCount: 4,
        primaryEventType: 'CHECK_IN',
        primaryEventTimestamp: tBaseTime,
        rejectionSummary:
            'Reported GPS location was outside authorized workplace geofence',
        employeeNotes: 'Attended client meeting at external site',
        submittedAt: tBaseTime.add(const Duration(hours: 10)),
        decision: 'APPROVED',
        decisionReason: 'Confirmed physical presence in site facility logs',
        decidedAt: tBaseTime.add(const Duration(hours: 11)),
        resolvedEventsCount: 4,
      );

      when(() => mockRemoteDataSource.getMyConflictIncidents(
              limit: any(named: 'limit')))
          .thenAnswer((_) async => EmployeeConflictIncidentListModel(
                items: [approvedIncidentItem],
                total: 1,
                limit: 50,
              ));

      when(() => mockDao.markConflictBundleResolved(
            bundleId: tBundleId,
            status: SyncStatus.synced,
          )).thenAnswer((_) async {});

      final resolvedBundle = tBundle.copyWith(
        submissionStatus: ConflictSubmissionStatus.approved,
        supervisorDecision: 'APPROVED',
        supervisorDecisionReason:
            'Confirmed physical presence in site facility logs',
      );

      when(() => mockDao.getConflictBundles(
            tenantId: any(named: 'tenantId'),
            userId: any(named: 'userId'),
          )).thenAnswer((_) async => [resolvedBundle]);

      when(() => mockDao.getQueueSummary(
            tenantId: any(named: 'tenantId'),
            userId: any(named: 'userId'),
          )).thenAnswer((_) async => tSummaryResolved);

      // Dispatch status refresh
      syncBloc.add(const SyncRefreshConflictStatusRequested(
        tenantId: tTenantId,
        userId: tUserId,
      ));

      await expectLater(
        syncBloc.stream,
        emitsInOrder([
          predicate((s) {
            final st = s as dynamic;
            return st.conflictActionSuccess != null &&
                st.conflictActionSuccess!.contains('updated from server');
          }),
        ]),
      );

      verify(() => mockDao.markConflictBundleResolved(
            bundleId: tBundleId,
            status: SyncStatus.synced,
          )).called(1);

      expect(syncBloc.state.conflictBundles.first.submissionStatus,
          ConflictSubmissionStatus.approved);
      expect(syncBloc.state.summary.syncedCount, 4);

      await syncBloc.close();
    });

    test(
        'Rejection Lifecycle: Supervisor Rejects Incident -> Local State Preserved with Reason',
        () async {
      const tIncidentId = 'inc-rejected-001';

      final rejectedItem = EmployeeConflictIncidentItemModel(
        id: tIncidentId,
        bundleId: tBundleId,
        sessionId: tSessionId,
        status: 'REJECTED',
        totalEventsCount: 4,
        primaryEventType: 'CHECK_IN',
        primaryEventTimestamp: tBaseTime,
        rejectionSummary: 'Outside geofence radius',
        employeeNotes: 'Attempted remote check-in',
        submittedAt: tBaseTime.add(const Duration(hours: 9)),
        decision: 'REJECTED',
        decisionReason:
            'Vehicle tracker confirms worker was not on duty at designated client facility',
        decidedAt: tBaseTime.add(const Duration(hours: 10)),
        resolvedEventsCount: 0,
      );

      when(() => mockRemoteDataSource.getMyConflictIncidents(
              limit: any(named: 'limit')))
          .thenAnswer((_) async => EmployeeConflictIncidentListModel(
                items: [rejectedItem],
                total: 1,
                limit: 50,
              ));

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

      final rejectedBundle = tBundle.copyWith(
        submissionStatus: ConflictSubmissionStatus.rejected,
        supervisorDecision: 'REJECTED',
        supervisorDecisionReason:
            'Vehicle tracker confirms worker was not on duty at designated client facility',
      );

      when(() => mockDao.getConflictBundles(
            tenantId: any(named: 'tenantId'),
            userId: any(named: 'userId'),
          )).thenAnswer((_) async => [rejectedBundle]);

      final syncBloc = buildBloc(withConnectivity: true);

      syncBloc.add(const SyncSummaryRequested(
        tenantId: tTenantId,
        userId: tUserId,
      ));
      await syncBloc.stream.firstWhere((s) => !s.isLoading);

      syncBloc.add(const SyncRefreshConflictStatusRequested(
        tenantId: tTenantId,
        userId: tUserId,
      ));

      await expectLater(
        syncBloc.stream,
        emitsInOrder([
          predicate((s) {
            final st = s as dynamic;
            return st.conflictActionSuccess != null &&
                st.conflictActionSuccess!.contains('updated from server');
          }),
        ]),
      );

      // Invariants: markConflictBundleResolved must NEVER be called with SyncStatus.synced on rejection!
      verifyNever(() => mockDao.markConflictBundleResolved(
            bundleId: any(named: 'bundleId'),
            status: SyncStatus.synced,
          ));

      // Metadata must record REJECTED decision and reason
      verify(() => mockDao.saveConflictBundleSubmission(
            bundleId: tBundleId,
            incidentId: tIncidentId,
            status: 'REJECTED',
            decision: 'REJECTED',
            decisionReason:
                'Vehicle tracker confirms worker was not on duty at designated client facility',
            submittedAt: any(named: 'submittedAt'),
            decidedAt: any(named: 'decidedAt'),
            employeeNotes: any(named: 'employeeNotes'),
          )).called(1);

      expect(syncBloc.state.conflictBundles.first.submissionStatus,
          ConflictSubmissionStatus.rejected);
      expect(syncBloc.state.conflictBundles.first.supervisorDecisionReason,
          contains('Vehicle tracker confirms worker was not on duty'));

      await syncBloc.close();
    });

    test(
        'Chaos: Network Failure During Submission Surfaces Error and Preserves Bundle for Retry',
        () async {
      when(() => mockRemoteDataSource.submitConflictBundle(any())).thenThrow(
        const NetworkException('Socket connection timeout to api.upostit.com'),
      );

      final syncBloc = buildBloc(withConnectivity: true);

      syncBloc.add(const SyncSummaryRequested(
        tenantId: tTenantId,
        userId: tUserId,
      ));
      await syncBloc.stream.firstWhere((s) => !s.isLoading);

      syncBloc
          .add(const SyncSubmitConflictBundleRequested(bundleId: tBundleId));

      await expectLater(
        syncBloc.stream,
        emitsInOrder([
          predicate((s) => (s as dynamic).isSubmittingConflict == true),
          predicate((s) {
            final st = s as dynamic;
            return st.isSubmittingConflict == false &&
                st.conflictActionError != null &&
                st.conflictActionError!.contains('Socket connection timeout');
          }),
        ]),
      );

      // Bundle remains available in state for subsequent retry
      expect(syncBloc.state.conflictBundles.length, 1);
      expect(syncBloc.state.conflictBundles.first.bundleId, tBundleId);

      await syncBloc.close();
    });

    test('Chaos: Server 409 Conflict Response Handled Without Crashing',
        () async {
      when(() => mockRemoteDataSource.submitConflictBundle(any())).thenThrow(
        const ServerException(
          'Bundle ID reused with mismatched conflict payload.',
          statusCode: 409,
        ),
      );

      final syncBloc = buildBloc(withConnectivity: true);

      syncBloc.add(const SyncSummaryRequested(
        tenantId: tTenantId,
        userId: tUserId,
      ));
      await syncBloc.stream.firstWhere((s) => !s.isLoading);

      syncBloc
          .add(const SyncSubmitConflictBundleRequested(bundleId: tBundleId));

      await expectLater(
        syncBloc.stream,
        emitsInOrder([
          predicate((s) => (s as dynamic).isSubmittingConflict == true),
          predicate((s) {
            final st = s as dynamic;
            return st.isSubmittingConflict == false &&
                st.conflictActionError != null &&
                st.conflictActionError!.contains(
                    'Bundle ID reused with mismatched conflict payload');
          }),
        ]),
      );

      await syncBloc.close();
    });
  });
}
