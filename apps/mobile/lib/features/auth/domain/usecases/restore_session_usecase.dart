import '../../../../core/errors/failure.dart';
import '../../../../core/errors/result.dart';
import '../../../../core/storage/secure_storage_service.dart';
import '../../../../core/storage/token_manager.dart';
import '../entities/auth_tokens.dart';
import '../repositories/auth_repository.dart';

class RestoreSessionUseCase {
  final AuthRepository _authRepository;
  final SecureStorageService _secureStorage;
  final TokenManager _tokenManager;

  RestoreSessionUseCase({
    required AuthRepository authRepository,
    required SecureStorageService secureStorage,
    required TokenManager tokenManager,
  })  : _authRepository = authRepository,
        _secureStorage = secureStorage,
        _tokenManager = tokenManager;

  Future<Result<AuthTokens>> call() async {
    final refreshToken = await _secureStorage.getRefreshToken();
    if (refreshToken == null || refreshToken.isEmpty) {
      return const Result.failure(
          AuthFailure('No stored session credentials found'));
    }

    final result = await _authRepository.refreshToken(refreshToken);

    return result.fold(
      (failure) async {
        // If it's an authentication invalidation / session expired, wipe local token
        if (failure is AuthFailure) {
          _tokenManager.clear();
          await _secureStorage.deleteRefreshToken();
        }
        // If it's a network failure, we preserve the token so the user can retry when online!
        return Result.failure(failure);
      },
      (tokens) async {
        _tokenManager.setAccessToken(tokens.accessToken);
        await _secureStorage.saveRefreshToken(tokens.refreshToken);
        return Result.success(tokens);
      },
    );
  }
}
