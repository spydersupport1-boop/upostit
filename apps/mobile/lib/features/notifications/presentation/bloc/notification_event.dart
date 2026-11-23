import 'package:equatable/equatable.dart';
import '../../domain/entities/in_app_notification.dart';
import '../../domain/entities/push_notification_payload.dart';

abstract class NotificationEvent extends Equatable {
  const NotificationEvent();

  @override
  List<Object?> get props => [];
}

/// Request to initialize push notifications, request permissions, and register token with backend.
class InitializePushNotifications extends NotificationEvent {
  final bool force;
  const InitializePushNotifications({this.force = false});

  @override
  List<Object?> get props => [force];
}

/// Dispatched when FCM rotates or refreshes the device token.
class TokenRefreshed extends NotificationEvent {
  final String newToken;
  const TokenRefreshed(this.newToken);

  @override
  List<Object?> get props => [newToken];
}

/// Dispatched on user logout or account switch to revoke the device token.
class RevokeDeviceTokenRequested extends NotificationEvent {
  const RevokeDeviceTokenRequested();
}

/// Dispatched to query in-app notification center inbox.
class FetchNotificationInboxRequested extends NotificationEvent {
  final bool isRefresh;
  const FetchNotificationInboxRequested({this.isRefresh = false});

  @override
  List<Object?> get props => [isRefresh];
}

/// Dispatched when a push notification is received while app is in foreground.
class ForegroundNotificationReceived extends NotificationEvent {
  final PushNotificationPayload payload;
  const ForegroundNotificationReceived(this.payload);

  @override
  List<Object?> get props => [payload];
}

/// Dispatched when a user taps a notification banner or tile.
class NotificationTappedEvent extends NotificationEvent {
  final InAppNotification notification;
  const NotificationTappedEvent(this.notification);

  @override
  List<Object?> get props => [notification];
}

/// Dispatched to mark a specific notification as read.
class MarkNotificationAsReadRequested extends NotificationEvent {
  final String notificationId;
  const MarkNotificationAsReadRequested(this.notificationId);

  @override
  List<Object?> get props => [notificationId];
}

/// Clears session notifications and resets state (e.g. on user logout).
class ClearNotificationSession extends NotificationEvent {
  const ClearNotificationSession();
}

/// Consumes a pending navigation route after GoRouter transitions.
class ClearNavigationRoute extends NotificationEvent {
  const ClearNavigationRoute();
}
