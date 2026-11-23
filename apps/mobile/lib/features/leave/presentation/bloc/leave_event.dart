import 'package:equatable/equatable.dart';

abstract class LeaveEvent extends Equatable {
  const LeaveEvent();

  @override
  List<Object?> get props => [];
}

/// Dispatched to load the employee leave dashboard data.
class LeaveDashboardRequested extends LeaveEvent {
  const LeaveDashboardRequested();
}

/// Dispatched to submit a leave application.
class LeaveApplicationSubmitted extends LeaveEvent {
  final String leaveTypeId;
  final String startDate;
  final String endDate;
  final bool isHalfDay;
  final String? halfDayPeriod;
  final String reason;

  const LeaveApplicationSubmitted({
    required this.leaveTypeId,
    required this.startDate,
    required this.endDate,
    this.isHalfDay = false,
    this.halfDayPeriod,
    required this.reason,
  });

  @override
  List<Object?> get props => [
        leaveTypeId,
        startDate,
        endDate,
        isHalfDay,
        halfDayPeriod,
        reason,
      ];
}

/// Dispatched to cancel an eligible leave request.
class LeaveCancellationRequested extends LeaveEvent {
  final String requestId;
  final String? reason;

  const LeaveCancellationRequested({
    required this.requestId,
    this.reason,
  });

  @override
  List<Object?> get props => [requestId, reason];
}

/// Dispatched to fetch or filter the employee's leave history.
class LeaveHistoryRequested extends LeaveEvent {
  final String? statusFilter;

  const LeaveHistoryRequested({this.statusFilter});

  @override
  List<Object?> get props => [statusFilter];
}

/// Dispatched to fetch upcoming holidays.
class UpcomingHolidaysRequested extends LeaveEvent {
  const UpcomingHolidaysRequested();
}

/// Dispatched by managers / HR / admin to fetch the review queue.
class SupervisorQueueRequested extends LeaveEvent {
  final String? statusFilter;

  const SupervisorQueueRequested({this.statusFilter});

  @override
  List<Object?> get props => [statusFilter];
}

/// Dispatched by supervisors to record an approval or rejection.
class SupervisorDecisionSubmitted extends LeaveEvent {
  final String requestId;
  final String action;
  final String? reason;

  const SupervisorDecisionSubmitted({
    required this.requestId,
    required this.action,
    this.reason,
  });

  @override
  List<Object?> get props => [requestId, action, reason];
}

/// Dispatched to clear transient alert notices.
class LeaveNoticesCleared extends LeaveEvent {
  const LeaveNoticesCleared();
}
