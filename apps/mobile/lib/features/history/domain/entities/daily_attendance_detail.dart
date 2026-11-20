import 'package:equatable/equatable.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_day.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_event.dart';
import 'package:mobile/features/attendance/domain/entities/today_shift.dart';
import 'package:mobile/features/sync/domain/entities/local_queue_item.dart';

/// Aggregated domain representation of an employee's attendance on a specific calendar date.
class DailyAttendanceDetail extends Equatable {
  final DateTime date;
  final AttendanceDay? dayRecord;
  final TodayShift? shift;
  final List<AttendanceEvent> events;
  final List<LocalQueueItem> pendingQueueItems;

  const DailyAttendanceDetail({
    required this.date,
    this.dayRecord,
    this.shift,
    this.events = const [],
    this.pendingQueueItems = const [],
  });

  String get effectiveStatus {
    if (pendingQueueItems.isNotEmpty) {
      return 'PENDING_SYNC';
    }
    if (dayRecord != null) {
      return dayRecord!.status.toUpperCase();
    }
    if (events.isNotEmpty) {
      final last = events.last;
      if (last.eventType == AttendanceEventType.checkOut) {
        return 'COMPLETED';
      }
      return 'IN_PROGRESS';
    }
    return 'UNRECORDED';
  }

  bool get hasPendingPunches => pendingQueueItems.isNotEmpty;

  Duration get workingDuration {
    if (dayRecord != null) {
      return Duration(minutes: dayRecord!.netWorkingMinutes);
    }
    return Duration.zero;
  }

  Duration get breakDuration {
    if (dayRecord != null) {
      return Duration(minutes: dayRecord!.totalBreakMinutes);
    }
    return Duration.zero;
  }

  int get lateMinutes => dayRecord?.lateArrivalMinutes ?? 0;
  int get earlyMinutes => dayRecord?.earlyDepartureMinutes ?? 0;

  DateTime? get firstCheckIn => dayRecord?.firstCheckIn ?? _findFirstCheckIn();
  DateTime? get lastCheckOut => dayRecord?.lastCheckOut ?? _findLastCheckOut();

  DateTime? _findFirstCheckIn() {
    for (final e in events) {
      if (e.eventType == AttendanceEventType.checkIn) {
        return e.effectiveAt;
      }
    }
    return null;
  }

  DateTime? _findLastCheckOut() {
    for (final e in events.reversed) {
      if (e.eventType == AttendanceEventType.checkOut) {
        return e.effectiveAt;
      }
    }
    return null;
  }

  @override
  List<Object?> get props => [
        date,
        dayRecord,
        shift,
        events,
        pendingQueueItems,
      ];
}
