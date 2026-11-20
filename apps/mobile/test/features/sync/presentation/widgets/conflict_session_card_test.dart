import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_event.dart';
import 'package:mobile/features/sync/domain/entities/local_queue_item.dart';
import 'package:mobile/features/sync/domain/entities/offline_sequence_conflict_bundle.dart';
import 'package:mobile/features/sync/domain/entities/sync_status.dart';
import 'package:mobile/features/sync/presentation/widgets/conflict_session_card.dart';

void main() {
  const tTenantId = 'tenant-corp-1';
  const tUserId = 'user-emp-1';
  const tSessionId = 'session-uuid-123456';
  const tBundleId = 'bundle-uuid-789';

  final tPrimaryRejected = LocalQueueItem(
    localId: 'loc-1',
    idempotencyKey: 'idemp-1',
    sessionId: tSessionId,
    tenantId: tTenantId,
    employeeId: 'emp-1',
    userId: tUserId,
    eventType: AttendanceEventType.checkIn,
    deviceReportedAt: DateTime.utc(2026, 11, 10, 8, 30),
    timezoneOffsetMinutes: 0,
    monotonicBootTimeMs: 1000,
    bootSessionId: 'boot-1',
    appliedPolicyVersion: 1,
    appliedPolicyMode: 'NONE',
    sequenceNumber: 1,
    syncStatus: SyncStatus.rejectedPermanent,
    conflictBundleId: tBundleId,
    lastErrorMessage: 'Timestamp beyond maximum drift window (422)',
    lastErrorStatusCode: 422,
    createdAt: DateTime.utc(2026, 11, 10, 8, 30),
    updatedAt: DateTime.utc(2026, 11, 10, 8, 30),
  );

  final tDependentQuarantined = LocalQueueItem(
    localId: 'loc-2',
    idempotencyKey: 'idemp-2',
    sessionId: tSessionId,
    tenantId: tTenantId,
    employeeId: 'emp-1',
    userId: tUserId,
    eventType: AttendanceEventType.checkOut,
    deviceReportedAt: DateTime.utc(2026, 11, 10, 17, 30),
    timezoneOffsetMinutes: 0,
    monotonicBootTimeMs: 10000,
    bootSessionId: 'boot-1',
    appliedPolicyVersion: 1,
    appliedPolicyMode: 'NONE',
    sequenceNumber: 2,
    syncStatus: SyncStatus.quarantinedDependentFailure,
    conflictBundleId: tBundleId,
    lastErrorMessage: 'Quarantined due to earlier failure in session',
    createdAt: DateTime.utc(2026, 11, 10, 17, 30),
    updatedAt: DateTime.utc(2026, 11, 10, 17, 30),
  );

  Widget createWidgetUnderTest({
    required OfflineSequenceConflictBundle bundle,
    bool isSubmitting = false,
    bool isConnected = true,
    void Function(String notes)? onSubmit,
    VoidCallback? onRefreshStatus,
  }) {
    return MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: ConflictSessionCard(
            bundle: bundle,
            isSubmitting: isSubmitting,
            isConnected: isConnected,
            onSubmit: onSubmit ?? (_) {},
            onRefreshStatus: onRefreshStatus ?? () {},
          ),
        ),
      ),
    );
  }

  group('ConflictSessionCard Widget Tests', () {
    testWidgets(
        'renders Needs Review badge, primary rejected punch, and dependent event',
        (tester) async {
      final bundle = OfflineSequenceConflictBundle(
        bundleId: tBundleId,
        sessionId: tSessionId,
        tenantId: tTenantId,
        userId: tUserId,
        primaryRejectedEvent: tPrimaryRejected,
        dependentEvents: [tDependentQuarantined],
      );

      await tester.pumpWidget(createWidgetUnderTest(bundle: bundle));

      expect(find.text('Needs Review'), findsOneWidget);
      expect(find.text('2 events in conflict bundle'), findsOneWidget);
      expect(find.text('Primary Rejected Event'), findsOneWidget);
      expect(find.text('Check-In'), findsOneWidget);
      expect(find.textContaining('Timestamp beyond maximum drift window'),
          findsOneWidget);
      expect(find.text('Dependent Quarantined Events (1)'), findsOneWidget);
      expect(find.text('Check-Out'), findsOneWidget);
      expect(find.text('Submit for Supervisor Review'), findsOneWidget);
    });

    testWidgets('submits employee notes on button tap', (tester) async {
      String? submittedNotes;
      final bundle = OfflineSequenceConflictBundle(
        bundleId: tBundleId,
        sessionId: tSessionId,
        tenantId: tTenantId,
        userId: tUserId,
        primaryRejectedEvent: tPrimaryRejected,
      );

      await tester.pumpWidget(createWidgetUnderTest(
        bundle: bundle,
        onSubmit: (notes) => submittedNotes = notes,
      ));

      final inputFinder =
          find.byKey(const Key('conflict_notes_input_$tBundleId'));
      expect(inputFinder, findsOneWidget);

      await tester.enterText(
          inputFinder, 'Supervisor please approve, network was down');
      await tester.pump();

      final buttonFinder = find.byKey(const Key('submit_conflict_$tBundleId'));
      await tester.tap(buttonFinder);
      await tester.pump();

      expect(submittedNotes, 'Supervisor please approve, network was down');
    });

    testWidgets('renders Pending Review state and triggers refresh status',
        (tester) async {
      bool refreshCalled = false;
      final bundle = OfflineSequenceConflictBundle(
        bundleId: tBundleId,
        sessionId: tSessionId,
        tenantId: tTenantId,
        userId: tUserId,
        primaryRejectedEvent: tPrimaryRejected,
        submissionStatus: ConflictSubmissionStatus.pendingReview,
      );

      await tester.pumpWidget(createWidgetUnderTest(
        bundle: bundle,
        onRefreshStatus: () => refreshCalled = true,
      ));

      expect(find.text('Pending Review'), findsOneWidget);
      expect(
          find.textContaining('Awaiting supervisor decision'), findsOneWidget);

      final refreshFinder =
          find.byKey(const Key('refresh_conflict_status_$tBundleId'));
      expect(refreshFinder, findsOneWidget);

      await tester.tap(refreshFinder);
      await tester.pump();

      expect(refreshCalled, true);
    });

    testWidgets('renders Approved state and resolved explanation',
        (tester) async {
      final bundle = OfflineSequenceConflictBundle(
        bundleId: tBundleId,
        sessionId: tSessionId,
        tenantId: tTenantId,
        userId: tUserId,
        primaryRejectedEvent: tPrimaryRejected,
        submissionStatus: ConflictSubmissionStatus.approved,
        supervisorDecision: 'APPROVE',
        supervisorDecisionReason: 'Verified working hours with security desk',
      );

      await tester.pumpWidget(createWidgetUnderTest(bundle: bundle));

      expect(find.text('Approved'), findsOneWidget);
      expect(find.textContaining('Conflict resolved and approved'),
          findsOneWidget);
      expect(find.text('Supervisor Decision: APPROVE'), findsOneWidget);
      expect(find.text('Reason: Verified working hours with security desk'),
          findsOneWidget);
    });

    testWidgets('renders Rejected state and supervisor reason', (tester) async {
      final bundle = OfflineSequenceConflictBundle(
        bundleId: tBundleId,
        sessionId: tSessionId,
        tenantId: tTenantId,
        userId: tUserId,
        primaryRejectedEvent: tPrimaryRejected,
        submissionStatus: ConflictSubmissionStatus.rejected,
        supervisorDecision: 'REJECT',
        supervisorDecisionReason: 'Punch time does not match security log',
      );

      await tester.pumpWidget(createWidgetUnderTest(bundle: bundle));

      expect(find.text('Rejected'), findsOneWidget);
      expect(find.text('Supervisor Decision: REJECT'), findsOneWidget);
      expect(find.text('Reason: Punch time does not match security log'),
          findsOneWidget);
    });
  });
}
