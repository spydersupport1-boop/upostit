import 'package:equatable/equatable.dart';

/// Clean Architecture Failure representation for domain and presentation layers.
abstract class Failure extends Equatable {
  final String message;
  final int? statusCode;

  const Failure(this.message, {this.statusCode});

  @override
  List<Object?> get props => [message, statusCode];
}

class ServerFailure extends Failure {
  const ServerFailure(super.message, {super.statusCode});
}

class NetworkFailure extends Failure {
  const NetworkFailure(
      [super.message =
          'Unable to connect to server. Please check your network connection.']);
}

class AuthFailure extends Failure {
  final bool isSessionExpired;
  final bool isReuseDetected;

  const AuthFailure(
    super.message, {
    super.statusCode = 401,
    this.isSessionExpired = false,
    this.isReuseDetected = false,
  });

  @override
  List<Object?> get props =>
      [message, statusCode, isSessionExpired, isReuseDetected];
}

class StorageFailure extends Failure {
  const StorageFailure(
      [super.message = 'Failed to access local secure credentials']);
}
