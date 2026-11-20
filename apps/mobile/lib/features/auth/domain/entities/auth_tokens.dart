import 'package:equatable/equatable.dart';

/// Domain entity representing issued authentication credentials.
class AuthTokens extends Equatable {
  final String accessToken;
  final String refreshToken;
  final String tokenType;
  final int expiresIn;

  const AuthTokens({
    required this.accessToken,
    required this.refreshToken,
    this.tokenType = 'bearer',
    required this.expiresIn,
  });

  @override
  List<Object?> get props => [accessToken, refreshToken, tokenType, expiresIn];
}
