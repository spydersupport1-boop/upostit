import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:mobile/core/network/api_client.dart';
import 'package:mobile/core/network/api_endpoints.dart';
import 'package:mobile/features/attendance/data/models/attendance_day_model.dart';
import 'package:mobile/features/attendance/data/models/shift_assignment_model.dart';
import 'package:mobile/features/history/data/datasources/history_remote_data_source.dart';

class MockApiClient extends Mock implements ApiClient {}

void main() {
  late MockApiClient mockApiClient;
  late HistoryRemoteDataSourceImpl dataSource;

  setUp(() {
    mockApiClient = MockApiClient();
    dataSource = HistoryRemoteDataSourceImpl(mockApiClient);
  });

  group('HistoryRemoteDataSource - getMonthlyAttendanceDays', () {
    test('fetches monthly attendance days with correct date range query params',
        () async {
      final mockDaysResponse = [
        {
          'id': 'day-1',
          'tenant_id': 't-1',
          'employee_id': 'emp-1',
          'work_date': '2026-11-01',
          'status': 'PRESENT',
          'effective_shift_id': 'shift-1',
          'first_check_in_at': '2026-11-01T09:00:00Z',
          'last_check_out_at': '2026-11-01T17:00:00Z',
          'total_work_minutes': 480,
          'total_break_minutes': 60,
          'late_arrival_minutes': 0,
          'early_departure_minutes': 0,
          'is_overnight': false,
          'calculation_version': 1,
          'needs_recalculation': false,
          'calculated_at': '2026-11-01T17:05:00Z',
        },
        {
          'id': 'day-2',
          'tenant_id': 't-1',
          'employee_id': 'emp-1',
          'work_date': '2026-11-02',
          'status': 'LATE',
          'effective_shift_id': 'shift-1',
          'first_check_in_at': '2026-11-02T09:25:00Z',
          'last_check_out_at': '2026-11-02T17:30:00Z',
          'total_work_minutes': 485,
          'total_break_minutes': 60,
          'late_arrival_minutes': 25,
          'early_departure_minutes': 0,
          'is_overnight': false,
          'calculation_version': 1,
          'needs_recalculation': false,
          'calculated_at': '2026-11-02T17:35:00Z',
        },
      ];

      when(() => mockApiClient.get(
            ApiEndpoints.attendanceDays,
            queryParameters: any(named: 'queryParameters'),
          )).thenAnswer(
        (_) async => Response(
          data: mockDaysResponse,
          statusCode: 200,
          requestOptions: RequestOptions(path: ApiEndpoints.attendanceDays),
        ),
      );

      final result =
          await dataSource.getMonthlyAttendanceDays(year: 2026, month: 11);

      expect(result.length, 2);
      expect(result[0], isA<AttendanceDayModel>());
      expect(result[0].status, 'PRESENT');
      expect(result[1].lateArrivalMinutes, 25);

      verify(() => mockApiClient.get(
            ApiEndpoints.attendanceDays,
            queryParameters: {
              'start_date': '2026-11-01',
              'end_date': '2026-11-30',
              'limit': 100,
            },
          )).called(1);
    });

    test('rethrows DioException on network error', () async {
      when(() => mockApiClient.get(
            ApiEndpoints.attendanceDays,
            queryParameters: any(named: 'queryParameters'),
          )).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: ApiEndpoints.attendanceDays),
          type: DioExceptionType.connectionError,
        ),
      );

      expect(
        () => dataSource.getMonthlyAttendanceDays(year: 2026, month: 11),
        throwsA(isA<DioException>()),
      );
    });
  });

  group('HistoryRemoteDataSource - getDayAuditEvents', () {
    test('fetches day events and returns chronologically sorted list',
        () async {
      final mockEvents = [
        {
          'id': 'ev-2',
          'tenant_id': 't-1',
          'employee_id': 'emp-1',
          'event_type': 'CHECK_OUT',
          'event_category': 'PRESENCE',
          'server_received_at': '2026-11-01T17:00:00Z',
          'effective_at': '2026-11-01T17:00:00Z',
          'source': 'MOBILE_APP',
          'timestamp_verification_status': 'VERIFIED',
          'review_status': 'APPROVED',
          'idempotency_key': 'key-out',
          'created_at': '2026-11-01T17:00:00Z',
        },
        {
          'id': 'ev-1',
          'tenant_id': 't-1',
          'employee_id': 'emp-1',
          'event_type': 'CHECK_IN',
          'event_category': 'PRESENCE',
          'server_received_at': '2026-11-01T09:00:00Z',
          'effective_at': '2026-11-01T09:00:00Z',
          'source': 'MOBILE_APP',
          'timestamp_verification_status': 'VERIFIED',
          'review_status': 'APPROVED',
          'idempotency_key': 'key-in',
          'created_at': '2026-11-01T09:00:00Z',
        },
      ];

      when(() => mockApiClient.get(
            ApiEndpoints.attendanceEvents,
            queryParameters: any(named: 'queryParameters'),
          )).thenAnswer(
        (_) async => Response(
          data: mockEvents,
          statusCode: 200,
          requestOptions: RequestOptions(path: ApiEndpoints.attendanceEvents),
        ),
      );

      final date = DateTime(2026, 11, 1);
      final result = await dataSource.getDayAuditEvents(date: date);

      expect(result.length, 2);
      expect(result[0].id, 'ev-1'); // sorted first
      expect(result[1].id, 'ev-2');
    });
  });

  group('HistoryRemoteDataSource - getShiftAssignments', () {
    test('fetches shift assignments with parsed operational timing fields',
        () async {
      final mockShiftResponse = [
        {
          'id': 'sa-1',
          'tenant_id': 't-1',
          'employee_id': 'emp-1',
          'shift_template_id': 'st-1',
          'shift_name': 'Standard Morning',
          'shift_code': 'MORNING',
          'start_time': '09:00:00',
          'end_time': '17:00:00',
          'grace_period_minutes': 15,
          'break_duration_minutes': 60,
          'is_overnight': false,
          'is_flexible': false,
          'weekly_off_days': [5, 6],
          'effective_from': '2026-01-01',
          'effective_to': null,
        }
      ];

      when(() => mockApiClient.get(
            ApiEndpoints.shiftAssignments,
            queryParameters: any(named: 'queryParameters'),
          )).thenAnswer(
        (_) async => Response(
          data: mockShiftResponse,
          statusCode: 200,
          requestOptions: RequestOptions(path: ApiEndpoints.shiftAssignments),
        ),
      );

      final result = await dataSource.getShiftAssignments();

      expect(result.length, 1);
      expect(result[0], isA<ShiftAssignmentModel>());
      expect(result[0].name, 'Standard Morning');
      expect(result[0].startTime, '09:00:00');
      expect(result[0].breakDurationMinutes, 60);
      expect(result[0].weeklyOffDays, [5, 6]);
    });
  });
}
