import 'package:dio/dio.dart';
import 'package:mobile/core/errors/failure.dart';
import 'package:mobile/core/errors/result.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_day.dart';
import 'package:mobile/features/attendance/domain/entities/today_shift.dart';
import 'package:mobile/features/history/data/datasources/history_remote_data_source.dart';
import 'package:mobile/features/history/domain/entities/daily_attendance_detail.dart';
import 'package:mobile/features/history/domain/repositories/history_repository.dart';
import 'package:mobile/features/sync/domain/entities/local_queue_item.dart';
import 'package:mobile/features/sync/domain/repositories/local_queue_dao.dart';

class HistoryRepositoryImpl implements HistoryRepository {
  final HistoryRemoteDataSource _remoteDataSource;
  final LocalQueueDao? _queueDao;
  final String? Function()? _getTenantId;
  final String? Function()? _getUserId;

  HistoryRepositoryImpl({
    required HistoryRemoteDataSource remoteDataSource,
    LocalQueueDao? queueDao,
    String? Function()? getTenantId,
    String? Function()? getUserId,
  })  : _remoteDataSource = remoteDataSource,
        _queueDao = queueDao,
        _getTenantId = getTenantId,
        _getUserId = getUserId;

  @override
  Future<Result<List<AttendanceDay>>> getMonthlyAttendance({
    required int year,
    required int month,
  }) async {
    try {
      final days = await _remoteDataSource.getMonthlyAttendanceDays(
        year: year,
        month: month,
      );
      days.sort((a, b) => a.attendanceDate.compareTo(b.attendanceDate));
      return Result.success(days);
    } on DioException catch (dioError) {
      return Result.failure(_mapDioError(dioError));
    } catch (e) {
      return Result.failure(ServerFailure(e.toString()));
    }
  }

  @override
  Future<Result<DailyAttendanceDetail>> getDailyAttendanceDetail(
    DateTime date, {
    AttendanceDay? preloadedDay,
  }) async {
    try {
      // 1. Resolve Day Projection (use preloaded if matching, or fetch)
      final AttendanceDay? day;
      if (preloadedDay != null &&
          preloadedDay.attendanceDate.year == date.year &&
          preloadedDay.attendanceDate.month == date.month &&
          preloadedDay.attendanceDate.day == date.day) {
        day = preloadedDay;
      } else {
        day = await _remoteDataSource.getDayProjection(date: date);
      }

      // 2. Fetch raw event audit ledger for that day
      final events = await _remoteDataSource.getDayAuditEvents(date: date);

      // 3. Resolve shift for that day if shift assignment exists
      TodayShift? shift;
      try {
        final shifts = await _remoteDataSource.getShiftAssignments(
          '${date.year.toString().padLeft(4, '0')}-${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}',
        );
        if (shifts.isNotEmpty) {
          shift = shifts.first;
        }
      } catch (_) {}

      // 4. Check for any pending local queue punches recorded on this calendar date
      List<LocalQueueItem> localPending = const [];
      if (_queueDao != null && _getTenantId != null && _getUserId != null) {
        final tId = _getTenantId();
        final uId = _getUserId();
        if (tId != null && uId != null) {
          try {
            final allPending = await _queueDao.getPendingEventsFifo(
              tenantId: tId,
              userId: uId,
              limit: 50,
            );
            localPending = allPending.where((p) {
              return p.deviceReportedAt.year == date.year &&
                  p.deviceReportedAt.month == date.month &&
                  p.deviceReportedAt.day == date.day;
            }).toList();
          } catch (_) {}
        }
      }

      return Result.success(
        DailyAttendanceDetail(
          date: date,
          dayRecord: day,
          shift: shift,
          events: events,
          pendingQueueItems: localPending,
        ),
      );
    } on DioException catch (dioError) {
      return Result.failure(_mapDioError(dioError));
    } catch (e) {
      return Result.failure(ServerFailure(e.toString()));
    }
  }

  @override
  Future<Result<List<TodayShift>>> getShiftSchedule() async {
    try {
      final shifts = await _remoteDataSource.getShiftAssignments();
      return Result.success(shifts);
    } on DioException catch (dioError) {
      return Result.failure(_mapDioError(dioError));
    } catch (e) {
      return Result.failure(ServerFailure(e.toString()));
    }
  }

  Failure _mapDioError(DioException dioError) {
    if (dioError.type == DioExceptionType.connectionTimeout ||
        dioError.type == DioExceptionType.sendTimeout ||
        dioError.type == DioExceptionType.receiveTimeout ||
        dioError.type == DioExceptionType.connectionError) {
      return const NetworkFailure(
          'Unable to connect to server. Please check your network connection.');
    }

    final responseData = dioError.response?.data;
    String errorMessage = 'A server error occurred. Please try again.';

    if (responseData is Map<String, dynamic>) {
      if (responseData['detail'] != null) {
        final detail = responseData['detail'];
        if (detail is String) {
          errorMessage = detail;
        } else if (detail is List && detail.isNotEmpty) {
          final first = detail.first;
          if (first is Map && first['msg'] != null) {
            errorMessage = first['msg'].toString();
          }
        }
      } else if (responseData['message'] != null) {
        errorMessage = responseData['message'].toString();
      }
    }
    return ServerFailure(errorMessage);
  }
}
