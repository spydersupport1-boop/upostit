import 'package:equatable/equatable.dart';

/// Domain entity representing a calculated daily attendance summary record.
class AttendanceDay extends Equatable {
  final String id;
  final String tenantId;
  final String employeeId;
  final DateTime attendanceDate;
  final String? shiftTemplateId;
  final String? shiftVersionId;
  final DateTime? firstCheckIn;
  final DateTime? lastCheckOut;
  final int totalWorkingMinutes;
  final int totalBreakMinutes;
  final int netWorkingMinutes;
  final int actualLateMinutes;
  final int lateArrivalMinutes;
  final int actualEarlyMinutes;
  final int earlyDepartureMinutes;
  final int overtimeMinutes;
  final String status;
  final String calculationStatus;
  final int calculationVersion;
  final bool isIncomplete;
  final bool missingPunch;
  final List<String> sourceEventIds;
  final Map<String, dynamic> metadata;
  final DateTime lastCalculatedAt;

  const AttendanceDay({
    required this.id,
    required this.tenantId,
    required this.employeeId,
    required this.attendanceDate,
    this.shiftTemplateId,
    this.shiftVersionId,
    this.firstCheckIn,
    this.lastCheckOut,
    required this.totalWorkingMinutes,
    required this.totalBreakMinutes,
    required this.netWorkingMinutes,
    this.actualLateMinutes = 0,
    this.lateArrivalMinutes = 0,
    this.actualEarlyMinutes = 0,
    this.earlyDepartureMinutes = 0,
    this.overtimeMinutes = 0,
    required this.status,
    required this.calculationStatus,
    this.calculationVersion = 1,
    this.isIncomplete = false,
    this.missingPunch = false,
    this.sourceEventIds = const [],
    this.metadata = const {},
    required this.lastCalculatedAt,
  });

  @override
  List<Object?> get props => [
        id,
        tenantId,
        employeeId,
        attendanceDate,
        shiftTemplateId,
        shiftVersionId,
        firstCheckIn,
        lastCheckOut,
        totalWorkingMinutes,
        totalBreakMinutes,
        netWorkingMinutes,
        actualLateMinutes,
        lateArrivalMinutes,
        actualEarlyMinutes,
        earlyDepartureMinutes,
        overtimeMinutes,
        status,
        calculationStatus,
        calculationVersion,
        isIncomplete,
        missingPunch,
        sourceEventIds,
        metadata,
        lastCalculatedAt,
      ];
}
