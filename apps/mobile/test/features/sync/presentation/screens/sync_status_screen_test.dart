import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_event.dart';
import 'package:mobile/features/auth/domain/entities/user_profile.dart';
import 'package:mobile/features/auth/presentation/bloc/auth_bloc.dart';
import 'package:mobile/features/auth/presentation/bloc/auth_state.dart';
import 'package:mobile/features/sync/domain/entities/local_queue_item.dart';
import 'package:mobile/features/sync/domain/entities/offline_sequence_conflict_bundle.dart';
import 'package:mobile/features/sync/domain/entities/sync_queue_summary.dart';
import 'package:mobile/features/sync/domain/entities/sync_status.dart';
import 'package:mobile/features/sync/presentation/bloc/sync_bloc.dart';
import 'package:mobile/features/sync/presentation/bloc/sync_event.dart';
import 'package:mobile/features/sync/presentation/bloc/sync_state.dart';
import 'package:mobile/features/sync/presentation/screens/sync_status_screen.dart';
import 'package:mocktail/mocktail.dart';

class MockSyncBloc extends Mock implements SyncBloc {}

class MockAuthBloc extends Mock implements AuthBloc {}

class FakeSyncEvent extends Fake implements SyncEvent {}

void main() {
  setUpAll(() {
    registerFallbackValue(FakeSyncEvent());
  });

  late MockSyncBloc mockSyncBloc;
  late MockAuthBloc mockAuthBloc;

  const tUser = UserEntity(
    id: 'user-1',
    tenantId: 'tenant-1',
    email: 'test@workspace.com',
    fullName: 'Test Worker',
    role: 'EMPLOYEE',
    status: 'ACTIVE',
  );

  const tTenant = TenantEntity(
    id: 'tenant-1',
    name: 'Acme Corp',
    slug: 'acme',
    companyEmail: 'contact@acme.com',
    countryCode: 'US',
    timezone: 'UTC',
  );

  const tUserProfile = UserProfile(
    user: tUser,
    tenant: tTenant,
  );

  final tQueueItem = LocalQueueItem(
    localId: 'loc-1',
    idempotencyKey: 'idemp-1',
    sessionId: 'session-1',
    tenantId: 'tenant-1',
    employeeId: 'emp-1',
    userId: 'user-1',
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

  setUp(() {
    mockSyncBloc = MockSyncBloc();
    mockAuthBloc = MockAuthBloc();

    when(() => mockSyncBloc.stream).thenAnswer((_) => const Stream.empty());
    when(() => mockAuthBloc.stream).thenAnswer((_) => const Stream.empty());
    when(() => mockAuthBloc.state)
        .thenReturn(const Authenticated(userProfile: tUserProfile));
  });

  Widget createWidgetUnderTest() {
    return MaterialApp(
      home: MultiBlocProvider(
        providers: [
          BlocProvider<SyncBloc>.value(value: mockSyncBloc),
          BlocProvider<AuthBloc>.value(value: mockAuthBloc),
        ],
        child: const SyncStatusScreen(),
      ),
    );
  }

  group('SyncStatusScreen', () {
    testWidgets(
        'renders metric breakdown cards and empty state when events list is empty',
        (tester) async {
      when(() => mockSyncBloc.state).thenReturn(const SyncState(
        summary: SyncQueueSummary(
          pendingCount: 0,
          syncingCount: 0,
          syncedCount: 12,
          permanentlyRejectedCount: 0,
          quarantinedCount: 0,
          flaggedCount: 1,
        ),
        isConnected: true,
        events: [],
      ));

      await tester.pumpWidget(createWidgetUnderTest());

      // Header metrics
      expect(find.text('Pending'), findsOneWidget);
      expect(find.text('Synced'), findsOneWidget);
      expect(find.text('12'), findsOneWidget);
      expect(find.text('Flagged'), findsOneWidget);
      expect(find.text('1'), findsOneWidget);

      // Empty state view
      expect(find.text('Queue is Empty'), findsOneWidget);
      expect(
          find.textContaining('All attendance punches have been synchronized'),
          findsOneWidget);
    });

    testWidgets('renders list of events when events exist in queue',
        (tester) async {
      when(() => mockSyncBloc.state).thenReturn(SyncState(
        summary: const SyncQueueSummary(
          pendingCount: 1,
          syncingCount: 0,
          syncedCount: 0,
          permanentlyRejectedCount: 0,
          quarantinedCount: 0,
          flaggedCount: 0,
        ),
        isConnected: true,
        events: [tQueueItem],
      ));

      await tester.pumpWidget(createWidgetUnderTest());

      expect(find.text('Stored Queue Records'), findsOneWidget);
      expect(find.text('Check In'), findsOneWidget);
      expect(find.text('Queue is Empty'), findsNothing);
    });

    testWidgets('disables Sync Now button when offline', (tester) async {
      when(() => mockSyncBloc.state).thenReturn(const SyncState(
        summary: SyncQueueSummary(
          pendingCount: 2,
        ),
        isConnected: false,
        isSyncing: false,
      ));

      await tester.pumpWidget(createWidgetUnderTest());

      final buttonFinder = find.byKey(const Key('manual_sync_now_button'));
      expect(buttonFinder, findsOneWidget);

      // Verify button disabled or offline message displayed
      expect(find.text('Internet connection required to synchronize'),
          findsOneWidget);
    });

    testWidgets(
        'dispatches SyncNowRequested when Sync Now button is tapped while online',
        (tester) async {
      when(() => mockSyncBloc.state).thenReturn(const SyncState(
        summary: SyncQueueSummary(
          pendingCount: 2,
        ),
        isConnected: true,
        isSyncing: false,
      ));

      await tester.pumpWidget(createWidgetUnderTest());

      final buttonFinder = find.byKey(const Key('manual_sync_now_button'));
      await tester.tap(buttonFinder);
      await tester.pump();

      verify(() => mockSyncBloc.add(any(that: isA<SyncNowRequested>())))
          .called(1);
    });

    testWidgets(
        'renders Quarantined Conflicts section when conflict bundles exist',
        (tester) async {
      final tPrimary = LocalQueueItem(
        localId: 'loc-1',
        idempotencyKey: 'idemp-1',
        sessionId: 'session-1',
        tenantId: 'tenant-1',
        employeeId: 'emp-1',
        userId: 'user-1',
        eventType: AttendanceEventType.checkIn,
        deviceReportedAt: DateTime.utc(2026, 11, 10, 8, 30),
        timezoneOffsetMinutes: 0,
        monotonicBootTimeMs: 1000,
        bootSessionId: 'boot-1',
        appliedPolicyVersion: 1,
        appliedPolicyMode: 'NONE',
        sequenceNumber: 1,
        syncStatus: SyncStatus.rejectedPermanent,
        conflictBundleId: 'bundle-xyz',
        lastErrorMessage: 'Clock drift exceeded window',
        createdAt: DateTime.utc(2026, 11, 10, 8, 30),
        updatedAt: DateTime.utc(2026, 11, 10, 8, 30),
      );

      final tBundle = OfflineSequenceConflictBundle(
        bundleId: 'bundle-xyz',
        sessionId: 'session-1',
        tenantId: 'tenant-1',
        userId: 'user-1',
        primaryRejectedEvent: tPrimary,
      );

      when(() => mockSyncBloc.state).thenReturn(SyncState(
        conflictBundles: [tBundle],
        isConnected: true,
      ));

      await tester.pumpWidget(createWidgetUnderTest());

      expect(find.text('Quarantined Conflicts'), findsOneWidget);
      expect(find.text('Needs Review'), findsOneWidget);
      expect(
          find.byKey(const Key('conflict_bundle_bundle-xyz')), findsOneWidget);
    });
  });
}
