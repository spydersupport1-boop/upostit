import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:mobile/core/errors/failure.dart';
import 'package:mobile/features/attendance/data/datasources/attendance_remote_data_source.dart';
import 'package:mobile/features/attendance/data/models/attendance_day_model.dart';
import 'package:mobile/features/attendance/data/models/attendance_event_model.dart';
import 'package:mobile/features/attendance/data/models/employee_wifi_verify_model.dart';
import 'package:mobile/features/attendance/data/models/punch_request_model.dart';
import 'package:mobile/features/attendance/data/models/punch_response_model.dart';
import 'package:mobile/features/attendance/data/repositories/attendance_repository_impl.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_event.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_status.dart';
import 'package:mobile/features/attendance/domain/entities/wifi_verification_result.dart';

class MockAttendanceRemoteDataSource extends Mock
    implements AttendanceRemoteDataSource {}

void main() {
  late MockAttendanceRemoteDataSource mockRemoteDataSource;
  late AttendanceRepositoryImpl repository;

  setUpAll(() {
    registerFallbackValue(
      const PunchRequestModel(
        eventType: AttendanceEventType.checkIn,
        idempotencyKey: 'fallback-key',
      ),
    );
    registerFallbackValue(
      const EmployeeWifiVerifyRequestModel(
        locationId: 'fallback-loc',
      ),
    );
  });

  setUp(() {
    mockRemoteDataSource = MockAttendanceRemoteDataSource();
    repository = AttendanceRepositoryImpl(mockRemoteDataSource);
  });

  final dummyEvent = AttendanceEventModel(
    id: 'evt-1',
    tenantId: 'tenant-1',
    employeeId: 'emp-1',
    eventType: AttendanceEventType.checkIn,
    eventCategory: 'STANDARD',
    serverReceivedAt: DateTime.utc(2026, 11, 4, 9, 0, 0),
    effectiveAt: DateTime.utc(2026, 11, 4, 9, 0, 0),
    source: 'MOBILE',
    timestampVerificationStatus: 'SERVER_AUTHORITATIVE',
    reviewStatus: 'NOT_REQUIRED',
    idempotencyKey: 'idem-1',
    createdAt: DateTime.utc(2026, 11, 4, 9, 0, 0),
  );

  group('recordPunch', () {
    test('returns PunchResult on successful punch', () async {
      when(() => mockRemoteDataSource.recordPunch(any())).thenAnswer(
        (_) async => PunchResponseModel(
          event: dummyEvent,
          additionalEvents: const [],
          isIdempotentReplay: false,
        ),
      );

      final result = await repository.recordPunch(
        eventType: AttendanceEventType.checkIn,
        idempotencyKey: 'idem-test-1234',
      );

      expect(result.isSuccess, isTrue);
      expect(result.data?.event.id, equals('evt-1'));
      verify(() => mockRemoteDataSource.recordPunch(any())).called(1);
    });

    test(
        'returns ServerFailure with server error detail when rejected with HTTP 400',
        () async {
      when(() => mockRemoteDataSource.recordPunch(any())).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: '/api/v1/attendance/punch'),
          response: Response(
            requestOptions: RequestOptions(path: '/api/v1/attendance/punch'),
            statusCode: 400,
            data: {'detail': 'Employee is already checked in.'},
          ),
        ),
      );

      final result = await repository.recordPunch(
        eventType: AttendanceEventType.checkIn,
        idempotencyKey: 'idem-test-1234',
      );

      expect(result.isSuccess, isFalse);
      expect(result.failure, isA<ServerFailure>());
      expect(
          result.failure?.message, equals('Employee is already checked in.'));
      expect(result.failure?.statusCode, equals(400));
    });

    test('returns NetworkFailure when connection times out', () async {
      when(() => mockRemoteDataSource.recordPunch(any())).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: '/api/v1/attendance/punch'),
          type: DioExceptionType.connectionTimeout,
        ),
      );

      final result = await repository.recordPunch(
        eventType: AttendanceEventType.checkIn,
        idempotencyKey: 'idem-test-1234',
      );

      expect(result.isSuccess, isFalse);
      expect(result.failure, isA<NetworkFailure>());
    });

    test('submits Wi-Fi evidence fields in punch request', () async {
      PunchRequestModel? capturedRequest;
      when(() => mockRemoteDataSource.recordPunch(any()))
          .thenAnswer((invocation) async {
        capturedRequest =
            invocation.positionalArguments.first as PunchRequestModel;
        return PunchResponseModel(
          event: dummyEvent,
          additionalEvents: const [],
          isIdempotentReplay: false,
        );
      });

      final result = await repository.recordPunch(
        eventType: AttendanceEventType.checkIn,
        idempotencyKey: 'wifi-punch-test-1',
        locationId: 'loc-1',
        wifiBssid: 'AA:BB:CC:DD:EE:01',
        wifiSsid: 'Corp-WiFi',
        wifiSignalStatus: 'AVAILABLE',
      );

      expect(result.isSuccess, isTrue);
      expect(capturedRequest?.wifiBssid, equals('AA:BB:CC:DD:EE:01'));
      expect(capturedRequest?.wifiSsid, equals('Corp-WiFi'));
      expect(capturedRequest?.wifiSignalStatus, equals('AVAILABLE'));
    });
  });

  group('verifyWorkplaceWifi', () {
    test('returns WifiVerificationResult on successful probe', () async {
      when(() => mockRemoteDataSource.verifyWorkplaceWifi(any()))
          .thenAnswer((_) async => const EmployeeWifiVerifyResponseModel(
                locationId: 'loc-1',
                locationName: 'Corporate HQ',
                locationCode: 'HQ-1',
                reportedBssid: 'AA:BB:CC:DD:EE:01',
                matchStatus: WifiMatchStatus.matched,
                isVerified: true,
                matchedAccessPointName: 'Main-AP',
                message: 'Connected to authorized workplace access point.',
              ));

      final result = await repository.verifyWorkplaceWifi(
        locationId: 'loc-1',
        bssid: 'AA:BB:CC:DD:EE:01',
        ssid: 'Corp-WiFi',
        signalStatus: 'AVAILABLE',
      );

      expect(result.isSuccess, isTrue);
      expect(result.data?.isVerified, isTrue);
      expect(result.data?.matchStatus, equals(WifiMatchStatus.matched));
      expect(result.data?.matchedAccessPointName, equals('Main-AP'));
    });

    test(
        'returns ServerFailure when probe is rejected with HTTP 403 unassigned',
        () async {
      when(() => mockRemoteDataSource.verifyWorkplaceWifi(any())).thenThrow(
        DioException(
          requestOptions: RequestOptions(
              path: '/api/v1/employees/me/workplaces/verify-wifi'),
          response: Response(
            requestOptions: RequestOptions(
                path: '/api/v1/employees/me/workplaces/verify-wifi'),
            statusCode: 403,
            data: {'detail': 'Workplace is not assigned to current employee.'},
          ),
        ),
      );

      final result = await repository.verifyWorkplaceWifi(
        locationId: 'loc-unassigned',
        bssid: 'AA:BB:CC:DD:EE:01',
      );

      expect(result.isSuccess, isFalse);
      expect(result.failure, isA<ServerFailure>());
      expect(result.failure?.statusCode, equals(403));
      expect(result.failure?.message, contains('Workplace is not assigned'));
    });
  });

  group('getTodayAttendanceDashboard', () {
    test('derives notCheckedIn status when no events recorded today', () async {
      when(() => mockRemoteDataSource.getAttendanceDay(any()))
          .thenAnswer((_) async => null);
      when(() => mockRemoteDataSource.getAttendanceEvents(
            startDate: any(named: 'startDate'),
            endDate: any(named: 'endDate'),
          )).thenAnswer((_) async => []);
      when(() => mockRemoteDataSource.getShiftAssignments(any()))
          .thenAnswer((_) async => []);
      when(() => mockRemoteDataSource.getMyWorkplaces())
          .thenAnswer((_) async => []);

      final result = await repository.getTodayAttendanceDashboard();

      expect(result.isSuccess, isTrue);
      expect(result.data?.status, equals(AttendanceStatus.notCheckedIn));
      expect(result.data?.todayEvents, isEmpty);
      expect(result.data?.lastEvent, isNull);
    });

    test('derives working status when last event is CHECK_IN or BREAK_END',
        () async {
      when(() => mockRemoteDataSource.getAttendanceDay(any())).thenAnswer(
        (_) async => AttendanceDayModel(
          id: 'day-1',
          tenantId: 'tenant-1',
          employeeId: 'emp-1',
          attendanceDate: DateTime.utc(2026, 11, 4),
          totalWorkingMinutes: 60,
          totalBreakMinutes: 0,
          netWorkingMinutes: 60,
          status: 'PRESENT',
          calculationStatus: 'CALCULATED',
          lastCalculatedAt: DateTime.utc(2026, 11, 4, 10, 0, 0),
        ),
      );
      when(() => mockRemoteDataSource.getAttendanceEvents(
            startDate: any(named: 'startDate'),
            endDate: any(named: 'endDate'),
          )).thenAnswer((_) async => [dummyEvent]);
      when(() => mockRemoteDataSource.getShiftAssignments(any()))
          .thenAnswer((_) async => []);
      when(() => mockRemoteDataSource.getMyWorkplaces())
          .thenAnswer((_) async => []);

      final result = await repository.getTodayAttendanceDashboard();

      expect(result.isSuccess, isTrue);
      expect(result.data?.status, equals(AttendanceStatus.working));
      expect(result.data?.lastEvent?.eventType,
          equals(AttendanceEventType.checkIn));
    });

    test('derives onBreak status when last event is BREAK_START', () async {
      final breakStartEvent = AttendanceEventModel(
        id: 'evt-2',
        tenantId: 'tenant-1',
        employeeId: 'emp-1',
        eventType: AttendanceEventType.breakStart,
        eventCategory: 'STANDARD',
        serverReceivedAt: DateTime.utc(2026, 11, 4, 12, 0, 0),
        effectiveAt: DateTime.utc(2026, 11, 4, 12, 0, 0),
        source: 'MOBILE',
        timestampVerificationStatus: 'SERVER_AUTHORITATIVE',
        reviewStatus: 'NOT_REQUIRED',
        idempotencyKey: 'idem-2',
        createdAt: DateTime.utc(2026, 11, 4, 12, 0, 0),
      );

      when(() => mockRemoteDataSource.getAttendanceDay(any()))
          .thenAnswer((_) async => null);
      when(() => mockRemoteDataSource.getAttendanceEvents(
            startDate: any(named: 'startDate'),
            endDate: any(named: 'endDate'),
          )).thenAnswer((_) async => [dummyEvent, breakStartEvent]);
      when(() => mockRemoteDataSource.getShiftAssignments(any()))
          .thenAnswer((_) async => []);
      when(() => mockRemoteDataSource.getMyWorkplaces())
          .thenAnswer((_) async => []);

      final result = await repository.getTodayAttendanceDashboard();

      expect(result.isSuccess, isTrue);
      expect(result.data?.status, equals(AttendanceStatus.onBreak));
      expect(result.data?.lastEvent?.eventType,
          equals(AttendanceEventType.breakStart));
    });

    test('derives completed status when last event is CHECK_OUT', () async {
      final checkOutEvent = AttendanceEventModel(
        id: 'evt-3',
        tenantId: 'tenant-1',
        employeeId: 'emp-1',
        eventType: AttendanceEventType.checkOut,
        eventCategory: 'STANDARD',
        serverReceivedAt: DateTime.utc(2026, 11, 4, 18, 0, 0),
        effectiveAt: DateTime.utc(2026, 11, 4, 18, 0, 0),
        source: 'MOBILE',
        timestampVerificationStatus: 'SERVER_AUTHORITATIVE',
        reviewStatus: 'NOT_REQUIRED',
        idempotencyKey: 'idem-3',
        createdAt: DateTime.utc(2026, 11, 4, 18, 0, 0),
      );

      when(() => mockRemoteDataSource.getAttendanceDay(any()))
          .thenAnswer((_) async => null);
      when(() => mockRemoteDataSource.getAttendanceEvents(
            startDate: any(named: 'startDate'),
            endDate: any(named: 'endDate'),
          )).thenAnswer((_) async => [dummyEvent, checkOutEvent]);
      when(() => mockRemoteDataSource.getShiftAssignments(any()))
          .thenAnswer((_) async => []);
      when(() => mockRemoteDataSource.getMyWorkplaces())
          .thenAnswer((_) async => []);

      final result = await repository.getTodayAttendanceDashboard();

      expect(result.isSuccess, isTrue);
      expect(result.data?.status, equals(AttendanceStatus.completed));
      expect(result.data?.lastEvent?.eventType,
          equals(AttendanceEventType.checkOut));
    });

    test(
        'returns NetworkFailure when attendance days fetch fails due to connectivity',
        () async {
      when(() => mockRemoteDataSource.getAttendanceDay(any())).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: '/api/v1/attendance/days'),
          type: DioExceptionType.connectionError,
        ),
      );

      final result = await repository.getTodayAttendanceDashboard();

      expect(result.isSuccess, isFalse);
      expect(result.failure, isA<NetworkFailure>());
    });

    test(
        'gracefully handles shift and workplace errors without failing dashboard',
        () async {
      when(() => mockRemoteDataSource.getAttendanceDay(any()))
          .thenAnswer((_) async => null);
      when(() => mockRemoteDataSource.getAttendanceEvents(
            startDate: any(named: 'startDate'),
            endDate: any(named: 'endDate'),
          )).thenAnswer((_) async => [dummyEvent]);
      // Shift and workplace endpoints throw errors
      when(() => mockRemoteDataSource.getShiftAssignments(any()))
          .thenThrow(Exception('Shifts unavailable'));
      when(() => mockRemoteDataSource.getMyWorkplaces())
          .thenThrow(Exception('Workplaces unavailable'));

      final result = await repository.getTodayAttendanceDashboard();

      expect(result.isSuccess, isTrue);
      expect(result.data?.status, equals(AttendanceStatus.working));
      expect(result.data?.shift, isNull);
      expect(result.data?.workplace, isNull);
    });
  });
}
