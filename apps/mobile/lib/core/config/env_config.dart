/// Application environment configuration.
///
/// Reads runtime or compile-time variables passed via:
/// flutter run --dart-define=API_BASE_URL=https://api.yourdomain.com
class EnvConfig {
  /// Base URL pointing to the FastAPI backend modular monolith.
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8000',
  );

  /// Application environment identifier (development, staging, production).
  static const String environment = String.fromEnvironment(
    'APP_ENV',
    defaultValue: 'development',
  );

  /// HTTP client connection timeout in milliseconds.
  static const int connectTimeoutMs = int.fromEnvironment(
    'CONNECT_TIMEOUT_MS',
    defaultValue: 15000,
  );

  /// HTTP client receive timeout in milliseconds.
  static const int receiveTimeoutMs = int.fromEnvironment(
    'RECEIVE_TIMEOUT_MS',
    defaultValue: 15000,
  );

  /// Returns true if running in development mode.
  static bool get isDevelopment => environment == 'development';

  /// Returns true if using HTTPS in production.
  static bool get isSecure => apiBaseUrl.startsWith('https://');
}
