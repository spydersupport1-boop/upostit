import '../../../../core/network/api_client.dart';
import '../../../../core/network/api_endpoints.dart';
import '../models/device_register_request_model.dart';
import '../models/device_register_response_model.dart';
import '../models/device_status_response_model.dart';

/// Contract for remote device API calls.
abstract class DeviceRemoteDataSource {
  /// Fetches current employee's registered device status from GET /api/v1/devices/me.
  Future<DeviceStatusResponseModel> getMyDeviceStatus();

  /// Registers or binds the device via POST /api/v1/devices/register.
  Future<DeviceRegisterResponseModel> registerDevice(
      DeviceRegisterRequestModel request);
}

/// Implementation using [ApiClient].
class DeviceRemoteDataSourceImpl implements DeviceRemoteDataSource {
  final ApiClient _apiClient;

  DeviceRemoteDataSourceImpl(this._apiClient);

  @override
  Future<DeviceStatusResponseModel> getMyDeviceStatus() async {
    final response = await _apiClient.get(ApiEndpoints.devicesMe);
    return DeviceStatusResponseModel.fromJson(
        response.data as Map<String, dynamic>);
  }

  @override
  Future<DeviceRegisterResponseModel> registerDevice(
      DeviceRegisterRequestModel request) async {
    final response = await _apiClient.post(
      ApiEndpoints.devicesRegister,
      data: request.toJson(),
    );
    return DeviceRegisterResponseModel.fromJson(
        response.data as Map<String, dynamic>);
  }
}
