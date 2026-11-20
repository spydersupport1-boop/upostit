import '../../../../core/errors/app_exception.dart';
import '../../../../core/errors/failure.dart';
import '../../../../core/errors/result.dart';
import '../../../../core/storage/secure_storage_service.dart';
import '../../../../core/storage/token_manager.dart';
import '../../domain/entities/auth_tokens.dart';
import '../../domain/entities/user_profile.dart';
import '../../domain/repositories/auth_repository.dart';
import '../datasources/auth_remote_data_source.dart';

class AuthRepositoryImpl implements AuthRepository {
  final AuthRemoteDataSource _remoteDataSource;
  final TokenManager _tokenManager;
  final SecureStorageService _secureStorage;

  AuthRepositoryImpl({
    required AuthRemoteDataSource remoteDataSource,
    required TokenManager tokenManager,
    required SecureStorageService secureStorage,
  })  : _remoteDataSource = remoteDataSource,
        _tokenManager = tokenManager,
        _secureStorage = secureStorage;

  @override
  Future<Result<AuthTokens>> login({
    required String email,
    required String password,
    required String tenantSlug,
  }) async {
    try {
      final tokens = await _remoteDataSource.login(
        email: email,
        password: password,
        tenantSlug: tenantSlug,
      );

      // Invariant: Access token stored strictly in volatile memory
      _tokenManager.setAccessToken(tokens.accessToken);

      // Invariant: Refresh token stored in platform-secure storage
      await _secureStorage.saveRefreshToken(tokens.refreshToken);
      await _secureStorage.saveTenantSlug(tenantSlug);
      await _secureStorage.saveEmail(email);

      return Result.success(tokens);
    } on NetworkException catch (e) {
      return Result.failure(NetworkFailure(e.message));
    } on AuthException catch (e) {
      return Result.failure(
        AuthFailure(
          e.message,
          statusCode: e.statusCode,
          isSessionExpired: e.isSessionExpired,
          isReuseDetected: e.isReuseDetected,
        ),
      );
    } on ServerException catch (e) {
      return Result.failure(ServerFailure(e.message, statusCode: e.statusCode));
    } catch (e) {
      return Result.failure(ServerFailure(e.toString()));
    }
  }

  @override
  Future<Result<AuthTokens>> refreshToken(String refreshToken) async {
    try {
      final tokens =
          await _remoteDataSource.refresh(refreshToken: refreshToken);

      _tokenManager.setAccessToken(tokens.accessToken);
      await _secureStorage.saveRefreshToken(tokens.refreshToken);

      return Result.success(tokens);
    } on NetworkException catch (e) {
      return Result.failure(NetworkFailure(e.message));
    } on AuthException catch (e) {
      return Result.failure(
        AuthFailure(
          e.message,
          statusCode: e.statusCode,
          isSessionExpired: e.isSessionExpired,
          isReuseDetected: e.isReuseDetected,
        ),
      );
    } on ServerException catch (e) {
      return Result.failure(ServerFailure(e.message, statusCode: e.statusCode));
    } catch (e) {
      return Result.failure(ServerFailure(e.toString()));
    }
  }

  @override
  Future<Result<UserProfile>> getMe() async {
    try {
      final profile = await _remoteDataSource.getMe();
      return Result.success(profile);
    } on NetworkException catch (e) {
      return Result.failure(NetworkFailure(e.message));
    } on AuthException catch (e) {
      return Result.failure(
        AuthFailure(
          e.message,
          statusCode: e.statusCode,
          isSessionExpired: e.isSessionExpired,
          isReuseDetected: e.isReuseDetected,
        ),
      );
    } on ServerException catch (e) {
      return Result.failure(ServerFailure(e.message, statusCode: e.statusCode));
    } catch (e) {
      return Result.failure(ServerFailure(e.toString()));
    }
  }

  @override
  Future<Result<void>> logout({required String? refreshToken}) async {
    try {
      await _remoteDataSource.logout(refreshToken: refreshToken);
      _tokenManager.clear();
      await _secureStorage.deleteRefreshToken();
      return const Result.success(null);
    } on NetworkException catch (e) {
      // Offline logout: local credentials still cleared in use case
      return Result.failure(NetworkFailure(e.message));
    } on ServerException catch (e) {
      return Result.failure(ServerFailure(e.message, statusCode: e.statusCode));
    } catch (e) {
      return Result.failure(ServerFailure(e.toString()));
    }
  }
}
