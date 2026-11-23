import '../../domain/entities/leave_type.dart';

class LeaveTypeModel extends LeaveType {
  const LeaveTypeModel({
    required super.id,
    required super.code,
    required super.name,
    super.description,
    required super.isPaid,
    required super.requiresApproval,
    required super.allowHalfDay,
    super.maxConsecutiveDays,
    required super.carryForwardLimit,
    required super.isActive,
  });

  factory LeaveTypeModel.fromJson(Map<String, dynamic> json) {
    return LeaveTypeModel(
      id: json['id'] as String,
      code: json['code'] as String,
      name: json['name'] as String,
      description: json['description'] as String?,
      isPaid: json['is_paid'] as bool? ?? true,
      requiresApproval: json['requires_approval'] as bool? ?? true,
      allowHalfDay: json['allow_half_day'] as bool? ?? true,
      maxConsecutiveDays: json['max_consecutive_days'] as int?,
      carryForwardLimit: json['carry_forward_limit'] != null
          ? double.tryParse(json['carry_forward_limit'].toString()) ?? 0.0
          : 0.0,
      isActive: json['is_active'] as bool? ?? true,
    );
  }
}
