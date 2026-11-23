import '../../domain/entities/leave_request.dart';

class LeaveRequestModel extends LeaveRequest {
  const LeaveRequestModel({
    required super.id,
    required super.employeeId,
    super.employeeName,
    required super.leaveTypeId,
    super.leaveTypeCode,
    super.leaveTypeName,
    required super.startDate,
    required super.endDate,
    required super.isHalfDay,
    super.halfDayPeriod,
    required super.totalDays,
    required super.reason,
    required super.status,
    super.reviewerNotes,
    super.decidedAt,
    required super.createdAt,
  });

  factory LeaveRequestModel.fromJson(Map<String, dynamic> json) {
    return LeaveRequestModel(
      id: json['id'] as String,
      employeeId: json['employee_id'] as String,
      employeeName: json['employee_name'] as String?,
      leaveTypeId: json['leave_type_id'] as String,
      leaveTypeCode: json['leave_type_code'] as String?,
      leaveTypeName: json['leave_type_name'] as String?,
      startDate: json['start_date'] as String,
      endDate: json['end_date'] as String,
      isHalfDay: json['is_half_day'] as bool? ?? false,
      halfDayPeriod: json['half_day_period'] as String?,
      totalDays: json['total_days'] != null
          ? double.tryParse(json['total_days'].toString()) ?? 1.0
          : 1.0,
      reason: json['reason'] as String? ?? '',
      status: json['status'] as String? ?? 'PENDING_APPROVAL',
      reviewerNotes: json['reviewer_notes'] as String?,
      decidedAt: json['decided_at'] != null
          ? DateTime.tryParse(json['decided_at'].toString())
          : null,
      createdAt: json['created_at'] != null
          ? DateTime.parse(json['created_at'].toString())
          : DateTime.now(),
    );
  }
}
