import 'package:equatable/equatable.dart';
import '../../domain/entities/user_profile.dart';

abstract class AuthState extends Equatable {
  const AuthState();

  @override
  List<Object?> get props => [];
}

/// Initial uninitialized state before session check completes.
class AuthInitial extends AuthState {
  const AuthInitial();
}

/// State while an asynchronous auth action is executing (logging in, refreshing).
class AuthLoading extends AuthState {
  final String? message;

  const AuthLoading({this.message});

  @override
  List<Object?> get props => [message];
}

/// Authenticated user session state.
class Authenticated extends AuthState {
  final UserProfile userProfile;

  const Authenticated({required this.userProfile});

  TenantEntity get tenant => userProfile.tenant;
  UserEntity get user => userProfile.user;

  @override
  List<Object?> get props => [userProfile];
}

/// Unauthenticated state (user logged out or initial login screen).
class Unauthenticated extends AuthState {
  final String? errorMessage;
  final String? infoMessage;
  final String? savedTenantSlug;
  final String? savedEmail;

  const Unauthenticated({
    this.errorMessage,
    this.infoMessage,
    this.savedTenantSlug,
    this.savedEmail,
  });

  @override
  List<Object?> get props =>
      [errorMessage, infoMessage, savedTenantSlug, savedEmail];
}

/// Offline or recoverable error during session restoration.
class AuthRestoreError extends AuthState {
  final String message;
  final bool isNetworkError;

  const AuthRestoreError({
    required this.message,
    this.isNetworkError = true,
  });

  @override
  List<Object?> get props => [message, isNetworkError];
}
