import '../../../../core/errors/failure.dart';
import '../../../../core/errors/result.dart';
import '../../../../core/storage/secure_storage_service.dart';
import '../../../../core/storage/token_manager.dart';
import '../repositories/auth_repository.dart';

class LogoutUseCase {
  final AuthRepository _authRepository;
  final SecureStorageService _secureStorage;
  final TokenManager _tokenManager;

  LogoutUseCase({
    required AuthRepository authRepository,
    required SecureStorageService secureStorage,
    required TokenManager tokenManager,
  })  : _authRepository = authRepository,
        _secureStorage = secureStorage,
        _tokenManager = tokenManager;

  Future<Result<void>> call() async {
    final refreshToken = await _secureStorage.getRefreshToken();

    // Attempt online server revocation first
    Result<void> serverResult = const Result.success(null);
    if (refreshToken != null && refreshToken.isNotEmpty) {
      serverResult = await _authRepository.logout(refreshToken: refreshToken);
    }

    // Always clear local access token and local secure refresh token
    _tokenManager.clear();
    await _secureStorage.deleteRefreshToken();

    return serverResult.fold(
      (failure) {
        if (failure is NetworkFailure) {
          return const Result.failure(
            NetworkFailure(
              'Logged out locally. Server session revocation could not be confirmed while offline.',
            ),
          );
        }
        return Result.failure(failure);
      },
      (_) => const Result.success(null),
    );
  }
}
