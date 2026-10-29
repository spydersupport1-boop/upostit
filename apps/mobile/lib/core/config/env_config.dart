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

  /// Returns true if running in development mode.
  static bool get isDevelopment => environment == 'development';
}
