/// Request DTO for registering an FCM push token with the backend.
class DeviceTokenRegisterRequestModel {
  final String platform;
  final String token;
  final String? deviceModel;
  final String? osVersion;
  final String? appVersion;

  const DeviceTokenRegisterRequestModel({
    required this.platform,
    required this.token,
    this.deviceModel,
    this.osVersion,
    this.appVersion,
  });

  Map<String, dynamic> toJson() {
    return {
      'platform': platform.toUpperCase(),
      'token': token,
      if (deviceModel != null) 'device_model': deviceModel,
      if (osVersion != null) 'os_version': osVersion,
      if (appVersion != null) 'app_version': appVersion,
    };
  }
}
