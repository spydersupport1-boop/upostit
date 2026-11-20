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
import 'package:mocktail/mocktail.dart';

class MockAuthBloc extends Mock implements AuthBloc {}

class MockProfileBloc extends Mock implements ProfileBloc {}

void main() {
  late MockAuthBloc mockAuthBloc;
  late MockProfileBloc mockProfileBloc;

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
    departmentName: 'Engineering',
    designationTitle: 'Senior Software Engineer',
    employmentType: 'full_time',
    status: 'active',
  );

  setUp(() {
    mockAuthBloc = MockAuthBloc();
    mockProfileBloc = MockProfileBloc();

    when(() => mockAuthBloc.stream).thenAnswer((_) => const Stream.empty());
    when(() => mockProfileBloc.stream).thenAnswer((_) => const Stream.empty());
  });

  Widget buildTestWidget() {
    return MaterialApp(
      theme: AppTheme.lightTheme,
      home: MultiBlocProvider(
        providers: [
          BlocProvider<AuthBloc>.value(value: mockAuthBloc),
          BlocProvider<ProfileBloc>.value(value: mockProfileBloc),
        ],
        child: const ProfileScreen(),
      ),
    );
  }

  testWidgets('renders loading state when auth state is not Authenticated',
      (tester) async {
    when(() => mockAuthBloc.state).thenReturn(const AuthInitial());
    when(() => mockProfileBloc.state).thenReturn(const ProfileInitial());

    await tester.pumpWidget(buildTestWidget());

    expect(find.text('Loading authentication session...'), findsOneWidget);
  });

  testWidgets('renders tenant and employee details when profile is loaded',
      (tester) async {
    when(() => mockAuthBloc.state).thenReturn(
      const Authenticated(
        userProfile: testUserProfile,
      ),
    );
    when(() => mockProfileBloc.state)
        .thenReturn(const ProfileLoaded(employee: testEmployee));

    await tester.pumpWidget(buildTestWidget());

    // Tenant info
    expect(find.text('Acme Corporation'), findsOneWidget);
    expect(find.text('Workspace: acme-corp • UTC'), findsOneWidget);

    // Employee identity info
    expect(find.text('Alice Smith'), findsOneWidget);
    expect(find.text('alice.smith@acme.com'), findsOneWidget);
    expect(find.text('EMP-001'), findsOneWidget);
    expect(find.text('Engineering'), findsOneWidget);
    expect(find.text('Senior Software Engineer'), findsOneWidget);
    expect(find.text('FULL TIME'), findsOneWidget);
    expect(find.text('OWNER'), findsOneWidget);
    expect(find.text('ACTIVE'), findsOneWidget);

    // Sign out button
    expect(find.text('Sign Out of Account'), findsOneWidget);
  });

  testWidgets(
      'renders fallback administrative user details when employee is not linked',
      (tester) async {
    when(() => mockAuthBloc.state).thenReturn(
      const Authenticated(
        userProfile: testUserProfile,
      ),
    );
    when(() => mockProfileBloc.state).thenReturn(
        const ProfileLoaded(employee: null, hasLinkedEmployee: false));

    await tester.pumpWidget(buildTestWidget());

    // User fallback
    expect(find.text('Alice Admin'), findsOneWidget);
    expect(find.text('admin@acme.com'), findsOneWidget);
    expect(find.text('Administrative User'), findsOneWidget);
  });

  testWidgets('displays warning banner when profile fetching returns an error',
      (tester) async {
    when(() => mockAuthBloc.state).thenReturn(
      const Authenticated(
        userProfile: testUserProfile,
      ),
    );
    when(() => mockProfileBloc.state).thenReturn(
      const ProfileError(
          'Could not reach workforce services. Showing cached identity.'),
    );

    await tester.pumpWidget(buildTestWidget());

    expect(
        find.text(
            'Could not reach workforce services. Showing cached identity.'),
        findsOneWidget);
  });

  testWidgets(
      'shows confirmation dialog on logout and dispatches LogoutRequested on confirm',
      (tester) async {
    when(() => mockAuthBloc.state).thenReturn(
      const Authenticated(
        userProfile: testUserProfile,
      ),
    );
    when(() => mockProfileBloc.state)
        .thenReturn(const ProfileLoaded(employee: testEmployee));

    await tester.pumpWidget(buildTestWidget());

    // Tap sign out button
    final signOutFinder = find.text('Sign Out of Account');
    await tester.ensureVisible(signOutFinder);
    await tester.tap(signOutFinder);
    await tester.pumpAndSettle();

    // Verify dialog content
    expect(find.text('Sign Out'), findsNWidgets(2)); // Title and confirm button
    expect(
        find.text(
            'Are you sure you want to sign out of your workspace session?'),
        findsOneWidget);

    // Confirm logout
    await tester.tap(find.widgetWithText(ElevatedButton, 'Sign Out'));
    await tester.pumpAndSettle();

    verify(() => mockAuthBloc.add(const LogoutRequested())).called(1);
  });
}
