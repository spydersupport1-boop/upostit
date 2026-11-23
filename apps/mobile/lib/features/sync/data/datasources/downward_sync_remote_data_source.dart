import '../../../../core/network/api_client.dart';
import '../../../../core/network/api_endpoints.dart';
import '../models/sync_delta_model.dart';

abstract class DownwardSyncRemoteDataSource {
  Future<SyncDeltaModel> fetchDelta({String? cursor, int limit = 50});
}

class DownwardSyncRemoteDataSourceImpl implements DownwardSyncRemoteDataSource {
  final ApiClient _apiClient;

  DownwardSyncRemoteDataSourceImpl(this._apiClient);

  @override
  Future<SyncDeltaModel> fetchDelta({String? cursor, int limit = 50}) async {
    final Map<String, dynamic> queryParams = {
      'limit': limit,
    };
    if (cursor != null && cursor.trim().isNotEmpty) {
      queryParams['cursor'] = cursor;
    }

    final response = await _apiClient.get(
      ApiEndpoints.syncDelta,
      queryParameters: queryParams,
    );

    final data = response.data as Map<String, dynamic>;
    return SyncDeltaModel.fromJson(data);
  }
}

