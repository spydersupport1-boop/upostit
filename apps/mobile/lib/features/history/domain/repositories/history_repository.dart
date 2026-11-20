import 'package:mobile/core/errors/result.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_day.dart';
import 'package:mobile/features/attendance/domain/entities/today_shift.dart';
import 'package:mobile/features/history/domain/entities/daily_attendance_detail.dart';

/// Contract for attendance history, monthly summaries, and shift roster.
abstract class HistoryRepository {
  /// Fetches monthly attendance days for calendar rendering.
  Future<Result<List<AttendanceDay>>> getMonthlyAttendance({
    required int year,
    required int month,
  });

  /// Fetches the complete attendance details and audit trail for a selected day.
  Future<Result<DailyAttendanceDetail>> getDailyAttendanceDetail(
    DateTime date, {
    AttendanceDay? preloadedDay,
  });

  /// Fetches active and upcoming shift assignments.
  Future<Result<List<TodayShift>>> getShiftSchedule();
}
