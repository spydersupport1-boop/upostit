import 'package:equatable/equatable.dart';

abstract class AuthEvent extends Equatable {
  const AuthEvent();

  @override
  List<Object?> get props => [];
}

/// Dispatched upon app launch to restore session from secure storage.
class AuthCheckRequested extends AuthEvent {
  const AuthCheckRequested();
}

/// Dispatched when user submits login credentials.
class LoginSubmitted extends AuthEvent {
  final String email;
  final String password;
  final String tenantSlug;

  const LoginSubmitted({
    required this.email,
    required this.password,
    required this.tenantSlug,
  });

  @override
  List<Object?> get props => [email, password, tenantSlug];
}

/// Dispatched when user taps logout.
class LogoutRequested extends AuthEvent {
  const LogoutRequested();
}

/// Dispatched by network interceptor when refresh token is rejected or revoked.
class SessionExpiredDetected extends AuthEvent {
  final String message;

  const SessionExpiredDetected(
      [this.message = 'Session expired. Please log in again.']);

  @override
  List<Object?> get props => [message];
}
