import '../../domain/entities/attendance_policy.dart';

/// Data Transfer Object for EmployeeAttendancePolicyResponse.
class AttendancePolicyModel extends AttendancePolicy {
  const AttendancePolicyModel({
    required super.tenantId,
    required super.version,
    required super.defaultMode,
    required super.allowedMethods,
    required super.requiredMethods,
    required super.combinationRule,
    required super.requiresGps,
    super.requiresWifi,
    super.requiresBiometric,
    super.requiresFace,
    super.maxAccuracyMeters,
    super.maxLocationAgeSeconds,
    super.maxWifiAgeSeconds,
    super.wifiFallbackAction,
    super.allowedFallbackMethods,
  });

  factory AttendancePolicyModel.fromJson(Map<String, dynamic> json) {
    return AttendancePolicyModel(
      tenantId: (json['tenant_id'] ?? '').toString(),
      version: (json['version'] as num?)?.toInt() ?? 1,
      defaultMode: (json['default_mode'] ?? 'MANUAL').toString(),
      allowedMethods: (json['allowed_methods'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          const ['MANUAL'],
      requiredMethods: (json['required_methods'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          const ['MANUAL'],
      combinationRule: (json['combination_rule'] ?? 'OR').toString(),
      requiresGps: (json['requires_gps'] as bool?) ?? false,
      requiresWifi: (json['requires_wifi'] as bool?) ?? false,
      requiresBiometric: (json['requires_biometric'] as bool?) ?? false,
      requiresFace: (json['requires_face'] as bool?) ?? false,
      maxAccuracyMeters: (json['max_accuracy_meters'] as num?)?.toInt() ?? 100,
      maxLocationAgeSeconds:
          (json['max_location_age_seconds'] as num?)?.toInt() ?? 30,
      maxWifiAgeSeconds: (json['max_wifi_age_seconds'] as num?)?.toInt() ?? 30,
      wifiFallbackAction: (json['wifi_fallback_action'] ?? 'REJECT').toString(),
      allowedFallbackMethods:
          (json['allowed_fallback_methods'] as List<dynamic>?)
                  ?.map((e) => e.toString())
                  .toList() ??
              const [],
    );
  }
}
