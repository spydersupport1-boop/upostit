import 'dart:async';
import '../../domain/entities/push_notification_payload.dart';
import 'push_notification_service.dart';

/// Test and development mock implementation of [PushNotificationService].
class MockPushNotificationService implements PushNotificationService {
  final StreamController<String> _tokenRefreshController =
      StreamController<String>.broadcast();
  final StreamController<PushNotificationPayload> _foregroundController =
      StreamController<PushNotificationPayload>.broadcast();
  final StreamController<PushNotificationPayload> _tappedController =
      StreamController<PushNotificationPayload>.broadcast();

  bool isPermissionGranted = true;
  bool shouldFailInitialization = false;
  String? mockToken = 'mock_fcm_token_sample_1234567890_device';
  PushNotificationPayload? initialNotificationPayload;
  int deleteTokenCallCount = 0;

  @override
  bool isConfigured = true;

  @override
  Future<bool> initialize() async {
    if (shouldFailInitialization) {
      isConfigured = false;
      return false;
    }
    return true;
  }

  @override
  Future<bool> requestNotificationPermissions() async {
    return isPermissionGranted;
  }

  @override
  Future<String?> getDeviceToken() async {
    if (!isPermissionGranted || !isConfigured) return null;
    return mockToken;
  }

  @override
  Stream<String> get onTokenRefresh => _tokenRefreshController.stream;

  @override
  Stream<PushNotificationPayload> get onForegroundNotification =>
      _foregroundController.stream;

  @override
  Stream<PushNotificationPayload> get onNotificationTapped =>
      _tappedController.stream;

  @override
  Future<PushNotificationPayload?> getInitialNotification() async {
    return initialNotificationPayload;
  }

  @override
  Future<void> deleteToken() async {
    deleteTokenCallCount++;
    mockToken = null;
  }

  /// Helper for tests to simulate incoming foreground push messages.
  void simulateForegroundMessage(PushNotificationPayload payload) {
    _foregroundController.add(payload);
  }

  /// Helper for tests to simulate tapping a push message from background.
  void simulateNotificationTap(PushNotificationPayload payload) {
    _tappedController.add(payload);
  }

  /// Helper for tests to simulate FCM token refresh.
  void simulateTokenRefresh(String newToken) {
    mockToken = newToken;
    _tokenRefreshController.add(newToken);
  }

  void dispose() {
    _tokenRefreshController.close();
    _foregroundController.close();
    _tappedController.close();
  }
}
