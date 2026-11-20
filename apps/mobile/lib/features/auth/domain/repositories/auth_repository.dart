import '../../../../core/errors/result.dart';
import '../entities/auth_tokens.dart';
import '../entities/user_profile.dart';

/// Contract for authentication operations decoupled from transport implementation.
abstract class AuthRepository {
  /// Authenticates user against specific tenant slug.
  Future<Result<AuthTokens>> login({
    required String email,
    required String password,
    required String tenantSlug,
  });

  /// Rotates refresh token and returns new access/refresh token pair.
  Future<Result<AuthTokens>> refreshToken(String refreshToken);

  /// Retrieves current authenticated user and company profile.
  Future<Result<UserProfile>> getMe();

  /// Revokes active session on server when online.
  Future<Result<void>> logout({required String? refreshToken});
}
