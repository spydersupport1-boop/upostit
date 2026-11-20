import 'package:equatable/equatable.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_day.dart';

/// Aggregated monthly presence and duration metrics.
class MonthlyAttendanceSummary extends Equatable {
  final int totalRecordedDays;
  final int presentCount;
  final int lateCount;
  final int halfDayCount;
  final int absentCount;
  final int incompleteCount;
  final int pendingReviewCount;
  final Duration totalWorkingDuration;
  final Duration totalBreakDuration;

  const MonthlyAttendanceSummary({
    this.totalRecordedDays = 0,
    this.presentCount = 0,
    this.lateCount = 0,
    this.halfDayCount = 0,
    this.absentCount = 0,
    this.incompleteCount = 0,
    this.pendingReviewCount = 0,
    this.totalWorkingDuration = Duration.zero,
    this.totalBreakDuration = Duration.zero,
  });

  factory MonthlyAttendanceSummary.fromDays(List<AttendanceDay> days) {
    int present = 0;
    int late = 0;
    int halfDay = 0;
    int absent = 0;
    int incomplete = 0;
    int pendingReview = 0;
    int workingMins = 0;
    int breakMins = 0;

    for (final day in days) {
      final statusUpper = day.status.toUpperCase();
      switch (statusUpper) {
        case 'PRESENT':
          present++;
          break;
        case 'LATE':
          late++;
          break;
        case 'HALF_DAY':
          halfDay++;
          break;
        case 'ABSENT':
          absent++;
          break;
        case 'INCOMPLETE':
          incomplete++;
          break;
        case 'PENDING_REVIEW':
          pendingReview++;
          break;
        default:
          if (day.firstCheckIn != null) {
            present++;
          }
      }

      if (day.isIncomplete) {
        incomplete++;
      }

      workingMins += day.netWorkingMinutes;
      breakMins += day.totalBreakMinutes;
    }

    return MonthlyAttendanceSummary(
      totalRecordedDays: days.length,
      presentCount: present,
      lateCount: late,
      halfDayCount: halfDay,
      absentCount: absent,
      incompleteCount: incomplete,
      pendingReviewCount: pendingReview,
      totalWorkingDuration: Duration(minutes: workingMins),
      totalBreakDuration: Duration(minutes: breakMins),
    );
  }

  String get formattedTotalHours {
    final hours = totalWorkingDuration.inHours;
    final mins = totalWorkingDuration.inMinutes % 60;
    return '${hours}h ${mins}m';
  }

  @override
  List<Object?> get props => [
        totalRecordedDays,
        presentCount,
        lateCount,
        halfDayCount,
        absentCount,
        incompleteCount,
        pendingReviewCount,
        totalWorkingDuration,
        totalBreakDuration,
      ];
}
