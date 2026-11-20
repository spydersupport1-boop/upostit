import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/theme/app_theme.dart';
import 'package:mobile/features/auth/domain/entities/user_profile.dart';
import 'package:mobile/features/auth/presentation/bloc/auth_bloc.dart';
import 'package:mobile/features/auth/presentation/bloc/auth_event.dart';
import 'package:mobile/features/auth/presentation/bloc/auth_state.dart';
import 'package:mobile/features/profile/domain/entities/employee.dart';
import 'package:mobile/features/profile/presentation/bloc/profile_bloc.dart';
import 'package:mobile/features/profile/presentation/bloc/profile_state.dart';
import 'package:mobile/features/profile/presentation/screens/profile_screen.dart';
import 'package:mobile/features/sync/domain/repositories/local_queue_dao.dart';
import 'package:mobile/features/sync/presentation/widgets/logout_warning_dialog.dart';
import 'package:mocktail/mocktail.dart';

class MockAuthBloc extends Mock implements AuthBloc {}

class MockProfileBloc extends Mock implements ProfileBloc {}

class MockLocalQueueDao extends Mock implements LocalQueueDao {}

void main() {
  late MockAuthBloc mockAuthBloc;
  late MockProfileBloc mockProfileBloc;
  late MockLocalQueueDao mockDao;

  const testUser = UserEntity(
    id: 'user-1',
    tenantId: 'tenant-1',
    email: 'admin@acme.com',
    fullName: 'Alice Admin',
    role: 'owner',
    status: 'active',
  );

  const testTenant = TenantEntity(
    id: 'tenant-1',
    name: 'Acme Corporation',
    slug: 'acme-corp',
    companyEmail: 'contact@acme.com',
    countryCode: 'US',
    timezone: 'UTC',
  );

  const testUserProfile = UserProfile(
    user: testUser,
    tenant: testTenant,
  );

  const testEmployee = Employee(
    id: 'emp-1',
    userId: 'user-1',
    tenantId: 'tenant-1',
    employeeId: 'EMP-001',
    firstName: 'Alice',
    lastName: 'Smith',
    workEmail: 'alice.smith@acme.com',
    employmentType: 'full_time',
    status: 'active',
  );

  setUp(() {
    mockAuthBloc = MockAuthBloc();
    mockProfileBloc = MockProfileBloc();
    mockDao = MockLocalQueueDao();

    when(() => mockAuthBloc.stream).thenAnswer((_) => const Stream.empty());
    when(() => mockProfileBloc.stream).thenAnswer((_) => const Stream.empty());
    when(() => mockAuthBloc.state)
        .thenReturn(const Authenticated(userProfile: testUserProfile));
    when(() => mockProfileBloc.state)
        .thenReturn(const ProfileLoaded(employee: testEmployee));
  });

  Widget buildTestWidget({LocalQueueDao? dao}) {
    return MaterialApp(
      theme: AppTheme.lightTheme,
      home: MultiBlocProvider(
        providers: [
          BlocProvider<AuthBloc>.value(value: mockAuthBloc),
          BlocProvider<ProfileBloc>.value(value: mockProfileBloc),
        ],
        child: ProfileScreen(localQueueDao: dao),
      ),
    );
  }

  group('ProfileScreen Logout Safety & Queue Tile', () {
    testWidgets('renders Offline Attendance Queue tile', (tester) async {
      await tester.pumpWidget(buildTestWidget());

      expect(find.text('Offline Attendance Queue'), findsOneWidget);
      expect(find.text('View queued punches, sync status and timeline'),
          findsOneWidget);
      expect(find.byIcon(Icons.cloud_sync_outlined), findsOneWidget);
    });

    testWidgets(
        'shows LogoutWarningDialog when unresolved records > 0, cancel keeps session intact',
        (tester) async {
      when(() => mockDao.getUnresolvedCount(
            tenantId: 'tenant-1',
            userId: 'user-1',
          )).thenAnswer((_) async => 4);

      await tester.pumpWidget(buildTestWidget(dao: mockDao));

      final signOutBtn = find.text('Sign Out of Account');
      await tester.ensureVisible(signOutBtn);
      await tester.tap(signOutBtn);
      await tester.pumpAndSettle();

      // Verify LogoutWarningDialog is presented
      expect(find.byType(LogoutWarningDialog), findsOneWidget);
      expect(find.text('Unsynced Records Warning'), findsOneWidget);
      expect(
          find.textContaining(
              'You have 4 unsynchronized attendance punches stored locally'),
          findsOneWidget);
      expect(find.textContaining('Cancel & Stay Signed In'), findsOneWidget);
      expect(find.textContaining('Sign Out Anyway'), findsOneWidget);

      // Tap Cancel
      await tester.tap(find.text('Cancel & Stay Signed In'));
      await tester.pumpAndSettle();

      // Dialog dismissed, session intact
      expect(find.byType(LogoutWarningDialog), findsNothing);
      verifyNever(() => mockAuthBloc.add(const LogoutRequested()));
    });

    testWidgets(
        'confirming Sign Out Anyway in LogoutWarningDialog dispatches LogoutRequested',
        (tester) async {
      when(() => mockDao.getUnresolvedCount(
            tenantId: 'tenant-1',
            userId: 'user-1',
          )).thenAnswer((_) async => 2);

      await tester.pumpWidget(buildTestWidget(dao: mockDao));

      final signOutBtn = find.text('Sign Out of Account');
      await tester.ensureVisible(signOutBtn);
      await tester.tap(signOutBtn);
      await tester.pumpAndSettle();

      // Tap Sign Out Anyway
      await tester.tap(find.text('Sign Out Anyway'));
      await tester.pumpAndSettle();

      verify(() => mockAuthBloc.add(const LogoutRequested())).called(1);
    });

    testWidgets(
        'shows standard confirmation dialog when unresolved records == 0',
        (tester) async {
      when(() => mockDao.getUnresolvedCount(
            tenantId: 'tenant-1',
            userId: 'user-1',
          )).thenAnswer((_) async => 0);

      await tester.pumpWidget(buildTestWidget(dao: mockDao));

      final signOutBtn = find.text('Sign Out of Account');
      await tester.ensureVisible(signOutBtn);
      await tester.tap(signOutBtn);
      await tester.pumpAndSettle();

      // Warning dialog NOT shown
      expect(find.byType(LogoutWarningDialog), findsNothing);
      // Standard dialog shown
      expect(
          find.text(
              'Are you sure you want to sign out of your workspace session?'),
          findsOneWidget);

      // Confirm sign out
      await tester.tap(find.widgetWithText(ElevatedButton, 'Sign Out'));
      await tester.pumpAndSettle();

      verify(() => mockAuthBloc.add(const LogoutRequested())).called(1);
    });
  });
}
