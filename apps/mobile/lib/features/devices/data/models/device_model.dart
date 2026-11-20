import '../../domain/entities/device_binding_status.dart';
import '../../domain/entities/device_info.dart';

/// Data Transfer Object for backend [DeviceResponse].
class DeviceModel extends DeviceInfo {
  const DeviceModel({
    required super.id,
    required super.tenantId,
    required super.employeeId,
    required super.platform,
    super.deviceModel,
    super.osName,
    super.osVersion,
    super.appVersion,
    required super.status,
    required super.registeredAt,
    super.lastSeenAt,
    super.revokedAt,
    super.revocationReason,
  });

  factory DeviceModel.fromJson(Map<String, dynamic> json) {
    return DeviceModel(
      id: json['id'] as String,
      tenantId: json['tenant_id'] as String,
      employeeId: json['employee_id'] as String,
      platform: json['platform'] as String? ?? 'OTHER',
      deviceModel: json['device_model'] as String?,
      osName: json['os_name'] as String?,
      osVersion: json['os_version'] as String?,
      appVersion: json['app_version'] as String?,
      status: DeviceBindingStatus.fromString(json['status'] as String?),
      registeredAt: DateTime.parse(json['registered_at'] as String).toUtc(),
      lastSeenAt: json['last_seen_at'] != null
          ? DateTime.parse(json['last_seen_at'] as String).toUtc()
          : null,
      revokedAt: json['revoked_at'] != null
          ? DateTime.parse(json['revoked_at'] as String).toUtc()
          : null,
      revocationReason: json['revocation_reason'] as String?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'tenant_id': tenantId,
      'employee_id': employeeId,
      'platform': platform,
      if (deviceModel != null) 'device_model': deviceModel,
      if (osName != null) 'os_name': osName,
      if (osVersion != null) 'os_version': osVersion,
      if (appVersion != null) 'app_version': appVersion,
      'status': status.name.toUpperCase(),
      'registered_at': registeredAt.toIso8601String(),
      if (lastSeenAt != null) 'last_seen_at': lastSeenAt!.toIso8601String(),
      if (revokedAt != null) 'revoked_at': revokedAt!.toIso8601String(),
      if (revocationReason != null) 'revocation_reason': revocationReason,
    };
  }
}
