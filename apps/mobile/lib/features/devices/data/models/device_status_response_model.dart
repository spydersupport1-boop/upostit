import '../../domain/entities/device_binding_status.dart';
import '../../domain/entities/device_status_result.dart';
import 'device_model.dart';

/// DTO mapping response of GET /api/v1/devices/me.
class DeviceStatusResponseModel extends DeviceStatusResult {
  const DeviceStatusResponseModel({
    required super.isBound,
    required super.status,
    super.device,
  });

  factory DeviceStatusResponseModel.fromJson(Map<String, dynamic> json) {
    final rawStatus = json['status'] as String?;
    final deviceJson = json['device'] as Map<String, dynamic>?;

    return DeviceStatusResponseModel(
      isBound: json['is_bound'] as bool? ?? false,
      status: DeviceBindingStatus.fromString(rawStatus),
      device: deviceJson != null ? DeviceModel.fromJson(deviceJson) : null,
    );
  }
}
