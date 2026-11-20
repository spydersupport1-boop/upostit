/// Request payload for POST /api/v1/devices/register.
class DeviceRegisterRequestModel {
  final String deviceId;
  final String platform;
  final String? deviceModel;
  final String? osName;
  final String? osVersion;
  final String? appVersion;
  final Map<String, dynamic> metadata;

  const DeviceRegisterRequestModel({
    required this.deviceId,
    required this.platform,
    this.deviceModel,
    this.osName,
    this.osVersion,
    this.appVersion,
    this.metadata = const {},
  });

  Map<String, dynamic> toJson() {
    return {
      'device_id': deviceId,
      'platform': platform.toUpperCase(),
      if (deviceModel != null) 'device_model': deviceModel,
      if (osName != null) 'os_name': osName,
      if (osVersion != null) 'os_version': osVersion,
      if (appVersion != null) 'app_version': appVersion,
      'metadata': metadata,
    };
  }
}
