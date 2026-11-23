import 'package:equatable/equatable.dart';
import '../../domain/entities/in_app_notification.dart';
import '../../domain/entities/push_device_registration.dart';

abstract class NotificationState extends Equatable {
  const NotificationState();

  @override
  List<Object?> get props => [];
}

class NotificationInitial extends NotificationState {
  const NotificationInitial();
}

class NotificationLoading extends NotificationState {
  final String? message;
  const NotificationLoading({this.message});

  @override
  List<Object?> get props => [message];
}

class NotificationLoaded extends NotificationState {
  final List<InAppNotification> notifications;
  final int unreadCount;
  final PushDeviceRegistration? activeRegistration;
  final bool isPushConfigured;
  final bool isPermissionGranted;
  final bool hasApiGap;
  final String? apiGapMessage;
  final String? navigationRoute;
  final String? noticeMessage;

  const NotificationLoaded({
    this.notifications = const [],
    this.unreadCount = 0,
    this.activeRegistration,
    this.isPushConfigured = false,
    this.isPermissionGranted = false,
    this.hasApiGap = false,
    this.apiGapMessage,
    this.navigationRoute,
    this.noticeMessage,
  });

  NotificationLoaded copyWith({
    List<InAppNotification>? notifications,
    int? unreadCount,
    PushDeviceRegistration? activeRegistration,
    bool clearActiveRegistration = false,
    bool? isPushConfigured,
    bool? isPermissionGranted,
    bool? hasApiGap,
    String? apiGapMessage,
    String? navigationRoute,
    bool clearNavigationRoute = false,
    String? noticeMessage,
    bool clearNotice = false,
  }) {
    return NotificationLoaded(
      notifications: notifications ?? this.notifications,
      unreadCount: unreadCount ?? this.unreadCount,
      activeRegistration: clearActiveRegistration
          ? null
          : (activeRegistration ?? this.activeRegistration),
      isPushConfigured: isPushConfigured ?? this.isPushConfigured,
      isPermissionGranted: isPermissionGranted ?? this.isPermissionGranted,
      hasApiGap: hasApiGap ?? this.hasApiGap,
      apiGapMessage: apiGapMessage ?? this.apiGapMessage,
      navigationRoute: clearNavigationRoute
          ? null
          : (navigationRoute ?? this.navigationRoute),
      noticeMessage: clearNotice ? null : (noticeMessage ?? this.noticeMessage),
    );
  }

  @override
  List<Object?> get props => [
        notifications,
        unreadCount,
        activeRegistration,
        isPushConfigured,
        isPermissionGranted,
        hasApiGap,
        apiGapMessage,
        navigationRoute,
        noticeMessage,
      ];
}

class NotificationError extends NotificationState {
  final String message;
  const NotificationError(this.message);

  @override
  List<Object?> get props => [message];
}
