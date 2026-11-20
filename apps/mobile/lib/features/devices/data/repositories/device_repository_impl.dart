import 'package:dio/dio.dart';
import '../../../../core/errors/failure.dart';
import '../../../../core/errors/result.dart';
import '../../domain/entities/device_info.dart';
import '../../domain/entities/device_status_result.dart';
import '../../domain/repositories/device_repository.dart';
import '../datasources/device_remote_data_source.dart';
import '../models/device_register_request_model.dart';
import '../services/device_identity_service.dart';

/// Implementation of [DeviceRepository] using [DeviceRemoteDataSource] and [DeviceIdentityService].
class DeviceRepositoryImpl implements DeviceRepository {
  final DeviceRemoteDataSource remoteDataSource;
  final DeviceIdentityService deviceIdentityService;

  DeviceRepositoryImpl({
    required this.remoteDataSource,
    required this.deviceIdentityService,
  });

  @override
  Future<Result<DeviceStatusResult>> getDeviceStatus() async {
    try {
      final response = await remoteDataSource.getMyDeviceStatus();
      return Result.success(response);
    } on DioException catch (dioError) {
      return Result.failure(_mapDioError(dioError));
    } catch (e) {
      return Result.failure(ServerFailure(e.toString()));
    }
  }

  @override
  Future<Result<DeviceInfo>> registerCurrentDevice() async {
    try {
      final deviceId = await deviceIdentityService.getOrCreateInstallationId();
      final platformInfo = await deviceIdentityService.getPlatformMetadata();

      final request = DeviceRegisterRequestModel(
        deviceId: deviceId,
        platform: platformInfo.platform,
        deviceModel: platformInfo.deviceModel,
        osName: platformInfo.osName,
        osVersion: platformInfo.osVersion,
        appVersion: platformInfo.appVersion,
        metadata: platformInfo.metadata,
      );

      final response = await remoteDataSource.registerDevice(request);
      return Result.success(response.device);
    } on DioException catch (dioError) {
      return Result.failure(_mapDioError(dioError));
    } catch (e) {
      return Result.failure(ServerFailure(e.toString()));
    }
  }

  Failure _mapDioError(DioException dioError) {
    if (dioError.type == DioExceptionType.connectionTimeout ||
        dioError.type == DioExceptionType.sendTimeout ||
        dioError.type == DioExceptionType.receiveTimeout ||
        dioError.type == DioExceptionType.connectionError) {
      return const NetworkFailure(
          'Unable to connect to server. Please check your network connection.');
    }

    final statusCode = dioError.response?.statusCode;
    final responseData = dioError.response?.data;
    String errorMessage = 'A server error occurred. Please try again.';

    if (responseData is Map<String, dynamic>) {
      if (responseData['detail'] != null) {
        final detail = responseData['detail'];
        if (detail is String) {
          errorMessage = detail;
        } else if (detail is List && detail.isNotEmpty) {
          final first = detail.first;
          if (first is Map && first['msg'] != null) {
            errorMessage = first['msg'].toString();
          }
        }
      } else if (responseData['message'] != null) {
        errorMessage = responseData['message'].toString();
      }
    }

    return ServerFailure(errorMessage, statusCode: statusCode);
  }
}
