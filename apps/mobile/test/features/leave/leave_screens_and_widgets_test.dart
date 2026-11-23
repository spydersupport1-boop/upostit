import 'package:bloc_test/bloc_test.dart';
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:mobile/features/auth/domain/entities/user_profile.dart';
import 'package:mobile/features/auth/presentation/bloc/auth_bloc.dart';
import 'package:mobile/features/auth/presentation/bloc/auth_event.dart';
import 'package:mobile/features/auth/presentation/bloc/auth_state.dart';
import 'package:mobile/features/leave/domain/entities/leave_balance.dart';
import 'package:mobile/features/leave/domain/entities/leave_request.dart';
import 'package:mobile/features/leave/domain/entities/leave_type.dart';
import 'package:mobile/features/leave/domain/entities/upcoming_holiday.dart';
import 'package:mobile/features/leave/presentation/bloc/leave_bloc.dart';
import 'package:mobile/features/leave/presentation/bloc/leave_event.dart';
import 'package:mobile/features/leave/presentation/bloc/leave_state.dart';
import 'package:mobile/features/leave/presentation/screens/apply_leave_screen.dart';
import 'package:mobile/features/leave/presentation/screens/holiday_hub_screen.dart';
import 'package:mobile/features/leave/presentation/screens/leave_approvals_screen.dart';
import 'package:mobile/features/leave/presentation/screens/leave_dashboard_screen.dart';
import 'package:mobile/features/leave/presentation/screens/leave_history_screen.dart';
import 'package:mobile/features/leave/presentation/widgets/balance_card.dart';
import 'package:mobile/features/leave/presentation/widgets/holiday_tile.dart';
import 'package:mobile/features/leave/presentation/widgets/leave_request_card.dart';
import 'package:mobile/features/leave/presentation/widgets/leave_status_badge.dart';

class MockLeaveBloc extends MockBloc<LeaveEvent, LeaveState>
    implements LeaveBloc {}

class MockAuthBloc extends MockBloc<AuthEvent, AuthState> implements AuthBloc {}

