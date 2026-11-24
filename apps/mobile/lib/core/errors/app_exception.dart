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

class DatabaseCorruptedException extends AppException {
  final dynamic cause;
  final String? quarantinedPath;

  const DatabaseCorruptedException([
    super.message =
        'Encrypted database file cannot be decrypted or is corrupted. Fail-closed: database preserved.',
    this.cause,
    this.quarantinedPath,
  ]) : super(details: cause);
}

class DatabaseRecoveryException extends AppException {
  final dynamic cause;

  const DatabaseRecoveryException([
    super.message = 'Database recovery process failed or was aborted.',
    this.cause,
  ]) : super(details: cause);
}

class DeviceRevokedException extends AppException {
  final String? deviceIdHash;
  final String? revocationReason;

  const DeviceRevokedException([
    super.message =
        'This device has been revoked by organization security. Offline punches are frozen.',
    this.deviceIdHash,
    this.revocationReason,
  ]);
}

class StorageThresholdWarningException extends AppException {
  final int currentCount;
  final int maxCapacity;

  const StorageThresholdWarningException(
    this.currentCount,
    this.maxCapacity, [
    super.message = 'Offline storage usage is approaching maximum capacity.',
  ]);
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
