import '../../../../core/errors/app_exception.dart';
import '../../../../core/network/api_client.dart';
import '../../../../core/network/api_endpoints.dart';
import '../models/device_token_register_request_model.dart';
import '../models/in_app_notification_model.dart';
import '../models/push_device_registration_model.dart';

/// Contract for remote communication with FastAPI notifications endpoints.
abstract class NotificationRemoteDataSource {
  Future<PushDeviceRegistrationModel> registerDeviceToken(
      DeviceTokenRegisterRequestModel request);

  Future<List<PushDeviceRegistrationModel>> listActiveDeviceTokens();

  Future<void> revokeDeviceToken(String rawToken);

  Future<void> revokeDeviceTokenByHash(String tokenHash);

  Future<List<InAppNotificationModel>> getNotificationInbox(
      {int limit = 20, int offset = 0});

  Future<void> markNotificationAsRead(String notificationId);
}

/// Implementation using [ApiClient].
class NotificationRemoteDataSourceImpl implements NotificationRemoteDataSource {
  final ApiClient _apiClient;

  NotificationRemoteDataSourceImpl(this._apiClient);

  @override
  Future<PushDeviceRegistrationModel> registerDeviceToken(
      DeviceTokenRegisterRequestModel request) async {
    final response = await _apiClient.post(
      ApiEndpoints.notificationDevices,
      data: request.toJson(),
    );

    if (response.data is Map<String, dynamic>) {
      return PushDeviceRegistrationModel.fromJson(
          response.data as Map<String, dynamic>);
    }
    throw const ServerException(
        'Malformed device registration response from server');
  }

  @override
  Future<List<PushDeviceRegistrationModel>> listActiveDeviceTokens() async {
    final response = await _apiClient.get(ApiEndpoints.notificationDevices);

    if (response.data is List) {
      final list = response.data as List;
      return list
          .map((item) => PushDeviceRegistrationModel.fromJson(
              item as Map<String, dynamic>))
          .toList();
    }
    return [];
  }

  @override
  Future<void> revokeDeviceToken(String rawToken) async {
    await _apiClient.post(
      ApiEndpoints.notificationDevicesRevoke,
      data: {'token': rawToken},
    );
  }

  @override
  Future<void> revokeDeviceTokenByHash(String tokenHash) async {
    await _apiClient.delete(
      ApiEndpoints.notificationDeviceByHash(tokenHash),
    );
  }

  @override
  Future<List<InAppNotificationModel>> getNotificationInbox({
    int limit = 20,
    int offset = 0,
  }) async {
    try {
      final response = await _apiClient.get(
        ApiEndpoints.notificationInbox,
        queryParameters: {
          'limit': limit,
          'offset': offset,
        },
      );

      if (response.data is Map && (response.data as Map).containsKey('items')) {
        final items = (response.data as Map)['items'] as List;
        return items
            .map((item) =>
                InAppNotificationModel.fromJson(item as Map<String, dynamic>))
            .toList();
      } else if (response.data is List) {
        return (response.data as List)
            .map((item) =>
                InAppNotificationModel.fromJson(item as Map<String, dynamic>))
            .toList();
      }
      return [];
    } on ServerException catch (e) {
      if (e.statusCode == 404 || e.statusCode == 501) {
        // Backend API Gap: Inbox endpoint is not yet implemented on the server
        throw ApiGapException(
          'In-app notification inbox endpoint (${ApiEndpoints.notificationInbox}) is not yet available on the backend.',
          e.statusCode,
        );
      }
      rethrow;
    }
  }

  @override
  Future<void> markNotificationAsRead(String notificationId) async {
    try {
      await _apiClient.post(
        '${ApiEndpoints.notificationInbox}/$notificationId/read',
      );
    } on ServerException catch (e) {
      if (e.statusCode == 404 || e.statusCode == 501) {
        // Backend API Gap: mark-as-read endpoint is not yet implemented on the server
        throw ApiGapException(
          'Mark-as-read endpoint is not yet available on the backend.',
          e.statusCode,
        );
      }
      rethrow;
    }
  }
}
