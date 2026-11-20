import 'package:equatable/equatable.dart';
import 'attendance_day.dart';
import 'attendance_event.dart';
import 'attendance_policy.dart';
import 'attendance_status.dart';
import 'assigned_workplace.dart';
import 'today_shift.dart';

/// Aggregated domain model representing the current day's complete attendance dashboard.
class AttendanceDashboard extends Equatable {
  final AttendanceStatus status;
  final AttendanceDay? todayDay;
  final List<AttendanceEvent> todayEvents;
  final AttendanceEvent? lastEvent;
  final TodayShift? shift;
  final AssignedWorkplace? workplace;
  final AttendancePolicy? policy;
  final Duration workingDuration;
  final Duration breakDuration;

  const AttendanceDashboard({
    required this.status,
    this.todayDay,
    this.todayEvents = const [],
    this.lastEvent,
    this.shift,
    this.workplace,
    this.policy,
    this.workingDuration = Duration.zero,
    this.breakDuration = Duration.zero,
  });

  AttendanceDashboard copyWith({
    AttendanceStatus? status,
    AttendanceDay? todayDay,
    List<AttendanceEvent>? todayEvents,
    AttendanceEvent? lastEvent,
    TodayShift? shift,
    AssignedWorkplace? workplace,
    AttendancePolicy? policy,
    Duration? workingDuration,
    Duration? breakDuration,
  }) {
    return AttendanceDashboard(
      status: status ?? this.status,
      todayDay: todayDay ?? this.todayDay,
      todayEvents: todayEvents ?? this.todayEvents,
      lastEvent: lastEvent ?? this.lastEvent,
      shift: shift ?? this.shift,
      workplace: workplace ?? this.workplace,
      policy: policy ?? this.policy,
      workingDuration: workingDuration ?? this.workingDuration,
      breakDuration: breakDuration ?? this.breakDuration,
    );
  }

  @override
  List<Object?> get props => [
        status,
        todayDay,
        todayEvents,
        lastEvent,
        shift,
        workplace,
        policy,
        workingDuration,
        breakDuration,
      ];
}
