import 'package:equatable/equatable.dart';

/// Domain entity representing an employee's submitted leave request.
class LeaveRequest extends Equatable {
  final String id;
  final String employeeId;
  final String? employeeName;
  final String leaveTypeId;
  final String? leaveTypeCode;
  final String? leaveTypeName;
  final String startDate;
  final String endDate;
  final bool isHalfDay;
  final String? halfDayPeriod;
  final double totalDays;
  final String reason;
  final String status;
  final String? reviewerNotes;
  final DateTime? decidedAt;
  final DateTime createdAt;

  const LeaveRequest({
    required this.id,
    required this.employeeId,
    this.employeeName,
    required this.leaveTypeId,
    this.leaveTypeCode,
    this.leaveTypeName,
    required this.startDate,
    required this.endDate,
    required this.isHalfDay,
    this.halfDayPeriod,
    required this.totalDays,
    required this.reason,
    required this.status,
    this.reviewerNotes,
    this.decidedAt,
    required this.createdAt,
  });

  bool get isPending => status == 'PENDING_APPROVAL';
  bool get isApproved => status == 'APPROVED';
  bool get isRejected => status == 'REJECTED';
  bool get isCancelled => status == 'CANCELLED';

  String? get reviewNotes => reviewerNotes;
  DateTime get startDateTime => DateTime.tryParse(startDate) ?? DateTime.now();
  DateTime get endDateTime => DateTime.tryParse(endDate) ?? DateTime.now();

  /// Evaluates whether the request is eligible for cancellation according to backend rules:
  /// - Pending requests may be cancelled immediately.
  /// - Approved requests may only be cancelled if the leave commences in the future (startDate > today).
  bool canCancel(DateTime today) {
    if (isPending) return true;
    if (isApproved) {
      try {
        final start = DateTime.parse(startDate);
        final todayMidnight = DateTime(today.year, today.month, today.day);
        return start.isAfter(todayMidnight);
      } catch (_) {
        return false;
      }
    }
    return false;
  }

  @override
  List<Object?> get props => [
        id,
        employeeId,
        employeeName,
        leaveTypeId,
        leaveTypeCode,
        leaveTypeName,
        startDate,
        endDate,
        isHalfDay,
        halfDayPeriod,
        totalDays,
        reason,
        status,
        reviewerNotes,
        decidedAt,
        createdAt,
      ];
}
