import 'package:bloc_test/bloc_test.dart';
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:mobile/features/attendance/domain/entities/assigned_workplace.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_dashboard.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_event.dart';
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
import 'package:mobile/shared/widgets/loading_indicator.dart';

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
          status: 'ACTIVE',
        ),
      ),
    );
  });

  Widget createWidgetUnderTest() {
    return MultiBlocProvider(
      providers: [
        BlocProvider<AttendanceBloc>.value(value: mockAttendanceBloc),
        BlocProvider<AuthBloc>.value(value: mockAuthBloc),
        BlocProvider<ProfileBloc>.value(value: mockProfileBloc),
      ],
      child: const MaterialApp(
        home: AttendanceHomeScreen(),
      ),
    );
  }

  testWidgets('renders LoadingIndicator when state is AttendanceLoading',
      (tester) async {
    when(() => mockAttendanceBloc.state).thenReturn(const AttendanceLoading());

    await tester.pumpWidget(createWidgetUnderTest());

    expect(find.byType(LoadingIndicator), findsOneWidget);
    expect(find.text('Loading attendance status...'), findsOneWidget);
  });

  testWidgets(
      'renders AttendanceLoadFailure view with retry button on load error',
      (tester) async {
    when(() => mockAttendanceBloc.state).thenReturn(
      const AttendanceLoadFailure(
          message: 'Cannot reach server', isNetworkError: true),
    );

    await tester.pumpWidget(createWidgetUnderTest());

    expect(find.text('Failed to Load Attendance'), findsOneWidget);
    expect(find.text('Cannot reach server'), findsOneWidget);
    expect(
        find.byKey(const Key('attendance_load_retry_button')), findsOneWidget);

    await tester.tap(find.byKey(const Key('attendance_load_retry_button')));
    await tester.pump();

    verify(() => mockAttendanceBloc.add(const AttendanceDashboardRequested()))
        .called(greaterThanOrEqualTo(1));
  });

  testWidgets(
      'renders full AttendanceHomeScreen layout when state is AttendanceLoaded',
      (tester) async {
    final dashboard = AttendanceDashboard(
      status: AttendanceStatus.working,
      workingDuration: const Duration(hours: 2, minutes: 15, seconds: 30),
      shift: const TodayShift(
        id: 'shift-1',
        name: 'Morning Field Shift',
        code: 'MFS',
        startTime: '08:00:00',
        endTime: '17:00:00',
      ),
      workplace: const AssignedWorkplace(
        id: 'wp-1',
        locationId: 'loc-1',
        locationName: 'North Warehouse',
        locationCode: 'NWH',
        address: '100 Industrial Pkwy',
        city: 'Chicago',
        countryCode: 'US',
        isPrimary: true,
        isCurrent: true,
      ),
      todayEvents: [
        AttendanceEvent(
          id: 'evt-1',
          tenantId: 't-1',
          employeeId: 'emp-1',
          eventType: AttendanceEventType.checkIn,
          eventCategory: 'STANDARD',
          serverReceivedAt: DateTime.utc(2026, 11, 4, 8, 0, 0),
          effectiveAt: DateTime.utc(2026, 11, 4, 8, 0, 0),
          source: 'MOBILE',
          timestampVerificationStatus: 'SERVER_AUTHORITATIVE',
          reviewStatus: 'NOT_REQUIRED',
          idempotencyKey: 'key-1',
          createdAt: DateTime.utc(2026, 11, 4, 8, 0, 0),
        ),
      ],
      lastEvent: AttendanceEvent(
        id: 'evt-1',
        tenantId: 't-1',
        employeeId: 'emp-1',
        eventType: AttendanceEventType.checkIn,
        eventCategory: 'STANDARD',
        serverReceivedAt: DateTime.utc(2026, 11, 4, 8, 0, 0),
        effectiveAt: DateTime.utc(2026, 11, 4, 8, 0, 0),
        source: 'MOBILE',
        timestampVerificationStatus: 'SERVER_AUTHORITATIVE',
        reviewStatus: 'NOT_REQUIRED',
        idempotencyKey: 'key-1',
        createdAt: DateTime.utc(2026, 11, 4, 8, 0, 0),
      ),
    );

    when(() => mockAttendanceBloc.state).thenReturn(
      AttendanceLoaded(dashboard: dashboard),
    );

    await tester.pumpWidget(createWidgetUnderTest());

    // 1. Employee header
    expect(find.text('Alexander Wright'), findsOneWidget);
    expect(find.textContaining('Senior Field Specialist'), findsOneWidget);
    expect(find.text('WORKING'), findsOneWidget);

    // 2. Shift and workplace
    expect(find.text('Morning Field Shift'), findsOneWidget);
    expect(find.text('North Warehouse'), findsOneWidget);

    // 3. Timer
    expect(find.byKey(const Key('working_timer_text')), findsOneWidget);
    expect(find.text('02:15:30'), findsOneWidget);

    // 4. Hero punch actions for WORKING state
    expect(find.byKey(const Key('hero_check_out_button')), findsOneWidget);
    expect(find.byKey(const Key('break_start_button')), findsOneWidget);

    // 5. Last punch badge and timeline
    expect(find.textContaining('Last punch: Check In'), findsOneWidget);
    expect(find.text('CONFIRMED'), findsOneWidget);
    expect(find.text('TODAY PUNCH TIMELINE'), findsOneWidget);
  });

  testWidgets(
      'renders retriable error banner and dispatches PunchRetryRequested on retry tap',
      (tester) async {
    const dashboard = AttendanceDashboard(
      status: AttendanceStatus.notCheckedIn,
      todayEvents: [],
    );

    when(() => mockAttendanceBloc.state).thenReturn(
      const AttendanceLoaded(
        dashboard: dashboard,
        errorMessage: 'Connection lost while submitting punch.',
        isRetriable: true,
        inFlightIdempotencyKey: 'key-retry-test',
        inFlightEventType: AttendanceEventType.checkIn,
      ),
    );

    await tester.pumpWidget(createWidgetUnderTest());

    expect(
        find.text('Connection lost while submitting punch.'), findsOneWidget);
    expect(find.byKey(const Key('punch_retry_button')), findsOneWidget);

    await tester.tap(find.byKey(const Key('punch_retry_button')));
    await tester.pump();

    verify(() => mockAttendanceBloc.add(const PunchRetryRequested())).called(1);
  });

  testWidgets(
      'renders pending review warning notice when reviewStatus is PENDING_REVIEW',
      (tester) async {
    const dashboard = AttendanceDashboard(
      status: AttendanceStatus.working,
      todayEvents: [],
    );

    when(() => mockAttendanceBloc.state).thenReturn(
      const AttendanceLoaded(
        dashboard: dashboard,
        pendingReviewNotice:
            'Punch recorded but flagged for manager review (SUSPICIOUS_CLOCK_DRIFT)',
      ),
    );

    await tester.pumpWidget(createWidgetUnderTest());

    expect(
      find.text(
          'Punch recorded but flagged for manager review (SUSPICIOUS_CLOCK_DRIFT)'),
      findsOneWidget,
    );
  });
}
