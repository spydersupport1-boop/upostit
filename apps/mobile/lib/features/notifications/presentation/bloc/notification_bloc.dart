import 'dart:async';
import 'package:flutter_bloc/flutter_bloc.dart';
import '../../../../core/errors/failure.dart';
import '../../../devices/data/services/device_identity_service.dart';
import '../../data/services/push_notification_service.dart';
import '../../domain/entities/in_app_notification.dart';
import '../../domain/entities/push_notification_payload.dart';
import '../../domain/repositories/notification_repository.dart';
import 'notification_event.dart';
import 'notification_state.dart';

/// Central BLoC managing FCM device token lifecycle, push interactions,
/// and in-app notification center state.
class NotificationBloc extends Bloc<NotificationEvent, NotificationState> {
  final NotificationRepository _repository;
  final PushNotificationService _pushService;
  final DeviceIdentityService _deviceIdentityService;
  final bool Function()? _isUserAuthenticated;

  StreamSubscription<String>? _tokenRefreshSub;
  StreamSubscription<PushNotificationPayload>? _foregroundNotificationSub;
  StreamSubscription<PushNotificationPayload>? _notificationTappedSub;

  NotificationBloc({
    required NotificationRepository repository,
    required PushNotificationService pushService,
    required DeviceIdentityService deviceIdentityService,
    bool Function()? isUserAuthenticated,
  })  : _repository = repository,
        _pushService = pushService,
        _deviceIdentityService = deviceIdentityService,
        _isUserAuthenticated = isUserAuthenticated,
        super(const NotificationInitial()) {
    on<InitializePushNotifications>(_onInitializePushNotifications);
    on<TokenRefreshed>(_onTokenRefreshed);
    on<RevokeDeviceTokenRequested>(_onRevokeDeviceTokenRequested);
    on<FetchNotificationInboxRequested>(_onFetchNotificationInboxRequested);
    on<ForegroundNotificationReceived>(_onForegroundNotificationReceived);
    on<NotificationTappedEvent>(_onNotificationTappedEvent);
    on<MarkNotificationAsReadRequested>(_onMarkNotificationAsReadRequested);
    on<ClearNotificationSession>(_onClearNotificationSession);
    on<ClearNavigationRoute>(_onClearNavigationRoute);

    _listenToPushServiceStreams();
  }

  void _listenToPushServiceStreams() {
    _tokenRefreshSub = _pushService.onTokenRefresh.listen(
      (newToken) => add(TokenRefreshed(newToken)),
    );

    _foregroundNotificationSub = _pushService.onForegroundNotification.listen(
      (payload) => add(ForegroundNotificationReceived(payload)),
    );

    _notificationTappedSub = _pushService.onNotificationTapped.listen(
      (payload) {
        final notif = _mapPayloadToInAppNotification(payload);
        add(NotificationTappedEvent(notif));
      },
    );
  }

