import '../../../../core/network/api_client.dart';
import '../../../../core/network/api_endpoints.dart';
import '../models/auth_tokens_model.dart';
import '../models/user_profile_model.dart';

abstract class AuthRemoteDataSource {
  Future<AuthTokensModel> login({
    required String email,
    required String password,
    required String tenantSlug,
  });

  Future<AuthTokensModel> refresh({required String refreshToken});

  Future<UserProfileModel> getMe();

  Future<void> logout({required String? refreshToken});
}

class AuthRemoteDataSourceImpl implements AuthRemoteDataSource {
  final ApiClient _apiClient;

  AuthRemoteDataSourceImpl(this._apiClient);

  @override
  Future<AuthTokensModel> login({
    required String email,
    required String password,
    required String tenantSlug,
  }) async {
    final response = await _apiClient.post(
      ApiEndpoints.login,
      data: {
        'email': email,
        'password': password,
        'tenant_slug': tenantSlug,
      },
    );

    return AuthTokensModel.fromJson(response.data as Map<String, dynamic>);
  }

  @override
  Future<AuthTokensModel> refresh({required String refreshToken}) async {
    final response = await _apiClient.post(
      ApiEndpoints.refresh,
      data: {'refresh_token': refreshToken},
    );

    return AuthTokensModel.fromJson(response.data as Map<String, dynamic>);
  }

  @override
  Future<UserProfileModel> getMe() async {
    final response = await _apiClient.get(ApiEndpoints.authMe);
    return UserProfileModel.fromJson(response.data as Map<String, dynamic>);
  }

  @override
  Future<void> logout({required String? refreshToken}) async {
    await _apiClient.post(
      ApiEndpoints.logout,
      data: refreshToken != null ? {'refresh_token': refreshToken} : null,
    );
  }
}
