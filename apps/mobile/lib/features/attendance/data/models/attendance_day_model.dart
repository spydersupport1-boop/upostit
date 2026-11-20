import '../../domain/entities/attendance_day.dart';

/// Data Transfer Object for AttendanceDayResponse JSON payloads.
class AttendanceDayModel extends AttendanceDay {
  const AttendanceDayModel({
    required super.id,
    required super.tenantId,
    required super.employeeId,
    required super.attendanceDate,
    super.shiftTemplateId,
    super.shiftVersionId,
    super.firstCheckIn,
    super.lastCheckOut,
    required super.totalWorkingMinutes,
    required super.totalBreakMinutes,
    required super.netWorkingMinutes,
    super.actualLateMinutes,
    super.lateArrivalMinutes,
    super.actualEarlyMinutes,
    super.earlyDepartureMinutes,
    super.overtimeMinutes,
    required super.status,
    required super.calculationStatus,
    super.calculationVersion,
    super.isIncomplete,
    super.missingPunch,
    super.sourceEventIds,
    super.metadata,
    required super.lastCalculatedAt,
  });

  factory AttendanceDayModel.fromJson(Map<String, dynamic> json) {
    return AttendanceDayModel(
      id: json['id'] as String,
      tenantId: json['tenant_id'] as String,
      employeeId: json['employee_id'] as String,
      attendanceDate: DateTime.parse(
          (json['attendance_date'] ?? json['work_date']) as String),
      shiftTemplateId: json['shift_template_id'] as String?,
      shiftVersionId: json['shift_version_id'] as String?,
      firstCheckIn: json['first_check_in'] != null
          ? DateTime.parse(json['first_check_in'] as String)
          : null,
      lastCheckOut: json['last_check_out'] != null
          ? DateTime.parse(json['last_check_out'] as String)
          : null,
      totalWorkingMinutes:
          (json['total_working_minutes'] as num?)?.toInt() ?? 0,
      totalBreakMinutes: (json['total_break_minutes'] as num?)?.toInt() ?? 0,
      netWorkingMinutes: (json['net_working_minutes'] as num?)?.toInt() ?? 0,
      actualLateMinutes: (json['actual_late_minutes'] as num?)?.toInt() ?? 0,
      lateArrivalMinutes: (json['late_arrival_minutes'] as num?)?.toInt() ?? 0,
      actualEarlyMinutes: (json['actual_early_minutes'] as num?)?.toInt() ?? 0,
      earlyDepartureMinutes:
          (json['early_departure_minutes'] as num?)?.toInt() ?? 0,
      overtimeMinutes: (json['overtime_minutes'] as num?)?.toInt() ?? 0,
      status: (json['status'] as String?) ?? 'NOT_RECORDED',
      calculationStatus: (json['calculation_status'] as String?) ?? 'PENDING',
      calculationVersion: (json['calculation_version'] as num?)?.toInt() ?? 1,
      isIncomplete: (json['is_incomplete'] as bool?) ?? false,
      missingPunch: (json['missing_punch'] as bool?) ?? false,
      sourceEventIds: (json['source_event_ids'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          const [],
      metadata: (json['metadata'] as Map<String, dynamic>?) ??
          (json['metadata_json'] as Map<String, dynamic>?) ??
          const {},
      lastCalculatedAt: json['last_calculated_at'] != null
          ? DateTime.parse(json['last_calculated_at'] as String)
          : DateTime.now(),
    );
  }
}
