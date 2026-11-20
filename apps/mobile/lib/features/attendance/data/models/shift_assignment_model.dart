import '../../domain/entities/today_shift.dart';

/// Data Transfer Object for employee shift assignment and shift template JSON.
class ShiftAssignmentModel extends TodayShift {
  const ShiftAssignmentModel({
    required super.id,
    required super.name,
    required super.code,
    super.startTime,
    super.endTime,
    super.gracePeriodMinutes,
    super.breakDurationMinutes,
    super.isOvernight,
    super.isFlexible,
    super.effectiveFrom,
    super.effectiveTo,
    super.weeklyOffDays,
  });

  factory ShiftAssignmentModel.fromJson(Map<String, dynamic> json) {
    return ShiftAssignmentModel(
      id: (json['shift_template_id'] ?? json['id']) as String,
      name: (json['shift_name'] ?? json['name'] ?? 'Regular Shift') as String,
      code: (json['shift_code'] ?? json['code'] ?? 'REG') as String,
      startTime: json['start_time'] as String?,
      endTime: json['end_time'] as String?,
      gracePeriodMinutes: (json['grace_period_minutes'] as num?)?.toInt() ?? 15,
      breakDurationMinutes:
          (json['break_duration_minutes'] as num?)?.toInt() ?? 0,
      isOvernight: (json['is_overnight'] as bool?) ?? false,
      isFlexible: (json['is_flexible'] as bool?) ?? false,
      effectiveFrom: json['effective_from'] != null
          ? DateTime.tryParse(json['effective_from'].toString())
          : null,
      effectiveTo: json['effective_to'] != null
          ? DateTime.tryParse(json['effective_to'].toString())
          : null,
      weeklyOffDays: (json['weekly_off_days'] as List<dynamic>?)
              ?.map((e) => (e as num).toInt())
              .toList() ??
          const [],
    );
  }
}
