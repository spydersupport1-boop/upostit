import 'device_model.dart';

/// DTO mapping response of POST /api/v1/devices/register.
class DeviceRegisterResponseModel {
  final DeviceModel device;
  final bool requiresApproval;
  final String message;

  const DeviceRegisterResponseModel({
    required this.device,
    required this.requiresApproval,
    required this.message,
  });

  factory DeviceRegisterResponseModel.fromJson(Map<String, dynamic> json) {
    return DeviceRegisterResponseModel(
      device: DeviceModel.fromJson(json['device'] as Map<String, dynamic>),
      requiresApproval: json['requires_approval'] as bool? ?? false,
      message: json['message'] as String? ?? '',
    );
  }
}
