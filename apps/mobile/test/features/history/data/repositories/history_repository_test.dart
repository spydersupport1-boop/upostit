import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:mobile/core/errors/failure.dart';
import 'package:mobile/features/attendance/data/models/attendance_day_model.dart';
import 'package:mobile/features/attendance/data/models/attendance_event_model.dart';
import 'package:mobile/features/attendance/data/models/shift_assignment_model.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_event.dart';
import 'package:mobile/features/history/data/datasources/history_remote_data_source.dart';
import 'package:mobile/features/history/data/repositories/history_repository_impl.dart';
import 'package:mobile/features/sync/domain/entities/local_queue_item.dart';
import 'package:mobile/features/sync/domain/entities/sync_status.dart';
import 'package:mobile/features/sync/domain/repositories/local_queue_dao.dart';

class MockHistoryRemoteDataSource extends Mock
    implements HistoryRemoteDataSource {}

class MockLocalQueueDao extends Mock implements LocalQueueDao {}

void main() {
  late MockHistoryRemoteDataSource mockRemoteDataSource;
  late MockLocalQueueDao mockQueueDao;
  late HistoryRepositoryImpl repository;

  final sampleDay = AttendanceDayModel(
    id: 'day-1',
    tenantId: 'tenant-1',
    employeeId: 'emp-1',
    attendanceDate: DateTime(2026, 11, 15),
    status: 'PRESENT',
    calculationStatus: 'CALCULATED',
    totalWorkingMinutes: 480,
    totalBreakMinutes: 60,
    netWorkingMinutes: 420,
    lateArrivalMinutes: 0,
    earlyDepartureMinutes: 0,
    lastCalculatedAt: DateTime(2026, 11, 15, 18, 0),
  );

  const sampleShift = ShiftAssignmentModel(
    id: 'shift-1',
    name: 'Day Shift',
    code: 'DAY',
    startTime: '09:00:00',
    endTime: '17:00:00',
    gracePeriodMinutes: 15,
    breakDurationMinutes: 60,
    isOvernight: false,
    isFlexible: false,
  );

  final sampleEvent = AttendanceEventModel(
    id: 'event-1',
    tenantId: 'tenant-1',
    employeeId: 'emp-1',
    eventType: AttendanceEventType.checkIn,
    eventCategory: 'PRESENCE',
    serverReceivedAt: DateTime.utc(2026, 11, 15, 9, 2),
    effectiveAt: DateTime.utc(2026, 11, 15, 9, 2),
    source: 'MOBILE_APP',
    timestampVerificationStatus: 'VERIFIED',
    reviewStatus: 'APPROVED',
    idempotencyKey: 'idemp-1',
    createdAt: DateTime.utc(2026, 11, 15, 9, 2),
  );

  setUp(() {
    mockRemoteDataSource = MockHistoryRemoteDataSource();
    mockQueueDao = MockLocalQueueDao();
    repository = HistoryRepositoryImpl(
      remoteDataSource: mockRemoteDataSource,
      queueDao: mockQueueDao,
      getTenantId: () => 'tenant-1',
      getUserId: () => 'user-1',
    );
  });

  group('HistoryRepository - getMonthlyAttendance', () {
    test('returns Result.success with days when remote succeeds', () async {
      when(() => mockRemoteDataSource.getMonthlyAttendanceDays(
            year: 2026,
            month: 11,
          )).thenAnswer((_) async => [sampleDay]);

      final result =
          await repository.getMonthlyAttendance(year: 2026, month: 11);

      expect(result.isSuccess, true);
      expect(result.data?.length, 1);
      expect(result.data?.first.id, 'day-1');
    });

    test('returns NetworkFailure when DioException is connection error',
        () async {
      when(() => mockRemoteDataSource.getMonthlyAttendanceDays(
            year: 2026,
            month: 11,
          )).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: '/'),
          type: DioExceptionType.connectionError,
        ),
      );

      final result =
          await repository.getMonthlyAttendance(year: 2026, month: 11);

      expect(result.isSuccess, false);
      expect(result.failure, isA<NetworkFailure>());
    });

    test('returns ServerFailure when server responds with 500', () async {
      when(() => mockRemoteDataSource.getMonthlyAttendanceDays(
            year: 2026,
            month: 11,
          )).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: '/'),
          response: Response(
            statusCode: 500,
            data: {'detail': 'Internal server error'},
            requestOptions: RequestOptions(path: '/'),
          ),
          type: DioExceptionType.badResponse,
        ),
      );

      final result =
          await repository.getMonthlyAttendance(year: 2026, month: 11);

      expect(result.isSuccess, false);
      expect(result.failure, isA<ServerFailure>());
    });
  });

  group('HistoryRepository - getDailyAttendanceDetail', () {
    test(
        'aggregates day, shift, events, and pending queue items for requested date',
        () async {
      final date = DateTime(2026, 11, 15);

      when(() => mockRemoteDataSource.getDayProjection(date: date))
          .thenAnswer((_) async => sampleDay);
      when(() => mockRemoteDataSource.getDayAuditEvents(date: date))
          .thenAnswer((_) async => [sampleEvent]);
      when(() => mockRemoteDataSource.getShiftAssignments(any()))
          .thenAnswer((_) async => [sampleShift]);

      final pendingItem = LocalQueueItem(
        localId: 'q-1',
        idempotencyKey: 'key-pending',
        tenantId: 'tenant-1',
        employeeId: 'emp-1',
        userId: 'user-1',
        eventType: AttendanceEventType.checkOut,
        appliedPolicyVersion: 1,
        appliedPolicyMode: 'NONE',
        sequenceNumber: 1,
        deviceReportedAt: DateTime.utc(2026, 11, 15, 17, 0),
        timezoneOffsetMinutes: 0,
        monotonicBootTimeMs: 1000,
        bootSessionId: 'boot-1',
        syncStatus: SyncStatus.pendingSync,
        createdAt: DateTime.utc(2026, 11, 15, 17, 0),
        updatedAt: DateTime.utc(2026, 11, 15, 17, 0),
      );

      when(() => mockQueueDao.getPendingEventsFifo(
            tenantId: 'tenant-1',
            userId: 'user-1',
            limit: 50,
          )).thenAnswer((_) async => [pendingItem]);

      final result = await repository.getDailyAttendanceDetail(date);

      expect(result.isSuccess, true);
      final detail = result.data!;
      expect(detail.date, date);
      expect(detail.dayRecord?.id, 'day-1');
      expect(detail.shift?.name, 'Day Shift');
      expect(detail.events.length, 1);
      expect(detail.pendingQueueItems.length, 1);
      expect(detail.hasPendingPunches, true);
      expect(detail.effectiveStatus, 'PENDING_SYNC');
    });
  });

  group('HistoryRepository - getShiftSchedule', () {
    test('returns Result.success with parsed shifts', () async {
      when(() => mockRemoteDataSource.getShiftAssignments())
          .thenAnswer((_) async => [sampleShift]);

      final result = await repository.getShiftSchedule();

      expect(result.isSuccess, true);
      expect(result.data?.length, 1);
      expect(result.data?.first.name, 'Day Shift');
      expect(result.data?.first.breakDurationMinutes, 60);
    });
  });
}
