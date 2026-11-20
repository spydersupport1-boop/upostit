import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_event.dart';
import 'package:mobile/features/sync/domain/entities/local_queue_item.dart';
import 'package:mobile/features/sync/domain/entities/sync_status.dart';
import 'package:mobile/features/sync/presentation/widgets/sync_event_tile.dart';

void main() {
  LocalQueueItem createTestItem({
    required AttendanceEventType eventType,
    required SyncStatus syncStatus,
    String? serverEventId,
    String? lastErrorMessage,
    String? conflictBundleId,
  }) {
    return LocalQueueItem(
      localId: 'loc-uuid-1',
      idempotencyKey: 'idemp-uuid-1',
      sessionId: 'session-1',
      tenantId: 'tenant-1',
      employeeId: 'emp-1',
      userId: 'user-1',
      eventType: eventType,
      deviceReportedAt: DateTime.utc(2026, 11, 4, 9, 15),
      timezoneOffsetMinutes: 0,
      monotonicBootTimeMs: 1234567,
      bootSessionId: 'boot-1',
      appliedPolicyVersion: 1,
      appliedPolicyMode: 'NONE',
      sequenceNumber: 1,
      syncStatus: syncStatus,
      serverEventId: serverEventId,
      lastErrorMessage: lastErrorMessage,
      conflictBundleId: conflictBundleId,
      createdAt: DateTime.utc(2026, 11, 4, 9, 15),
      updatedAt: DateTime.utc(2026, 11, 4, 9, 15),
    );
  }

  Widget createWidgetUnderTest(LocalQueueItem item) {
    return MaterialApp(
      home: Scaffold(
        body: Padding(
          padding: const EdgeInsets.all(16.0),
          child: SyncEventTile(item: item),
        ),
      ),
    );
  }

  group('SyncEventTile', () {
    testWidgets('renders CHECK_IN with Pending badge', (tester) async {
      final item = createTestItem(
        eventType: AttendanceEventType.checkIn,
        syncStatus: SyncStatus.pendingSync,
      );

      await tester.pumpWidget(createWidgetUnderTest(item));

      expect(find.text('Check In'), findsOneWidget);
      expect(find.text('Pending'), findsOneWidget);
      expect(find.byIcon(Icons.login_rounded), findsOneWidget);
    });

    testWidgets('renders Synced item with serverEventId confirmation',
        (tester) async {
      final item = createTestItem(
        eventType: AttendanceEventType.checkOut,
        syncStatus: SyncStatus.synced,
        serverEventId: 'srv-event-8899',
      );

      await tester.pumpWidget(createWidgetUnderTest(item));

      expect(find.text('Check Out'), findsOneWidget);
      expect(find.text('Synced'), findsOneWidget);
      expect(find.textContaining('Server ID: srv-event-8899'), findsOneWidget);
      expect(find.byIcon(Icons.check_circle_rounded), findsWidgets);
    });

    testWidgets(
        'renders Permanently Rejected item with sanitized error message',
        (tester) async {
      final item = createTestItem(
        eventType: AttendanceEventType.breakStart,
        syncStatus: SyncStatus.rejectedPermanent,
        lastErrorMessage:
            'Sequence conflict: Must check in before starting break.',
      );

      await tester.pumpWidget(createWidgetUnderTest(item));

      expect(find.text('Start Break'), findsOneWidget);
      expect(find.text('Rejected'), findsOneWidget);
      expect(
          find.textContaining(
              'Rejection Reason: Sequence conflict: Must check in before starting break.'),
          findsOneWidget);
      expect(find.byIcon(Icons.cancel_rounded), findsWidgets);
    });

    testWidgets('renders Quarantined item with notice and no supervisor claim',
        (tester) async {
      final item = createTestItem(
        eventType: AttendanceEventType.checkOut,
        syncStatus: SyncStatus.quarantinedDependentFailure,
        conflictBundleId: 'bundle-xyz-123',
      );

      await tester.pumpWidget(createWidgetUnderTest(item));

      expect(find.text('Check Out'), findsOneWidget);
      expect(find.text('Quarantined'), findsOneWidget);
      expect(
          find.textContaining(
              'Quarantined because an earlier punch in this session failed.'),
          findsOneWidget);
      // Strictly verify no false claim of supervisor submission
      expect(find.textContaining('submitted to supervisor'), findsNothing);
    });

    testWidgets('renders Flagged item with audit warning note', (tester) async {
      final item = createTestItem(
        eventType: AttendanceEventType.checkIn,
        syncStatus: SyncStatus.flaggedPendingReview,
        serverEventId: 'srv-flag-777',
      );

      await tester.pumpWidget(createWidgetUnderTest(item));

      expect(find.text('Flagged'), findsOneWidget);
      expect(
          find.textContaining(
              'Recorded on server, flagged for supervisor review'),
          findsOneWidget);
    });
  });
}
