import '../../../../core/errors/result.dart';
import '../entities/in_app_notification.dart';
import '../entities/push_device_registration.dart';

/// Contract for notification operations including device push token lifecycle
/// and in-app notification center querying.
abstract class NotificationRepository {
  /// Registers or rotates an FCM device push token with the backend.
  Future<Result<PushDeviceRegistration>> registerDeviceToken({
    required String token,
    required String platform,
    String? deviceModel,
    String? osVersion,
    String? appVersion,
    bool force = false,
  });

  /// Lists active push device registrations for the authenticated user.
  Future<Result<List<PushDeviceRegistration>>> listActiveDeviceTokens();

  /// Revokes a device token by its raw token value.
  Future<Result<void>> revokeDeviceToken(String token);

  /// Revokes a device token by its SHA-256 token hash.
  Future<Result<void>> revokeDeviceTokenByHash(String tokenHash);

  /// Fetches in-app notifications for the authenticated user.
  /// If the backend does not expose an inbox endpoint, returns an [ApiGapFailure]
  /// or merges session notifications gracefully.
  Future<Result<List<InAppNotification>>> getNotificationInbox();

  /// Marks a specific notification as read.
  Future<Result<void>> markNotificationAsRead(String notificationId);

  /// Stream of new notifications received during the active session.
  Stream<InAppNotification> get onNotificationReceived;

  /// Adds a notification received in foreground/background to the local session cache.
  void addSessionNotification(InAppNotification notification);

  /// Returns current in-memory session notifications.
  List<InAppNotification> get sessionNotifications;
}