void main() {
  late MockLeaveBloc mockLeaveBloc;
  late MockAuthBloc mockAuthBloc;

  const sampleType = LeaveType(
    id: 'lt-1',
    code: 'ANNUAL',
    name: 'Annual Leave',
    isPaid: true,
    requiresApproval: true,
    allowHalfDay: true,
    maxConsecutiveDays: 14,
    carryForwardLimit: 5,
    isActive: true,
  );

  const sampleBalance = LeaveBalance(
    id: 'lb-1',
    employeeId: 'emp-101',
    leaveTypeId: 'lt-1',
    leaveTypeCode: 'ANNUAL',
    leaveTypeName: 'Annual Leave',
    year: 2026,
    annualAllocation: 15,
    carriedForward: 0,
    accrued: 0,
    used: 2,
    pendingApproval: 1,
    availableBalance: 12,
  );

  final sampleRequest = LeaveRequest(
    id: 'lr-1',
    employeeId: 'emp-101',
    employeeName: 'John Employee',
    leaveTypeId: 'lt-1',
    leaveTypeCode: 'ANNUAL',
    startDate: '2026-12-01',
    endDate: '2026-12-03',
    isHalfDay: false,
    totalDays: 3,
    reason: 'Family trip',
    status: 'PENDING_APPROVAL',
    createdAt: DateTime(2026, 11, 20),
  );

  const sampleHoliday = UpcomingHoliday(
    id: 'hol-1',
    holidayDate: '2026-12-25',
    name: 'Christmas Day',
    holidayType: 'PUBLIC',
    isOptional: false,
    calendarId: 'cal-1',
    calendarName: 'National Calendar',
    resolutionSource: 'LOCATION',
  );

  setUp(() {
    mockLeaveBloc = MockLeaveBloc();
    mockAuthBloc = MockAuthBloc();

    when(() => mockAuthBloc.state).thenReturn(
      const Authenticated(
        userProfile: UserProfile(
          user: UserEntity(
            id: 'mgr-1',
            tenantId: 't-1',
            fullName: 'Manager Smith',
            email: 'mgr@acme.com',
            role: 'MANAGER',
            status: 'active',
          ),
          tenant: TenantEntity(
            id: 't-1',
            slug: 'acme',
            name: 'Acme Corp',
            companyEmail: 'info@acme.com',
            countryCode: 'US',
            timezone: 'America/New_York',
          ),
        ),
      ),
    );
  });

  Widget createTestWidget(Widget child) {
    return MultiBlocProvider(
      providers: [
        BlocProvider<LeaveBloc>.value(value: mockLeaveBloc),
        BlocProvider<AuthBloc>.value(value: mockAuthBloc),
      ],
      child: MaterialApp(
        home: child,
      ),
    );
  }

  group('Leave Widgets Tests', () {
    testWidgets('LeaveStatusBadge renders correct labels and styles',
        (tester) async {
      await tester.pumpWidget(const MaterialApp(
        home: Column(
          children: [
            LeaveStatusBadge(status: 'APPROVED'),
            LeaveStatusBadge(status: 'PENDING_APPROVAL'),
            LeaveStatusBadge(status: 'REJECTED'),
            LeaveStatusBadge(status: 'CANCELLED'),
          ],
        ),
      ));

      expect(find.text('Approved'), findsOneWidget);
      expect(find.text('Pending'), findsOneWidget);
      expect(find.text('Rejected'), findsOneWidget);
      expect(find.text('Cancelled'), findsOneWidget);
    });

    testWidgets('BalanceCard renders available days and allocations',
        (tester) async {
      await tester.pumpWidget(const MaterialApp(
        home: Scaffold(
          body: BalanceCard(
            balance: sampleBalance,
            leaveType: sampleType,
          ),
        ),
      ));

      expect(find.text('Annual Leave'), findsOneWidget);
      expect(find.text('ANNUAL'), findsOneWidget);
      expect(find.text('12.0'), findsOneWidget);
      expect(find.text('days available'), findsOneWidget);
      expect(find.text('Used: 2.0d'), findsOneWidget);
      expect(find.text('Pending: 1.0d'), findsOneWidget);
    });

    testWidgets('HolidayTile renders holiday date, name, and resolution source',
        (tester) async {
      await tester.pumpWidget(const MaterialApp(
        home: Scaffold(
          body: HolidayTile(holiday: sampleHoliday),
        ),
      ));

      expect(find.text('Christmas Day'), findsOneWidget);
      expect(find.text('PUBLIC'), findsOneWidget);
      expect(find.text('National Calendar'), findsOneWidget);
      expect(find.text('location'), findsOneWidget);
    });

    testWidgets('LeaveRequestCard displays details and triggers onCancel',
        (tester) async {
      var cancelled = false;
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: LeaveRequestCard(
            request: sampleRequest,
            onCancel: () => cancelled = true,
          ),
        ),
      ));

      expect(find.text('ANNUAL'), findsOneWidget);
      expect(find.text('3 days'), findsOneWidget);
      expect(find.text('Family trip'), findsOneWidget);
      expect(find.text('Cancel Request'), findsOneWidget);

      await tester.tap(find.text('Cancel Request'));
      await tester.pump();
      expect(cancelled, true);
    });
  });

  group('Leave Screens Tests', () {
    testWidgets('LeaveDashboardScreen renders balances, requests, and holidays',
        (tester) async {
      when(() => mockLeaveBloc.state).thenReturn(
        LeaveState(
          balances: const [sampleBalance],
          leaveTypes: const [sampleType],
          myRequests: [sampleRequest],
          upcomingHolidays: const [sampleHoliday],
        ),
      );

      await tester.pumpWidget(createTestWidget(const LeaveDashboardScreen()));
      await tester.pumpAndSettle();

      expect(find.text('Leave & Holidays'), findsOneWidget);
      expect(find.text('Apply for Leave'), findsOneWidget);
      expect(find.text('Leave Balances'), findsOneWidget);
      expect(find.text('12.0'), findsOneWidget);
      expect(find.text('Recent Requests'), findsOneWidget);
      expect(find.text('Upcoming Holidays'), findsOneWidget);
      expect(find.text('Christmas Day'), findsOneWidget);
    });

    testWidgets('ApplyLeaveScreen validates reason input', (tester) async {
      tester.view.physicalSize = const Size(800, 1400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() {
        tester.view.resetPhysicalSize();
        tester.view.resetDevicePixelRatio();
      });

      when(() => mockLeaveBloc.state).thenReturn(
        const LeaveState(
          leaveTypes: [sampleType],
          balances: [sampleBalance],
        ),
      );

      await tester.pumpWidget(createTestWidget(const ApplyLeaveScreen()));
      await tester.pumpAndSettle();

      expect(find.text('Apply for Leave'), findsOneWidget);
      expect(find.text('Annual Leave (ANNUAL)'), findsOneWidget);

      // Tap submit with empty reason
      await tester.tap(find.text('Submit Leave Application'));
      await tester.pumpAndSettle();

      expect(find.text('Reason is required'), findsOneWidget);
    });

    testWidgets(
        'HolidayHubScreen renders upcoming holidays and resolution info',
        (tester) async {
      when(() => mockLeaveBloc.state).thenReturn(
        const LeaveState(
          upcomingHolidays: [sampleHoliday],
        ),
      );

      await tester.pumpWidget(createTestWidget(const HolidayHubScreen()));
      await tester.pumpAndSettle();

      expect(find.text('Holiday Calendar'), findsOneWidget);
      expect(find.text('Christmas Day'), findsOneWidget);
      expect(
        find.textContaining('Holidays are automatically resolved'),
        findsOneWidget,
      );
    });

    testWidgets('LeaveHistoryScreen renders list of requests and filter chips',
        (tester) async {
      when(() => mockLeaveBloc.state).thenReturn(
        LeaveState(
          myRequests: [sampleRequest],
        ),
      );

      await tester.pumpWidget(createTestWidget(const LeaveHistoryScreen()));
      await tester.pumpAndSettle();

      expect(find.text('Leave History'), findsOneWidget);
      expect(find.text('All'), findsOneWidget);
      expect(find.widgetWithText(FilterChip, 'Pending'), findsOneWidget);
      expect(find.text('Family trip'), findsOneWidget);
    });

    testWidgets(
        'LeaveApprovalsScreen displays queue and enforces anti-self-approval',
        (tester) async {
      final selfRequest = LeaveRequest(
        id: 'lr-self',
        employeeId: 'mgr-1', // same as current user 'mgr-1'
        leaveTypeId: 'lt-1',
        leaveTypeCode: 'ANNUAL',
        startDate: '2026-12-10',
        endDate: '2026-12-12',
        isHalfDay: false,
        totalDays: 2,
        reason: 'My own vacation',
        status: 'PENDING_APPROVAL',
        createdAt: DateTime(2026, 11, 20),
      );

      when(() => mockLeaveBloc.state).thenReturn(
        LeaveState(
          supervisorQueue: [sampleRequest, selfRequest],
        ),
      );

      await tester.pumpWidget(createTestWidget(const LeaveApprovalsScreen()));
      await tester.pumpAndSettle();

      expect(find.text('Leave Approvals'), findsOneWidget);
      expect(find.textContaining('Family trip'), findsOneWidget);

      // Normal request has Approve & Reject
      expect(find.text('Approve'), findsOneWidget);
      expect(find.text('Reject'), findsOneWidget);

      // Self-submitted request has Anti-Self-Approval notice and NO Approve/Reject buttons
      expect(
        find.textContaining(
            'Anti-Self-Approval: You cannot approve or reject your own leave request.'),
        findsOneWidget,
      );
    });
  });
}