  Future<void> _onInitializePushNotifications(
    InitializePushNotifications event,
    Emitter<NotificationState> emit,
  ) async {
    final current = state is NotificationLoaded
        ? state as NotificationLoaded
        : const NotificationLoaded();

    emit(const NotificationLoading(
        message: 'Initializing push notifications...'));

    // 1. Initialize push service
    final isConfigured = await _pushService.initialize();
    if (!isConfigured) {
      emit(current.copyWith(
        isPushConfigured: false,
        noticeMessage:
            'Firebase push configuration not detected. Mock/local notification mode active.',
      ));
      add(const FetchNotificationInboxRequested());
      return;
    }

    // 2. Request permissions
    final permissionGranted =
        await _pushService.requestNotificationPermissions();
    if (!permissionGranted) {
      emit(current.copyWith(
        isPushConfigured: true,
        isPermissionGranted: false,
        noticeMessage:
            'Notification permissions were denied by user or system.',
      ));
      add(const FetchNotificationInboxRequested());
      return;
    }

    // 3. Register token if authenticated
    final isAuth = _isUserAuthenticated == null || _isUserAuthenticated();
    if (!isAuth) {
      emit(current.copyWith(
        isPushConfigured: true,
        isPermissionGranted: true,
      ));
      return;
    }

    final token = await _pushService.getDeviceToken();
    if (token != null && token.isNotEmpty) {
      final metadata = await _deviceIdentityService.getPlatformMetadata();
      final result = await _repository.registerDeviceToken(
        token: token,
        platform: metadata.platform,
        deviceModel: metadata.deviceModel,
        osVersion: metadata.osVersion,
        appVersion: metadata.appVersion,
        force: event.force,
      );

      if (result.isSuccess) {
        emit(current.copyWith(
          isPushConfigured: true,
          isPermissionGranted: true,
          activeRegistration: result.data,
        ));
      } else if (result.isFailure) {
        emit(current.copyWith(
          isPushConfigured: true,
          isPermissionGranted: true,
          noticeMessage:
              'Push token registration failed: ${result.failure?.message ?? "Unknown error"}',
        ));
      }
    }

    // 4. Check if app was cold-launched from a tapped notification
    final initialPayload = await _pushService.getInitialNotification();
    if (initialPayload != null) {
      final initialNotif = _mapPayloadToInAppNotification(initialPayload);
      _repository.addSessionNotification(initialNotif);
      if (initialNotif.deepLinkRoute != null) {
        emit(current.copyWith(navigationRoute: initialNotif.deepLinkRoute));
      }
    }

    // 5. Populate inbox
    add(const FetchNotificationInboxRequested());
  }

  Future<void> _onTokenRefreshed(
    TokenRefreshed event,
    Emitter<NotificationState> emit,
  ) async {
    final isAuth = _isUserAuthenticated == null || _isUserAuthenticated();
    if (!isAuth) return;

    final metadata = await _deviceIdentityService.getPlatformMetadata();
    final result = await _repository.registerDeviceToken(
      token: event.newToken,
      platform: metadata.platform,
      deviceModel: metadata.deviceModel,
      osVersion: metadata.osVersion,
      appVersion: metadata.appVersion,
      force: true, // Force registration on provider refresh
    );

    if (result.isSuccess && state is NotificationLoaded) {
      emit((state as NotificationLoaded).copyWith(
        activeRegistration: result.data,
      ));
    }
  }

  Future<void> _onRevokeDeviceTokenRequested(
    RevokeDeviceTokenRequested event,
    Emitter<NotificationState> emit,
  ) async {
    final current = state is NotificationLoaded
        ? state as NotificationLoaded
        : const NotificationLoaded();

    final token = await _pushService.getDeviceToken();
    if (token != null) {
      await _repository.revokeDeviceToken(token);
    }
    await _pushService.deleteToken();

    emit(current.copyWith(
      clearActiveRegistration: true,
      clearNotice: true,
    ));
  }

  Future<void> _onFetchNotificationInboxRequested(
    FetchNotificationInboxRequested event,
    Emitter<NotificationState> emit,
  ) async {
    final current = state is NotificationLoaded
        ? state as NotificationLoaded
        : const NotificationLoaded();

    if (!event.isRefresh) {
      emit(const NotificationLoading(message: 'Loading notifications...'));
    }

    final result = await _repository.getNotificationInbox();

    if (result.isSuccess) {
      final items = result.data ?? [];
      final unread = items.where((n) => !n.isRead).length;
      emit(current.copyWith(
        notifications: items,
        unreadCount: unread,
        hasApiGap: false,
        apiGapMessage: null,
        clearNotice: true,
      ));
    } else if (result.isFailure) {
      final failure = result.failure;
      if (failure is ApiGapFailure) {
        // Backend API gap: inbox endpoint does not yet exist.
        // Fall back to session-received push notifications and flag the API gap.
        final sessionItems = _repository.sessionNotifications;
        final unread = sessionItems.where((n) => !n.isRead).length;
        emit(current.copyWith(
          notifications: sessionItems,
          unreadCount: unread,
          hasApiGap: true,
          apiGapMessage: failure.message,
        ));
      } else {
        emit(current.copyWith(
          notifications: _repository.sessionNotifications,
          unreadCount:
              _repository.sessionNotifications.where((n) => !n.isRead).length,
          noticeMessage: failure?.message ?? 'Failed to load notifications',
        ));
      }
    }
  }

