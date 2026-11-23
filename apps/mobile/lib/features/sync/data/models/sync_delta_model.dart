import 'dart:convert';

/// Domain and data models for Phase 11.3 Downward Delta Synchronization.

class SyncDeltaModel {
  final String syncType;
  final String serverTime;
  final String nextCursor;
  final bool hasMore;
  final SyncEmployeeModel? employee;
  final List<SyncShiftModel> shifts;
  final List<SyncWorkplaceModel> workplaces;
  final List<SyncHolidayModel> holidays;
  final List<SyncLeaveTypeModel> leaveTypes;
  final List<SyncLeaveBalanceModel> leaveBalances;
  final List<SyncLeaveRequestModel> leaveRequests;
  final SyncAttendancePolicyModel? attendancePolicy;
  final SyncReportingHierarchyModel? reportingHierarchy;
  final List<SyncTombstoneModel> tombstones;

  const SyncDeltaModel({
    required this.syncType,
    required this.serverTime,
    required this.nextCursor,
    required this.hasMore,
    this.employee,
    this.shifts = const [],
    this.workplaces = const [],
    this.holidays = const [],
    this.leaveTypes = const [],
    this.leaveBalances = const [],
    this.leaveRequests = const [],
    this.attendancePolicy,
    this.reportingHierarchy,
    this.tombstones = const [],
  });

