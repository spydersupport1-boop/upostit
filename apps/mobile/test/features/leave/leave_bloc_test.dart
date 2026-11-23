import 'package:bloc_test/bloc_test.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:mobile/core/errors/failure.dart';
import 'package:mobile/core/errors/result.dart';
import 'package:mobile/features/leave/domain/entities/leave_balance.dart';
import 'package:mobile/features/leave/domain/entities/leave_request.dart';
import 'package:mobile/features/leave/domain/entities/leave_type.dart';
import 'package:mobile/features/leave/domain/entities/upcoming_holiday.dart';
import 'package:mobile/features/leave/domain/repositories/leave_repository.dart';
import 'package:mobile/features/leave/presentation/bloc/leave_bloc.dart';
import 'package:mobile/features/leave/presentation/bloc/leave_event.dart';
import 'package:mobile/features/leave/presentation/bloc/leave_state.dart';

class MockLeaveRepository extends Mock implements LeaveRepository {}

void main() {
  late MockLeaveRepository mockRepository;

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
    employeeId: 'emp-1',
    leaveTypeId: 'lt-1',
    leaveTypeCode: 'ANNUAL',
    leaveTypeName: 'Annual Leave',
    year: 2026,
    annualAllocation: 15,
    carriedForward: 0,
    accrued: 0,
    used: 2,
    pendingApproval: 0,
    availableBalance: 13,
  );

  final sampleRequest = LeaveRequest(
    id: 'lr-1',
    employeeId: 'emp-1',
    leaveTypeId: 'lt-1',
    leaveTypeCode: 'ANNUAL',
    startDate: '2026-12-01',
    endDate: '2026-12-03',
    isHalfDay: false,
    totalDays: 3,
    reason: 'Vacation',
    status: 'PENDING_APPROVAL',
    createdAt: DateTime(2026, 11, 20),
  );

  const sampleHoliday = UpcomingHoliday(
    id: 'h-1',
    holidayDate: '2026-12-25',
    name: 'Christmas Day',
    holidayType: 'PUBLIC',
    isOptional: false,
    calendarId: 'cal-1',
    calendarName: 'National Calendar',
    resolutionSource: 'LOCATION',
  );

  setUp(() {
    mockRepository = MockLeaveRepository();
  });

  group('LeaveBloc Tests', () {
    test('initial state has empty data and flags set to false', () {
      final bloc = LeaveBloc(repository: mockRepository);
      expect(bloc.state.isLoading, false);
      expect(bloc.state.isSubmitting, false);
      expect(bloc.state.balances, isEmpty);
      expect(bloc.state.myRequests, isEmpty);
      expect(bloc.state.upcomingHolidays, isEmpty);
    });

    blocTest<LeaveBloc, LeaveState>(
      'LeaveDashboardRequested fetches balances, types, requests, and holidays',
      build: () {
        when(() => mockRepository.getMyBalances())
            .thenAnswer((_) async => const Result.success([sampleBalance]));
        when(() => mockRepository.getLeaveTypes())
            .thenAnswer((_) async => const Result.success([sampleType]));
        when(() => mockRepository.getMyLeaveRequests(limit: 5))
            .thenAnswer((_) async => Result.success([sampleRequest]));
        when(() => mockRepository.getUpcomingHolidays(limit: 5))
            .thenAnswer((_) async => const Result.success([sampleHoliday]));
        return LeaveBloc(repository: mockRepository);
      },
      act: (bloc) => bloc.add(const LeaveDashboardRequested()),
      expect: () => [
        const LeaveState(isLoading: true),
        LeaveState(
          isLoading: false,
          balances: const [sampleBalance],
          leaveTypes: const [sampleType],
          myRequests: [sampleRequest],
          upcomingHolidays: const [sampleHoliday],
        ),
      ],
    );

    blocTest<LeaveBloc, LeaveState>(
      'LeaveApplicationSubmitted successfully applies leave and triggers balance refresh',
      build: () {
        when(() => mockRepository.applyLeave(
              leaveTypeId: 'lt-1',
              startDate: '2026-12-01',
              endDate: '2026-12-03',
              isHalfDay: false,
              halfDayPeriod: null,
              reason: 'Vacation',
            )).thenAnswer((_) async => Result.success(sampleRequest));
        when(() => mockRepository.getMyBalances())
            .thenAnswer((_) async => const Result.success([
                  LeaveBalance(
                    id: 'lb-1',
                    employeeId: 'emp-1',
                    leaveTypeId: 'lt-1',
                    leaveTypeCode: 'ANNUAL',
                    leaveTypeName: 'Annual Leave',
                    year: 2026,
                    annualAllocation: 15,
                    carriedForward: 0,
                    accrued: 0,
                    used: 2,
                    pendingApproval: 3,
                    availableBalance: 10,
                  )
                ]));
        return LeaveBloc(repository: mockRepository);
      },
      act: (bloc) => bloc.add(const LeaveApplicationSubmitted(
        leaveTypeId: 'lt-1',
        startDate: '2026-12-01',
        endDate: '2026-12-03',
        reason: 'Vacation',
      )),
      expect: () => [
        const LeaveState(isSubmitting: true),
        LeaveState(
          isSubmitting: false,
          myRequests: [sampleRequest],
          lastSubmittedRequest: sampleRequest,
          successNotice: 'Leave request submitted successfully',
        ),
        LeaveState(
          isSubmitting: false,
          myRequests: [sampleRequest],
          lastSubmittedRequest: sampleRequest,
          successNotice: 'Leave request submitted successfully',
          balances: const [
            LeaveBalance(
              id: 'lb-1',
              employeeId: 'emp-1',
              leaveTypeId: 'lt-1',
              leaveTypeCode: 'ANNUAL',
              leaveTypeName: 'Annual Leave',
              year: 2026,
              annualAllocation: 15,
              carriedForward: 0,
              accrued: 0,
              used: 2,
              pendingApproval: 3,
              availableBalance: 10,
            )
          ],
        ),
      ],
    );

    blocTest<LeaveBloc, LeaveState>(
      'LeaveApplicationSubmitted fails with error message on backend rejection',
      build: () {
        when(() => mockRepository.applyLeave(
              leaveTypeId: 'lt-1',
              startDate: '2026-12-01',
              endDate: '2026-12-03',
              isHalfDay: false,
              halfDayPeriod: null,
              reason: 'Vacation',
            )).thenAnswer((_) async => const Result.failure(
              ServerFailure(
                  'Insufficient leave balance for requested duration'),
            ));
        return LeaveBloc(repository: mockRepository);
      },
      act: (bloc) => bloc.add(const LeaveApplicationSubmitted(
        leaveTypeId: 'lt-1',
        startDate: '2026-12-01',
        endDate: '2026-12-03',
        reason: 'Vacation',
      )),
      expect: () => [
        const LeaveState(isSubmitting: true),
        const LeaveState(
          isSubmitting: false,
          errorMessage: 'Insufficient leave balance for requested duration',
        ),
      ],
    );

    blocTest<LeaveBloc, LeaveState>(
      'LeaveCancellationRequested updates request to CANCELLED',
      seed: () => LeaveState(
        myRequests: [sampleRequest],
        balances: const [sampleBalance],
      ),
      build: () {
        final cancelledRequest = LeaveRequest(
          id: 'lr-1',
          employeeId: 'emp-1',
          leaveTypeId: 'lt-1',
          startDate: '2026-12-01',
          endDate: '2026-12-03',
          isHalfDay: false,
          totalDays: 3,
          reason: 'Vacation',
          status: 'CANCELLED',
          createdAt: DateTime(2026, 11, 20),
        );

        when(() => mockRepository.cancelLeaveRequest('lr-1', reason: 'Change'))
            .thenAnswer((_) async => Result.success(cancelledRequest));
        when(() => mockRepository.getMyBalances())
            .thenAnswer((_) async => const Result.success([
                  LeaveBalance(
                    id: 'lb-1',
                    employeeId: 'emp-1',
                    leaveTypeId: 'lt-1',
                    leaveTypeCode: 'ANNUAL',
                    leaveTypeName: 'Annual Leave',
                    year: 2026,
                    annualAllocation: 15,
                    carriedForward: 0,
                    accrued: 0,
                    used: 0,
                    pendingApproval: 0,
                    availableBalance: 15,
                  )
                ]));
        return LeaveBloc(repository: mockRepository);
      },
      act: (bloc) => bloc.add(const LeaveCancellationRequested(
        requestId: 'lr-1',
        reason: 'Change',
      )),
      expect: () => [
        LeaveState(
          isSubmitting: true,
          myRequests: [sampleRequest],
          balances: const [sampleBalance],
        ),
        LeaveState(
          isSubmitting: false,
          myRequests: [
            LeaveRequest(
              id: 'lr-1',
              employeeId: 'emp-1',
              leaveTypeId: 'lt-1',
              startDate: '2026-12-01',
              endDate: '2026-12-03',
              isHalfDay: false,
              totalDays: 3,
              reason: 'Vacation',
              status: 'CANCELLED',
              createdAt: DateTime(2026, 11, 20),
            )
          ],
          balances: const [sampleBalance],
          successNotice: 'Leave request cancelled successfully',
        ),
        LeaveState(
          isSubmitting: false,
          myRequests: [
            LeaveRequest(
              id: 'lr-1',
              employeeId: 'emp-1',
              leaveTypeId: 'lt-1',
              startDate: '2026-12-01',
              endDate: '2026-12-03',
              isHalfDay: false,
              totalDays: 3,
              reason: 'Vacation',
              status: 'CANCELLED',
              createdAt: DateTime(2026, 11, 20),
            )
          ],
          balances: const [
            LeaveBalance(
              id: 'lb-1',
              employeeId: 'emp-1',
              leaveTypeId: 'lt-1',
              leaveTypeCode: 'ANNUAL',
              leaveTypeName: 'Annual Leave',
              year: 2026,
              annualAllocation: 15,
              carriedForward: 0,
              accrued: 0,
              used: 0,
              pendingApproval: 0,
              availableBalance: 15,
            )
          ],
          successNotice: 'Leave request cancelled successfully',
        ),
      ],
    );

    blocTest<LeaveBloc, LeaveState>(
      'SupervisorDecisionSubmitted approves request and updates supervisor queue',
      seed: () => LeaveState(
        supervisorQueue: [sampleRequest],
      ),
      build: () {
        final approvedRequest = LeaveRequest(
          id: 'lr-1',
          employeeId: 'emp-1',
          leaveTypeId: 'lt-1',
          startDate: '2026-12-01',
          endDate: '2026-12-03',
          isHalfDay: false,
          totalDays: 3,
          reason: 'Vacation',
          status: 'APPROVED',
          reviewerNotes: 'Approved by manager',
          createdAt: DateTime(2026, 11, 20),
        );

        when(() => mockRepository.adjudicateLeaveRequest(
              'lr-1',
              action: 'APPROVE',
              reason: 'Approved by manager',
            )).thenAnswer((_) async => Result.success(approvedRequest));
        return LeaveBloc(repository: mockRepository);
      },
      act: (bloc) => bloc.add(const SupervisorDecisionSubmitted(
        requestId: 'lr-1',
        action: 'APPROVE',
        reason: 'Approved by manager',
      )),
      expect: () => [
        LeaveState(
          isSubmitting: true,
          supervisorQueue: [sampleRequest],
        ),
        LeaveState(
          isSubmitting: false,
          supervisorQueue: [
            LeaveRequest(
              id: 'lr-1',
              employeeId: 'emp-1',
              leaveTypeId: 'lt-1',
              startDate: '2026-12-01',
              endDate: '2026-12-03',
              isHalfDay: false,
              totalDays: 3,
              reason: 'Vacation',
              status: 'APPROVED',
              reviewerNotes: 'Approved by manager',
              createdAt: DateTime(2026, 11, 20),
            )
          ],
          successNotice: 'Leave request approved successfully',
        ),
      ],
    );
  });
}