  void _onForegroundNotificationReceived(
    ForegroundNotificationReceived event,
    Emitter<NotificationState> emit,
  ) {
    final notif = _mapPayloadToInAppNotification(event.payload);
    _repository.addSessionNotification(notif);

    final current = state is NotificationLoaded
        ? state as NotificationLoaded
        : const NotificationLoaded();

    final updated = List<InAppNotification>.from(current.notifications);
    final existingIdx = updated.indexWhere((n) => n.id == notif.id);
    if (existingIdx >= 0) {
      updated[existingIdx] = notif;
    } else {
      updated.insert(0, notif);
    }

    final unread = updated.where((n) => !n.isRead).length;
    emit(current.copyWith(
      notifications: updated,
      unreadCount: unread,
    ));
  }

  Future<void> _onNotificationTappedEvent(
    NotificationTappedEvent event,
    Emitter<NotificationState> emit,
  ) async {
    final route = event.notification.deepLinkRoute;
    if (state is NotificationLoaded) {
      final current = state as NotificationLoaded;
      final updated = current.notifications.map((n) {
        if (n.id == event.notification.id) {
          return n.copyWith(isRead: true);
        }
        return n;
      }).toList();
      final unread = updated.where((n) => !n.isRead).length;
      emit(current.copyWith(
        notifications: updated,
        unreadCount: unread,
        navigationRoute: route != null && _isSafeRoute(route) ? route : null,
      ));
    }
    await _repository.markNotificationAsRead(event.notification.id);
  }

  Future<void> _onMarkNotificationAsReadRequested(
    MarkNotificationAsReadRequested event,
    Emitter<NotificationState> emit,
  ) async {
    final current =
        state is NotificationLoaded ? state as NotificationLoaded : null;
    if (current == null) return;

    // Optimistically update local list
    final updated = current.notifications.map((n) {
      if (n.id == event.notificationId) {
        return n.copyWith(isRead: true);
      }
      return n;
    }).toList();

    final unread = updated.where((n) => !n.isRead).length;
    emit(current.copyWith(
      notifications: updated,
      unreadCount: unread,
    ));

    // Delegate to repository
    await _repository.markNotificationAsRead(event.notificationId);
  }

  void _onClearNotificationSession(
    ClearNotificationSession event,
    Emitter<NotificationState> emit,
  ) {
    emit(const NotificationLoaded(
      notifications: [],
      unreadCount: 0,
      activeRegistration: null,
    ));
  }

  void _onClearNavigationRoute(
    ClearNavigationRoute event,
    Emitter<NotificationState> emit,
  ) {
    if (state is NotificationLoaded) {
      emit((state as NotificationLoaded).copyWith(clearNavigationRoute: true));
    }
  }

  InAppNotification _mapPayloadToInAppNotification(
      PushNotificationPayload payload) {
    return InAppNotification(
      id: payload.notificationId ??
          DateTime.now().millisecondsSinceEpoch.toString(),
      title: payload.title,
      body: payload.body,
      eventType: payload.eventType ?? 'push_notification',
      channel: 'PUSH',
      priority: payload.priority ?? 'NORMAL',
      createdAt: payload.receivedAt,
      isRead: false,
      payloadJson: payload.data,
    );
  }

  bool _isSafeRoute(String route) {
    // Whitelist approved internal application routes only; reject arbitrary external schemes or paths
    const safePrefixes = [
      '/home',
      '/leave',
      '/schedule',
      '/history',
      '/sync',
      '/profile'
    ];
    return safePrefixes
        .any((prefix) => route == prefix || route.startsWith('$prefix/'));
  }

  @override
  Future<void> close() {
    _tokenRefreshSub?.cancel();
    _foregroundNotificationSub?.cancel();
    _notificationTappedSub?.cancel();
    return super.close();
  }
}
