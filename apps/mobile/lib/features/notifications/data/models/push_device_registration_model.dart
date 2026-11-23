import '../../domain/entities/push_device_registration.dart';

/// Data transfer object mapping backend [DevicePushTokenResponse] JSON payloads.
class PushDeviceRegistrationModel extends PushDeviceRegistration {
  const PushDeviceRegistrationModel({
    required super.id,
    required super.tenantId,
    required super.userId,
    super.employeeId,
    required super.platform,
    required super.tokenPreview,
    super.deviceModel,
    super.osVersion,
    super.appVersion,
    required super.status,
    required super.lastSeenAt,
    required super.createdAt,
  });

  factory PushDeviceRegistrationModel.fromJson(Map<String, dynamic> json) {
    return PushDeviceRegistrationModel(
      id: json['id'] as String,
      tenantId: json['tenant_id'] as String,
      userId: json['user_id'] as String,
      employeeId: json['employee_id'] as String?,
      platform: json['platform'] as String? ?? 'ANDROID',
      tokenPreview: json['token_preview'] as String? ?? '***',
      deviceModel: json['device_model'] as String?,
      osVersion: json['os_version'] as String?,
      appVersion: json['app_version'] as String?,
      status: json['status'] as String? ?? 'ACTIVE',
      lastSeenAt: json['last_seen_at'] != null
          ? DateTime.parse(json['last_seen_at'] as String)
          : DateTime.now(),
      createdAt: json['created_at'] != null
          ? DateTime.parse(json['created_at'] as String)
          : DateTime.now(),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'tenant_id': tenantId,
      'user_id': userId,
      'employee_id': employeeId,
      'platform': platform,
      'token_preview': tokenPreview,
      'device_model': deviceModel,
      'os_version': osVersion,
      'app_version': appVersion,
      'status': status,
      'last_seen_at': lastSeenAt.toIso8601String(),
      'created_at': createdAt.toIso8601String(),
    };
  }
}
