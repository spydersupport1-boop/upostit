/// Core application exception hierarchy.
abstract class AppException implements Exception {
  final String message;
  final int? statusCode;
  final dynamic details;

  const AppException(this.message, {this.statusCode, this.details});

  @override
  String toString() => message;
}

class ServerException extends AppException {
  const ServerException(super.message, {super.statusCode, super.details});
}

class NetworkException extends AppException {
  const NetworkException(
      [super.message =
          'Network connection unavailable. Please check your internet connection.']);
}

class AuthException extends AppException {
  final bool isSessionExpired;
  final bool isReuseDetected;

  const AuthException(
    super.message, {
    super.statusCode = 401,
    super.details,
    this.isSessionExpired = false,
    this.isReuseDetected = false,
  });
}

class StorageException extends AppException {
  const StorageException([super.message = 'Secure storage access failure']);
}

class DatabaseEncryptionException extends AppException {
  final dynamic cause;
  final StackTrace? stackTrace;

  const DatabaseEncryptionException([
    super.message =
        'Secure database initialization failed. Plaintext fallback is prohibited.',
    this.cause,
    this.stackTrace,
  ]) : super(details: cause);
}

class QueueCapacityExceededException extends AppException {
  const QueueCapacityExceededException(
      [super.message =
          'Local offline queue capacity exceeded (maximum 500 pending events).']);
}

class ApiGapException extends AppException {
  const ApiGapException([
    super.message =
        'This operation is not currently supported by the backend API.',
    int? statusCode = 404,
  ]) : super(statusCode: statusCode);
}
