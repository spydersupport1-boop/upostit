import '../../domain/entities/push_notification_payload.dart';

/// Contract for device-level push notification services (FCM or mock).
abstract class PushNotificationService {
  /// Initializes the underlying messaging service.
  /// Returns `true` if initialization succeeded, or `false` if Firebase is unconfigured.
  Future<bool> initialize();

  /// Requests user permission to display alerts and badge icons.
  /// Returns `true` if permission was granted.
  Future<bool> requestNotificationPermissions();

  /// Retrieves the unique platform push registration token.
  /// Returns `null` if permission was denied or push is unconfigured.
  Future<String?> getDeviceToken();

  /// Stream of new tokens emitted when FCM rotates or refreshes the registration token.
  Stream<String> get onTokenRefresh;

  /// Stream of push notifications received while the application is in the foreground.
  Stream<PushNotificationPayload> get onForegroundNotification;

  /// Stream emitted when a user taps a system notification from background/notification tray.
  Stream<PushNotificationPayload> get onNotificationTapped;

  /// Retrieves the notification payload if the application was cold-launched from a tapped notification.
  Future<PushNotificationPayload?> getInitialNotification();

  /// Whether the push service is configured with live credentials.
  bool get isConfigured;

  /// Deletes the local registration token on device (e.g. during logout).
  Future<void> deleteToken();
}
