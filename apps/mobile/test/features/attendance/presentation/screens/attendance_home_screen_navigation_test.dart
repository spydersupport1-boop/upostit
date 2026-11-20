import 'package:bloc_test/bloc_test.dart';
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mocktail/mocktail.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_dashboard.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_status.dart';
import 'package:mobile/features/attendance/domain/entities/today_shift.dart';
import 'package:mobile/features/attendance/presentation/bloc/attendance_bloc.dart';
import 'package:mobile/features/attendance/presentation/bloc/attendance_event.dart';
import 'package:mobile/features/attendance/presentation/bloc/attendance_state.dart';
import 'package:mobile/features/attendance/presentation/screens/attendance_home_screen.dart';
import 'package:mobile/features/auth/domain/entities/user_profile.dart';
import 'package:mobile/features/auth/presentation/bloc/auth_bloc.dart';
import 'package:mobile/features/auth/presentation/bloc/auth_event.dart';
import 'package:mobile/features/auth/presentation/bloc/auth_state.dart';
import 'package:mobile/features/profile/domain/entities/employee.dart';
import 'package:mobile/features/profile/presentation/bloc/profile_bloc.dart';
import 'package:mobile/features/profile/presentation/bloc/profile_event.dart';
import 'package:mobile/features/profile/presentation/bloc/profile_state.dart';

class MockAttendanceBloc extends MockBloc<AttendanceBlocEvent, AttendanceState>
    implements AttendanceBloc {}

class MockAuthBloc extends MockBloc<AuthEvent, AuthState> implements AuthBloc {}

class MockProfileBloc extends MockBloc<ProfileEvent, ProfileState>
    implements ProfileBloc {}

void main() {
  late MockAttendanceBloc mockAttendanceBloc;
  late MockAuthBloc mockAuthBloc;
  late MockProfileBloc mockProfileBloc;

  setUp(() {
    mockAttendanceBloc = MockAttendanceBloc();
    mockAuthBloc = MockAuthBloc();
    mockProfileBloc = MockProfileBloc();

    when(() => mockAuthBloc.state).thenReturn(
      const Authenticated(
        userProfile: UserProfile(
          user: UserEntity(
            id: 'u-1',
            tenantId: 't-1',
            fullName: 'Alexander Wright',
            email: 'alex@company.com',
            role: 'employee',
            status: 'active',
          ),
          tenant: TenantEntity(
            id: 't-1',
            slug: 'acme-corp',
            name: 'Acme Corporation',
            companyEmail: 'info@acme.com',
            countryCode: 'US',
            timezone: 'America/New_York',
          ),
        ),
      ),
    );

    when(() => mockProfileBloc.state).thenReturn(
      const ProfileLoaded(
        employee: Employee(
          id: 'emp-1',
          tenantId: 't-1',
          employeeId: 'EMP-001',
          firstName: 'Alexander',
          lastName: 'Wright',
          workEmail: 'alex@company.com',
          employmentType: 'FULL_TIME',
          designationTitle: 'Senior Field Specialist',
          departmentName: 'Field Operations',
          status: 'ACTIVE',
        ),
      ),
    );
  });

  Widget createTestApp(GoRouter router) {
    return MultiBlocProvider(
      providers: [
        BlocProvider<AttendanceBloc>.value(value: mockAttendanceBloc),
        BlocProvider<AuthBloc>.value(value: mockAuthBloc),
        BlocProvider<ProfileBloc>.value(value: mockProfileBloc),
      ],
      child: MaterialApp.router(
        routerConfig: router,
      ),
    );
  }

  group('AttendanceHomeScreen - Navigation & Quick Actions', () {
    testWidgets('renders 4 navigation destinations and quick action cards',
        (tester) async {
      const dashboard = AttendanceDashboard(
        status: AttendanceStatus.notCheckedIn,
        shift: TodayShift(
          id: 'shift-1',
          name: 'Day Shift',
          code: 'DAY',
          startTime: '09:00:00',
          endTime: '17:00:00',
        ),
        todayEvents: [],
      );

      when(() => mockAttendanceBloc.state).thenReturn(
        const AttendanceLoaded(dashboard: dashboard),
      );

      final router = GoRouter(
        initialLocation: '/home',
        routes: [
          GoRoute(
            path: '/home',
            builder: (_, __) => const AttendanceHomeScreen(),
          ),
          GoRoute(
            path: '/schedule',
            builder: (_, __) =>
                const Scaffold(body: Text('Schedule Screen Target')),
          ),
          GoRoute(
            path: '/history',
            builder: (_, __) =>
                const Scaffold(body: Text('History Screen Target')),
          ),
          GoRoute(
            path: '/profile',
            builder: (_, __) =>
                const Scaffold(body: Text('Profile Screen Target')),
          ),
          GoRoute(
            path: '/sync',
            builder: (_, __) =>
                const Scaffold(body: Text('Sync Screen Target')),
          ),
        ],
      );

      await tester.pumpWidget(createTestApp(router));
      await tester.pumpAndSettle();

      // Verify bottom nav destinations & app bar
      expect(find.text('Attendance'),
          findsNWidgets(2)); // in app bar and bottom nav
      expect(find.text('Schedule'),
          findsNWidgets(2)); // in nav bar and quick action
      expect(find.text('History'),
          findsNWidgets(2)); // in nav bar and quick action
      expect(find.text('Profile'), findsOneWidget);
      expect(find.text('Sync Queue'), findsOneWidget);

      // Tap NavigationBar destination Schedule
      await tester.tap(find.byIcon(Icons.calendar_month_outlined).first);
      await tester.pumpAndSettle();
      expect(find.text('Schedule Screen Target'), findsOneWidget);
    });

    testWidgets('quick navigation action card navigates to /history',
        (tester) async {
      const dashboard = AttendanceDashboard(
        status: AttendanceStatus.notCheckedIn,
        shift: TodayShift(
          id: 'shift-1',
          name: 'Day Shift',
          code: 'DAY',
          startTime: '09:00:00',
          endTime: '17:00:00',
        ),
        todayEvents: [],
      );

      when(() => mockAttendanceBloc.state).thenReturn(
        const AttendanceLoaded(dashboard: dashboard),
      );

      final router = GoRouter(
        initialLocation: '/home',
        routes: [
          GoRoute(
            path: '/home',
            builder: (_, __) => const AttendanceHomeScreen(),
          ),
          GoRoute(
            path: '/schedule',
            builder: (_, __) =>
                const Scaffold(body: Text('Schedule Screen Target')),
          ),
          GoRoute(
            path: '/history',
            builder: (_, __) =>
                const Scaffold(body: Text('History Screen Target')),
          ),
        ],
      );

      await tester.pumpWidget(createTestApp(router));
      await tester.pumpAndSettle();

      // Tap History Quick Action card
      await tester.tap(find.text('History').first);
      await tester.pumpAndSettle();
      expect(find.text('History Screen Target'), findsOneWidget);
    });
  });
}