  factory SyncDeltaModel.fromJson(Map<String, dynamic> json) {
    return SyncDeltaModel(
      syncType: json['sync_type'] as String? ?? 'FULL',
      serverTime: json['server_time'] as String? ?? '',
      nextCursor: json['next_cursor'] as String? ?? '',
      hasMore: json['has_more'] as bool? ?? false,
      employee: json['employee'] != null
          ? SyncEmployeeModel.fromJson(json['employee'] as Map<String, dynamic>)
          : null,
      shifts: (json['shifts'] as List<dynamic>?)
              ?.map((e) => SyncShiftModel.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const [],
      workplaces: (json['workplaces'] as List<dynamic>?)
              ?.map(
                  (e) => SyncWorkplaceModel.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const [],
      holidays: (json['holidays'] as List<dynamic>?)
              ?.map((e) => SyncHolidayModel.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const [],
      leaveTypes: (json['leave_types'] as List<dynamic>?)
              ?.map(
                  (e) => SyncLeaveTypeModel.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const [],
      leaveBalances: (json['leave_balances'] as List<dynamic>?)
              ?.map((e) =>
                  SyncLeaveBalanceModel.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const [],
      leaveRequests: (json['leave_requests'] as List<dynamic>?)
              ?.map((e) =>
                  SyncLeaveRequestModel.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const [],
      attendancePolicy: json['attendance_policy'] != null
          ? SyncAttendancePolicyModel.fromJson(
              json['attendance_policy'] as Map<String, dynamic>)
          : null,
      reportingHierarchy: json['reporting_hierarchy'] != null
          ? SyncReportingHierarchyModel.fromJson(
              json['reporting_hierarchy'] as Map<String, dynamic>)
          : null,
      tombstones: (json['tombstones'] as List<dynamic>?)
              ?.map(
                  (e) => SyncTombstoneModel.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const [],
    );
  }
}

class SyncEmployeeModel {
  final String id;
  final String tenantId;
  final String employeeId;
  final String firstName;
  final String lastName;
  final String workEmail;
  final String? phoneNumber;
  final String? departmentId;
  final String? designationId;
  final String? reportingManagerId;
  final String employmentType;
  final String status;
  final String? workLocation;
  final String updatedAt;

  const SyncEmployeeModel({
    required this.id,
    required this.tenantId,
    required this.employeeId,
    required this.firstName,
    required this.lastName,
    required this.workEmail,
    this.phoneNumber,
    this.departmentId,
    this.designationId,
    this.reportingManagerId,
    required this.employmentType,
    required this.status,
    this.workLocation,
    required this.updatedAt,
  });

  factory SyncEmployeeModel.fromJson(Map<String, dynamic> json) {
    return SyncEmployeeModel(
      id: json['id'] as String,
      tenantId: json['tenant_id'] as String,
      employeeId: json['employee_id'] as String,
      firstName: json['first_name'] as String,
      lastName: json['last_name'] as String,
      workEmail: json['work_email'] as String,
      phoneNumber: json['phone_number'] as String?,
      departmentId: json['department_id'] as String?,
      designationId: json['designation_id'] as String?,
      reportingManagerId: json['reporting_manager_id'] as String?,
      employmentType: json['employment_type'] as String? ?? 'full_time',
      status: json['status'] as String? ?? 'active',
      workLocation: json['work_location'] as String?,
      updatedAt: json['updated_at'] as String,
    );
  }

  Map<String, dynamic> toMap() {
    return {
      'id': id,
      'tenant_id': tenantId,
      'employee_id': employeeId,
      'first_name': firstName,
      'last_name': lastName,
      'work_email': workEmail,
      'phone_number': phoneNumber,
      'department_id': departmentId,
      'designation_id': designationId,
      'reporting_manager_id': reportingManagerId,
      'employment_type': employmentType,
      'status': status,
      'work_location': workLocation,
      'updated_at': updatedAt,
    };
  }
}

class SyncShiftModel {
  final String id;
  final String shiftTemplateId;
  final String name;
  final String code;
  final String startTime;
  final String endTime;
  final int gracePeriodMinutes;
  final int earlyExitGraceMinutes;
  final int halfDayThresholdMinutes;
  final int fullDayThresholdMinutes;
  final int breakDurationMinutes;
  final bool isOvernight;
  final bool isFlexible;
  final List<int> weeklyOffDays;
  final String effectiveFrom;
  final String? effectiveTo;
  final String updatedAt;

  const SyncShiftModel({
    required this.id,
    required this.shiftTemplateId,
    required this.name,
    required this.code,
    required this.startTime,
    required this.endTime,
    required this.gracePeriodMinutes,
    required this.earlyExitGraceMinutes,
    required this.halfDayThresholdMinutes,
    required this.fullDayThresholdMinutes,
    required this.breakDurationMinutes,
    required this.isOvernight,
    required this.isFlexible,
    required this.weeklyOffDays,
    required this.effectiveFrom,
    this.effectiveTo,
    required this.updatedAt,
  });

  factory SyncShiftModel.fromJson(Map<String, dynamic> json) {
    return SyncShiftModel(
      id: json['id'] as String,
      shiftTemplateId: json['shift_template_id'] as String,
      name: json['name'] as String,
      code: json['code'] as String,
      startTime: json['start_time'] as String,
      endTime: json['end_time'] as String,
      gracePeriodMinutes: json['grace_period_minutes'] as int? ?? 15,
      earlyExitGraceMinutes: json['early_exit_grace_minutes'] as int? ?? 15,
      halfDayThresholdMinutes: json['half_day_threshold_minutes'] as int? ?? 240,
      fullDayThresholdMinutes: json['full_day_threshold_minutes'] as int? ?? 480,
      breakDurationMinutes: json['break_duration_minutes'] as int? ?? 60,
      isOvernight: json['is_overnight'] as bool? ?? false,
      isFlexible: json['is_flexible'] as bool? ?? false,
      weeklyOffDays: (json['weekly_off_days'] as List<dynamic>?)
              ?.map((e) => e as int)
              .toList() ??
          const [6, 0],
      effectiveFrom: json['effective_from'] as String,
      effectiveTo: json['effective_to'] as String?,
      updatedAt: json['updated_at'] as String,
    );
  }

  Map<String, dynamic> toMap(String tenantId) {
    return {
      'id': id,
      'tenant_id': tenantId,
      'shift_template_id': shiftTemplateId,
      'name': name,
      'code': code,
      'start_time': startTime,
      'end_time': endTime,
      'grace_period_minutes': gracePeriodMinutes,
      'early_exit_grace_minutes': earlyExitGraceMinutes,
      'half_day_threshold_minutes': halfDayThresholdMinutes,
      'full_day_threshold_minutes': fullDayThresholdMinutes,
      'break_duration_minutes': breakDurationMinutes,
      'is_overnight': isOvernight ? 1 : 0,
      'is_flexible': isFlexible ? 1 : 0,
      'weekly_off_days': jsonEncode(weeklyOffDays),
      'effective_from': effectiveFrom,
      'effective_to': effectiveTo,
      'updated_at': updatedAt,
    };
  }
}

class SyncWorkplaceModel {
  final String id;
  final String name;
  final String code;
  final String addressLine1;
  final String city;
  final double latitude;
  final double longitude;
  final int radiusMeters;
  final String timezone;
  final List<String> wifiBssids;
  final bool isActive;
  final bool isAssigned;
  final bool isPrimary;
  final String updatedAt;

  const SyncWorkplaceModel({
    required this.id,
    required this.name,
    required this.code,
    required this.addressLine1,
    required this.city,
    required this.latitude,
    required this.longitude,
    required this.radiusMeters,
    required this.timezone,
    required this.wifiBssids,
    required this.isActive,
    required this.isAssigned,
    required this.isPrimary,
    required this.updatedAt,
  });

  factory SyncWorkplaceModel.fromJson(Map<String, dynamic> json) {
    return SyncWorkplaceModel(
      id: json['id'] as String,
      name: json['name'] as String,
      code: json['code'] as String,
      addressLine1: json['address_line1'] as String,
      city: json['city'] as String,
      latitude: (json['latitude'] as num).toDouble(),
      longitude: (json['longitude'] as num).toDouble(),
      radiusMeters: json['radius_meters'] as int? ?? 100,
      timezone: json['timezone'] as String? ?? 'UTC',
      wifiBssids: (json['wifi_bssids'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          const [],
      isActive: json['is_active'] as bool? ?? true,
      isAssigned: json['is_assigned'] as bool? ?? true,
      isPrimary: json['is_primary'] as bool? ?? false,
      updatedAt: json['updated_at'] as String,
    );
  }

  Map<String, dynamic> toMap(String tenantId) {
    return {
      'id': id,
      'tenant_id': tenantId,
      'name': name,
      'code': code,
      'address_line1': addressLine1,
      'city': city,
      'latitude': latitude,
      'longitude': longitude,
      'radius_meters': radiusMeters,
      'timezone': timezone,
      'wifi_bssids': jsonEncode(wifiBssids),
      'is_active': isActive ? 1 : 0,
      'is_assigned': isAssigned ? 1 : 0,
      'is_primary': isPrimary ? 1 : 0,
      'updated_at': updatedAt,
    };
  }
}

class SyncHolidayModel {
  final String id;
  final String calendarId;
  final String holidayDate;
  final String name;
  final String holidayType;
  final bool isOptional;
  final String updatedAt;

  const SyncHolidayModel({
    required this.id,
    required this.calendarId,
    required this.holidayDate,
    required this.name,
    required this.holidayType,
    required this.isOptional,
    required this.updatedAt,
  });

  factory SyncHolidayModel.fromJson(Map<String, dynamic> json) {
    return SyncHolidayModel(
      id: json['id'] as String,
      calendarId: json['calendar_id'] as String,
      holidayDate: json['holiday_date'] as String,
      name: json['name'] as String,
      holidayType: json['holiday_type'] as String? ?? 'PUBLIC',
      isOptional: json['is_optional'] as bool? ?? false,
      updatedAt: json['updated_at'] as String,
    );
  }

  Map<String, dynamic> toMap(String tenantId) {
    return {
      'id': id,
      'tenant_id': tenantId,
      'calendar_id': calendarId,
      'holiday_date': holidayDate,
      'name': name,
      'holiday_type': holidayType,
      'is_optional': isOptional ? 1 : 0,
      'updated_at': updatedAt,
    };
  }
}

class SyncLeaveTypeModel {
  final String id;
  final String code;
  final String name;
  final bool isPaid;
  final bool allowHalfDay;
  final String updatedAt;

  const SyncLeaveTypeModel({
    required this.id,
    required this.code,
    required this.name,
    required this.isPaid,
    required this.allowHalfDay,
    required this.updatedAt,
  });

  factory SyncLeaveTypeModel.fromJson(Map<String, dynamic> json) {
    return SyncLeaveTypeModel(
      id: json['id'] as String,
      code: json['code'] as String,
      name: json['name'] as String,
      isPaid: json['is_paid'] as bool? ?? true,
      allowHalfDay: json['allow_half_day'] as bool? ?? true,
      updatedAt: json['updated_at'] as String,
    );
  }

  Map<String, dynamic> toMap(String tenantId) {
    return {
      'id': id,
      'tenant_id': tenantId,
      'code': code,
      'name': name,
      'is_paid': isPaid ? 1 : 0,
      'allow_half_day': allowHalfDay ? 1 : 0,
      'updated_at': updatedAt,
    };
  }
}

class SyncLeaveBalanceModel {
  final String id;
  final String leaveTypeId;
  final int year;
  final double annualAllocation;
  final double used;
  final double availableBalance;
  final String updatedAt;

  const SyncLeaveBalanceModel({
    required this.id,
    required this.leaveTypeId,
    required this.year,
    required this.annualAllocation,
    required this.used,
    required this.availableBalance,
    required this.updatedAt,
  });

  factory SyncLeaveBalanceModel.fromJson(Map<String, dynamic> json) {
    return SyncLeaveBalanceModel(
      id: json['id'] as String,
      leaveTypeId: json['leave_type_id'] as String,
      year: json['year'] as int,
      annualAllocation: (json['annual_allocation'] as num).toDouble(),
      used: (json['used'] as num).toDouble(),
      availableBalance: (json['available_balance'] as num).toDouble(),
      updatedAt: json['updated_at'] as String,
    );
  }

  Map<String, dynamic> toMap(String tenantId, String employeeId) {
    return {
      'id': id,
      'tenant_id': tenantId,
      'employee_id': employeeId,
      'leave_type_id': leaveTypeId,
      'year': year,
      'annual_allocation': annualAllocation,
      'used': used,
      'available_balance': availableBalance,
      'updated_at': updatedAt,
    };
  }
}

class SyncLeaveRequestModel {
  final String id;
  final String leaveTypeId;
  final String startDate;
  final String endDate;
  final bool isHalfDay;
  final double totalDays;
  final String reason;
  final String status;
  final String? decidedAt;
  final String updatedAt;

  const SyncLeaveRequestModel({
    required this.id,
    required this.leaveTypeId,
    required this.startDate,
    required this.endDate,
    required this.isHalfDay,
    required this.totalDays,
    required this.reason,
    required this.status,
    this.decidedAt,
    required this.updatedAt,
  });

  factory SyncLeaveRequestModel.fromJson(Map<String, dynamic> json) {
    return SyncLeaveRequestModel(
      id: json['id'] as String,
      leaveTypeId: json['leave_type_id'] as String,
      startDate: json['start_date'] as String,
      endDate: json['end_date'] as String,
      isHalfDay: json['is_half_day'] as bool? ?? false,
      totalDays: (json['total_days'] as num).toDouble(),
      reason: json['reason'] as String,
      status: json['status'] as String,
      decidedAt: json['decided_at'] as String?,
      updatedAt: json['updated_at'] as String,
    );
  }

  Map<String, dynamic> toMap(String tenantId, String employeeId) {
    return {
      'id': id,
      'tenant_id': tenantId,
      'employee_id': employeeId,
      'leave_type_id': leaveTypeId,
      'start_date': startDate,
      'end_date': endDate,
      'is_half_day': isHalfDay ? 1 : 0,
      'total_days': totalDays,
      'reason': reason,
      'status': status,
      'decided_at': decidedAt,
      'updated_at': updatedAt,
    };
  }
}

class SyncAttendancePolicyModel {
  final String id;
  final int version;
  final bool isActive;
  final String defaultMode;
  final List<String> allowedMethods;
  final List<String> requiredMethods;
  final String combinationRule;
  final Map<String, dynamic> gpsConfig;
  final Map<String, dynamic> wifiConfig;
  final String updatedAt;

  const SyncAttendancePolicyModel({
    required this.id,
    required this.version,
    required this.isActive,
    required this.defaultMode,
    required this.allowedMethods,
    required this.requiredMethods,
    required this.combinationRule,
    required this.gpsConfig,
    required this.wifiConfig,
    required this.updatedAt,
  });

  factory SyncAttendancePolicyModel.fromJson(Map<String, dynamic> json) {
    return SyncAttendancePolicyModel(
      id: json['id'] as String,
      version: json['version'] as int? ?? 1,
      isActive: json['is_active'] as bool? ?? true,
      defaultMode: json['default_mode'] as String? ?? 'MANUAL',
      allowedMethods: (json['allowed_methods'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          const ['MANUAL'],
      requiredMethods: (json['required_methods'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          const ['MANUAL'],
      combinationRule: json['combination_rule'] as String? ?? 'OR',
      gpsConfig: json['gps_config'] as Map<String, dynamic>? ?? {},
      wifiConfig: json['wifi_config'] as Map<String, dynamic>? ?? {},
      updatedAt: json['updated_at'] as String,
    );
  }

  Map<String, dynamic> toMap(String tenantId) {
    return {
      'id': id,
      'tenant_id': tenantId,
      'version': version,
      'is_active': isActive ? 1 : 0,
      'default_mode': defaultMode,
      'allowed_methods': jsonEncode(allowedMethods),
      'required_methods': jsonEncode(requiredMethods),
      'combination_rule': combinationRule,
      'gps_config': jsonEncode(gpsConfig),
      'wifi_config': jsonEncode(wifiConfig),
      'updated_at': updatedAt,
    };
  }
}

class SyncDirectReportModel {
  final String id;
  final String employeeId;
  final String firstName;
  final String lastName;
  final String workEmail;
  final String? departmentName;
  final String status;
  final String updatedAt;

  const SyncDirectReportModel({
    required this.id,
    required this.employeeId,
    required this.firstName,
    required this.lastName,
    required this.workEmail,
    this.departmentName,
    required this.status,
    required this.updatedAt,
  });

  factory SyncDirectReportModel.fromJson(Map<String, dynamic> json) {
    return SyncDirectReportModel(
      id: json['id'] as String,
      employeeId: json['employee_id'] as String,
      firstName: json['first_name'] as String,
      lastName: json['last_name'] as String,
      workEmail: json['work_email'] as String,
      departmentName: json['department_name'] as String?,
      status: json['status'] as String? ?? 'active',
      updatedAt: json['updated_at'] as String,
    );
  }

  Map<String, dynamic> toMap(String tenantId) {
    return {
      'id': id,
      'tenant_id': tenantId,
      'employee_id': employeeId,
      'first_name': firstName,
      'last_name': lastName,
      'work_email': workEmail,
      'department_name': departmentName,
      'status': status,
      'updated_at': updatedAt,
    };
  }
}

class SyncReportingHierarchyModel {
  final String? managerId;
  final String? managerName;
  final String? managerEmail;
  final List<SyncDirectReportModel> directReports;

  const SyncReportingHierarchyModel({
    this.managerId,
    this.managerName,
    this.managerEmail,
    this.directReports = const [],
  });

  factory SyncReportingHierarchyModel.fromJson(Map<String, dynamic> json) {
    return SyncReportingHierarchyModel(
      managerId: json['manager_id'] as String?,
      managerName: json['manager_name'] as String?,
      managerEmail: json['manager_email'] as String?,
      directReports: (json['direct_reports'] as List<dynamic>?)
              ?.map((e) =>
                  SyncDirectReportModel.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const [],
    );
  }
}

class SyncTombstoneModel {
  final String entityType;
  final String entityId;
  final String deletedAt;

  const SyncTombstoneModel({
    required this.entityType,
    required this.entityId,
    required this.deletedAt,
  });

  factory SyncTombstoneModel.fromJson(Map<String, dynamic> json) {
    return SyncTombstoneModel(
      entityType: json['entity_type'] as String,
      entityId: json['entity_id'] as String,
      deletedAt: json['deleted_at'] as String,
    );
  }
}

