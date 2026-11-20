import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:mobile/core/errors/app_exception.dart';
import 'package:mobile/core/errors/failure.dart';
import 'package:mobile/core/network/api_client.dart';
import 'package:mobile/core/network/api_endpoints.dart';
import 'package:mobile/features/leave/data/datasources/leave_remote_data_source.dart';
import 'package:mobile/features/leave/data/models/leave_balance_model.dart';
import 'package:mobile/features/leave/data/models/leave_request_model.dart';
import 'package:mobile/features/leave/data/models/leave_type_model.dart';
import 'package:mobile/features/leave/data/models/upcoming_holiday_model.dart';
import 'package:mobile/features/leave/data/repositories/leave_repository_impl.dart';
import 'package:mobile/features/leave/domain/entities/leave_request.dart';

class MockApiClient extends Mock implements ApiClient {}

class MockLeaveRemoteDataSource extends Mock
    implements LeaveRemoteDataSource {}

void main() {
  group('Leave Models & Invariants', () {
    test('LeaveTypeModel deserializes from JSON correctly', () {
      final json = {
        'id': 'lt-1',
        'code': 'ANNUAL',
        'name': 'Annual Paid Vacation',
        'is_paid': true,
        'requires_approval': true,
        'allow_half_day': true,
        'max_consecutive_days': 14,
        'carry_forward_limit': 5.0,
        'is_active': true,
      };

      final model = LeaveTypeModel.fromJson(json);

      expect(model.id, 'lt-1');
      expect(model.code, 'ANNUAL');
      expect(model.name, 'Annual Paid Vacation');
      expect(model.isPaid, true);
      expect(model.requiresApproval, true);
      expect(model.allowHalfDay, true);
      expect(model.maxConsecutiveDays, 14);
      expect(model.carryForwardLimit, 5.0);
      expect(model.isActive, true);
    });

    test('LeaveBalanceModel deserializes and computes availableBalance', () {
      final json = {
        'id': 'lb-1',
        'employee_id': 'emp-101',
        'leave_type_id': 'lt-1',
        'leave_type_code': 'ANNUAL',
        'leave_type_name': 'Annual Paid Leave',
        'year': 2026,
        'annual_allocation': 20.0,
        'carried_forward': 2.0,
        'accrued': 0.0,
        'used': 5.0,
        'pending_approval': 1.5,
        'available_balance': 15.5,
      };

      final model = LeaveBalanceModel.fromJson(json);

      expect(model.id, 'lb-1');
      expect(model.employeeId, 'emp-101');
      expect(model.leaveTypeCode, 'ANNUAL');
      expect(model.annualAllocation, 20.0);
      expect(model.carriedForward, 2.0);
      expect(model.used, 5.0);
      expect(model.pendingApproval, 1.5);
      expect(model.availableBalance, 15.5);
    });

    test('LeaveRequestModel deserializes from JSON and resolves properties', () {
      final json = {
        'id': 'lr-1',
        'employee_id': 'emp-101',
        'employee_name': 'Jane Doe',
        'leave_type_id': 'lt-1',
        'leave_type_code': 'ANNUAL',
        'leave_type_name': 'Annual Leave',
        'start_date': '2026-12-01',
        'end_date': '2026-12-05',
        'is_half_day': false,
        'half_day_period': null,
        'total_days': 5.0,
        'reason': 'Family vacation trip',
        'status': 'PENDING_APPROVAL',
        'reviewer_notes': null,
        'created_at': '2026-11-20T10:00:00Z',
      };

      final model = LeaveRequestModel.fromJson(json);

      expect(model.id, 'lr-1');
      expect(model.employeeId, 'emp-101');
      expect(model.employeeName, 'Jane Doe');
      expect(model.leaveTypeCode, 'ANNUAL');
      expect(model.isPending, true);
      expect(model.isApproved, false);
      expect(model.isRejected, false);
      expect(model.isCancelled, false);
      expect(model.totalDays, 5.0);
      expect(model.startDateTime.year, 2026);
      expect(model.startDateTime.month, 12);
      expect(model.startDateTime.day, 1);
    });

    test('UpcomingHolidayModel deserializes correctly', () {
      final json = {
        'id': 'hol-1',
        'holiday_date': '2026-12-25',
        'name': 'Christmas Day',
        'holiday_type': 'PUBLIC',
        'is_optional': false,
        'calendar_id': 'cal-1',
        'calendar_name': 'National Holidays',
        'resolution_source': 'LOCATION',
      };

      final model = UpcomingHolidayModel.fromJson(json);

      expect(model.id, 'hol-1');
      expect(model.holidayDate, '2026-12-25');
      expect(model.name, 'Christmas Day');
      expect(model.isPublic, true);
      expect(model.isOptional, false);
      expect(model.calendarName, 'National Holidays');
      expect(model.resolutionSource, 'LOCATION');
      expect(model.date.month, 12);
      expect(model.date.day, 25);
    });

    group('LeaveRequest canCancel() Business Invariants', () {
      final today = DateTime(2026, 11, 20);

      test('Pending request can always be cancelled', () {
        final req = LeaveRequest(
          id: '1',
          employeeId: 'emp-1',
          leaveTypeId: 'lt-1',
          startDate: '2026-11-15',
          endDate: '2026-11-16',
          isHalfDay: false,
          totalDays: 2,
          reason: 'Reason',
          status: 'PENDING_APPROVAL',
          createdAt: DateTime.now(),
        );

        expect(req.canCancel(today), true);
      });

      test('Approved future-dated request can be cancelled', () {
        final req = LeaveRequest(
          id: '2',
          employeeId: 'emp-1',
          leaveTypeId: 'lt-1',
          startDate: '2026-11-25',
          endDate: '2026-11-26',
          isHalfDay: false,
          totalDays: 2,
          reason: 'Reason',
          status: 'APPROVED',
          createdAt: DateTime.now(),
        );

        expect(req.canCancel(today), true);
      });

      test('Approved commenced or past request CANNOT be cancelled', () {
        final reqCommencedToday = LeaveRequest(
          id: '3',
          employeeId: 'emp-1',
          leaveTypeId: 'lt-1',
          startDate: '2026-11-20',
          endDate: '2026-11-21',
          isHalfDay: false,
          totalDays: 2,
          reason: 'Reason',
          status: 'APPROVED',
          createdAt: DateTime.now(),
        );

        final reqPast = LeaveRequest(
          id: '4',
          employeeId: 'emp-1',
          leaveTypeId: 'lt-1',
          startDate: '2026-11-10',
          endDate: '2026-11-12',
          isHalfDay: false,
          totalDays: 3,
          reason: 'Reason',
          status: 'APPROVED',
          createdAt: DateTime.now(),
        );

        expect(reqCommencedToday.canCancel(today), false);
        expect(reqPast.canCancel(today), false);
      });

      test('Rejected or Cancelled requests can never be cancelled', () {
        final reqRejected = LeaveRequest(
          id: '5',
          employeeId: 'emp-1',
          leaveTypeId: 'lt-1',
          startDate: '2026-12-01',
          endDate: '2026-12-02',
          isHalfDay: false,
          totalDays: 2,
          reason: 'Reason',
          status: 'REJECTED',
          createdAt: DateTime.now(),
        );

        final reqCancelled = LeaveRequest(
          id: '6',
          employeeId: 'emp-1',
          leaveTypeId: 'lt-1',
          startDate: '2026-12-01',
          endDate: '2026-12-02',
          isHalfDay: false,
          totalDays: 2,
          reason: 'Reason',
          status: 'CANCELLED',
          createdAt: DateTime.now(),
        );

        expect(reqRejected.canCancel(today), false);
        expect(reqCancelled.canCancel(today), false);
      });
    });
  });

  group('Leave Remote Data Source & Repository', () {
    late MockApiClient mockApiClient;
    late LeaveRemoteDataSourceImpl dataSource;
    late MockLeaveRemoteDataSource mockRemoteDataSource;
    late LeaveRepositoryImpl repository;

    const sampleBalanceModel = LeaveBalanceModel(
      id: 'b-1',
      employeeId: 'emp-101',
      leaveTypeId: 'lt-1',
      leaveTypeCode: 'ANNUAL',
      leaveTypeName: 'Annual Leave',
      year: 2026,
      annualAllocation: 15.0,
      carriedForward: 0.0,
      accrued: 0.0,
      used: 2.0,
      pendingApproval: 0.0,
      availableBalance: 13.0,
    );

    final sampleRequestModel = LeaveRequestModel(
      id: 'req-99',
      employeeId: 'emp-1',
      leaveTypeId: 'lt-1',
      leaveTypeCode: 'ANNUAL',
      startDate: '2026-11-25',
      endDate: '2026-11-26',
      isHalfDay: false,
      totalDays: 2.0,
      reason: 'Medical checkup',
      status: 'PENDING_APPROVAL',
      createdAt: DateTime.now(),
    );

    setUp(() {
      mockApiClient = MockApiClient();
      dataSource = LeaveRemoteDataSourceImpl(mockApiClient);
      mockRemoteDataSource = MockLeaveRemoteDataSource();
      repository = LeaveRepositoryImpl(mockRemoteDataSource);
    });

    test('LeaveRemoteDataSourceImpl.getMyBalances parses API response', () async {
      when(() => mockApiClient.get<Map<String, dynamic>>(any()))
          .thenAnswer((_) async => Response(
                requestOptions: RequestOptions(path: ApiEndpoints.leaveBalancesMy),
                data: {
                  'success': true,
                  'data': [
                    {
                      'id': 'b-1',
                      'employee_id': 'emp-101',
                      'leave_type_id': 'lt-1',
                      'leave_type_code': 'ANNUAL',
                      'annual_allocation': 15.0,
                      'carried_forward': 0.0,
                      'accrued': 0.0,
                      'used': 2.0,
                      'pending_approval': 0.0,
                      'available_balance': 13.0,
                    }
                  ]
                },
                statusCode: 200,
              ));

      final balances = await dataSource.getMyBalances();

      expect(balances.length, 1);
      expect(balances.first.leaveTypeCode, 'ANNUAL');
      expect(balances.first.availableBalance, 13.0);
    });

    test('LeaveRepositoryImpl.getMyBalances returns success Result', () async {
      when(() => mockRemoteDataSource.getMyBalances())
          .thenAnswer((_) async => [sampleBalanceModel]);

      final result = await repository.getMyBalances();

      expect(result.isSuccess, true);
      expect(result.value.length, 1);
      expect(result.value.first.leaveTypeCode, 'ANNUAL');
    });

    test('LeaveRepositoryImpl.applyLeave returns created request', () async {
      when(() => mockRemoteDataSource.applyLeave(
            leaveTypeId: 'lt-1',
            startDate: '2026-11-25',
            endDate: '2026-11-26',
            isHalfDay: false,
            halfDayPeriod: null,
            reason: 'Medical checkup',
          )).thenAnswer((_) async => sampleRequestModel);

      final result = await repository.applyLeave(
        leaveTypeId: 'lt-1',
        startDate: '2026-11-25',
        endDate: '2026-11-26',
        reason: 'Medical checkup',
      );

      expect(result.isSuccess, true);
      expect(result.value.id, 'req-99');
      expect(result.value.status, 'PENDING_APPROVAL');
    });

    test('LeaveRepositoryImpl.cancelLeaveRequest maps ServerException to ServerFailure',
        () async {
      when(() => mockRemoteDataSource.cancelLeaveRequest(
            'req-99',
            reason: 'Changed mind',
          )).thenThrow(
        const ServerException(
          'Only pending or future approved leaves may be cancelled.',
          statusCode: 400,
        ),
      );

      final result = await repository.cancelLeaveRequest(
        'req-99',
        reason: 'Changed mind',
      );

      expect(result.isFailure, true);
      expect(result.error, isA<ServerFailure>());
      expect(
        result.error.message,
        'Only pending or future approved leaves may be cancelled.',
      );
    });

    test('LeaveRepositoryImpl.adjudicateLeaveRequest returns updated request',
        () async {
      final approved = LeaveRequestModel(
        id: 'req-10',
        employeeId: 'emp-2',
        leaveTypeId: 'lt-1',
        startDate: '2026-12-01',
        endDate: '2026-12-02',
        isHalfDay: false,
        totalDays: 2.0,
        reason: 'Vacation',
        status: 'APPROVED',
        reviewerNotes: 'Approved by manager',
        createdAt: DateTime.now(),
      );

      when(() => mockRemoteDataSource.adjudicateLeaveRequest(
            'req-10',
            action: 'APPROVE',
            reason: 'Approved by manager',
          )).thenAnswer((_) async => approved);

      final result = await repository.adjudicateLeaveRequest(
        'req-10',
        action: 'APPROVE',
        reason: 'Approved by manager',
      );

      expect(result.isSuccess, true);
      expect(result.value.status, 'APPROVED');
      expect(result.value.reviewerNotes, 'Approved by manager');
    });
  });
}
