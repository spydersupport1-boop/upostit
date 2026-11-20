/// High-level attendance state of an employee on a given working day.
///
/// Derived strictly from server-confirmed attendance events and projections.
enum AttendanceStatus {
  /// Employee has not yet checked in today, or has no active session.
  notCheckedIn,

  /// Employee is actively working (checked in and not on break).
  working,

  /// Employee has temporarily paused work for a break.
  onBreak,

  /// Employee has completed their work shift and checked out for the day.
  completed,
}

extension AttendanceStatusX on AttendanceStatus {
  String get displayName {
    switch (this) {
      case AttendanceStatus.notCheckedIn:
        return 'Not Checked In';
      case AttendanceStatus.working:
        return 'Working';
      case AttendanceStatus.onBreak:
        return 'On Break';
      case AttendanceStatus.completed:
        return 'Shift Completed';
    }
  }

  bool get isActiveSession =>
      this == AttendanceStatus.working || this == AttendanceStatus.onBreak;
}
