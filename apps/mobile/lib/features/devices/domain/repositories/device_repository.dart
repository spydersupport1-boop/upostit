import '../../../../core/errors/result.dart';
import '../entities/device_info.dart';
import '../entities/device_status_result.dart';

/// Contract for device binding, registration, and status queries.
abstract class DeviceRepository {
  /// Fetches the current binding status for the authenticated employee and device.
  Future<Result<DeviceStatusResult>> getDeviceStatus();

  /// Registers the current mobile installation with the backend device binding service.
  Future<Result<DeviceInfo>> registerCurrentDevice();
}
