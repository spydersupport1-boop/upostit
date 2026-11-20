import '../../domain/entities/leave_balance.dart';

class LeaveBalanceModel extends LeaveBalance {
  const LeaveBalanceModel({
    required super.id,
    required super.employeeId,
    required super.leaveTypeId,
    required super.leaveTypeCode,
    required super.leaveTypeName,
    required super.year,
    required super.annualAllocation,
    required super.carriedForward,
    required super.accrued,
    required super.used,
    required super.pendingApproval,
    required super.availableBalance,
  });

  factory LeaveBalanceModel.fromJson(Map<String, dynamic> json) {
    return LeaveBalanceModel(
      id: json['id'] as String,
      employeeId: json['employee_id'] as String,
      leaveTypeId: json['leave_type_id'] as String,
      leaveTypeCode: json['leave_type_code'] as String,
      leaveTypeName: json['leave_type_name'] as String? ??
          (json['leave_type_code'] as String? ?? 'Leave'),
      year: json['year'] as int? ?? DateTime.now().year,
      annualAllocation: json['annual_allocation'] != null
          ? double.tryParse(json['annual_allocation'].toString()) ?? 0.0
          : 0.0,
      carriedForward: json['carried_forward'] != null
          ? double.tryParse(json['carried_forward'].toString()) ?? 0.0
          : 0.0,
      accrued: json['accrued'] != null
          ? double.tryParse(json['accrued'].toString()) ?? 0.0
          : 0.0,
      used: json['used'] != null
          ? double.tryParse(json['used'].toString()) ?? 0.0
          : 0.0,
      pendingApproval: json['pending_approval'] != null
          ? double.tryParse(json['pending_approval'].toString()) ?? 0.0
          : 0.0,
      availableBalance: json['available_balance'] != null
          ? double.tryParse(json['available_balance'].toString()) ?? 0.0
          : 0.0,
    );
  }
}
