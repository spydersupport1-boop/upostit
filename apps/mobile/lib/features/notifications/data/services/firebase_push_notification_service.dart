import 'dart:async';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import '../../domain/entities/push_notification_payload.dart';
import 'push_notification_service.dart';

/// Top-level background message handler required by Firebase Messaging.
@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  // Background notification received. Note: No heavy UI work or raw token logging here.
  debugPrint(
      'Received background push notification (messageId: ${message.messageId})');
}

/// Production implementation of [PushNotificationService] using Firebase Cloud Messaging.
class FirebasePushNotificationService implements PushNotificationService {
  final FirebaseMessaging _messaging;
  final StreamController<String> _tokenRefreshController =
      StreamController<String>.broadcast();
  final StreamController<PushNotificationPayload> _foregroundController =
      StreamController<PushNotificationPayload>.broadcast();
  final StreamController<PushNotificationPayload> _tappedController =
      StreamController<PushNotificationPayload>.broadcast();

  bool _isInitialized = false;
  bool _isConfigured = false;
  StreamSubscription<String>? _tokenRefreshSub;
  StreamSubscription<RemoteMessage>? _onMessageSub;
  StreamSubscription<RemoteMessage>? _onMessageOpenedAppSub;

  FirebasePushNotificationService({FirebaseMessaging? messaging})
      : _messaging = messaging ?? FirebaseMessaging.instance;

  @override
  bool get isConfigured => _isConfigured;

  @override
  Future<bool> initialize() async {
    if (_isInitialized) return _isConfigured;

    try {
      // Verify Firebase default app is initialized
      try {
        if (Firebase.apps.isEmpty) {
          await Firebase.initializeApp();
        }
        _isConfigured = true;
      } catch (e) {
        // Firebase configuration missing (e.g. google-services.json not configured in dev)
        debugPrint('Firebase not configured on device: $e');
        _isConfigured = false;
        _isInitialized = true;
        return false;
      }

      // Configure background handler
      FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);

      // Listen to token refresh
      // ignore: deprecated_member_use
      _tokenRefreshSub = _messaging.onTokenRefresh.listen(
        (newToken) {
          debugPrint('FCM Token refreshed by provider');
          _tokenRefreshController.add(newToken);
        },
        onError: (err) {
          debugPrint('Error on token refresh stream: $err');
        },
      );

      // Listen to foreground notifications
      _onMessageSub = FirebaseMessaging.onMessage.listen(
        (RemoteMessage message) {
          final payload = _mapRemoteMessageToPayload(message);
          _foregroundController.add(payload);
        },
        onError: (err) {
          debugPrint('Error on foreground message stream: $err');
        },
      );

      // Listen to notification taps when app is in background
      _onMessageOpenedAppSub = FirebaseMessaging.onMessageOpenedApp.listen(
        (RemoteMessage message) {
          final payload = _mapRemoteMessageToPayload(message);
          _tappedController.add(payload);
        },
        onError: (err) {
          debugPrint('Error on message opened app stream: $err');
        },
      );

      _isInitialized = true;
      return true;
    } catch (e) {
      debugPrint('Failed to initialize Firebase Messaging: $e');
      _isConfigured = false;
      _isInitialized = true;
      return false;
    }
  }

  @override
  Future<bool> requestNotificationPermissions() async {
    if (!_isConfigured) return false;

    try {
      final settings = await _messaging.requestPermission(
        alert: true,
        announcement: false,
        badge: true,
        carPlay: false,
        criticalAlert: false,
        provisional: false,
        sound: true,
      );

      final isGranted =
          settings.authorizationStatus == AuthorizationStatus.authorized ||
              settings.authorizationStatus == AuthorizationStatus.provisional;
      return isGranted;
    } catch (e) {
      debugPrint('Error requesting notification permissions: $e');
      return false;
    }
  }

  @override
  Future<String?> getDeviceToken() async {
    if (!_isConfigured) return null;

    try {
      // ignore: deprecated_member_use
      final token = await _messaging.getToken();
      return token;
    } catch (e) {
      debugPrint('Failed to obtain FCM device registration token: $e');
      return null;
    }
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
    if (!_isConfigured) return null;

    try {
      final initialMessage = await _messaging.getInitialMessage();
      if (initialMessage != null) {
        return _mapRemoteMessageToPayload(initialMessage);
      }
      return null;
    } catch (e) {
      debugPrint('Error getting initial notification: $e');
      return null;
    }
  }

  @override
  Future<void> deleteToken() async {
    if (!_isConfigured) return;
    try {
      // ignore: deprecated_member_use
      await _messaging.deleteToken();
    } catch (e) {
      debugPrint('Error deleting local FCM token: $e');
    }
  }

  PushNotificationPayload _mapRemoteMessageToPayload(RemoteMessage message) {
    final notification = message.notification;
    final data = message.data;

    final title = notification?.title ??
        data['title']?.toString() ??
        data['subject']?.toString() ??
        'Notification';

    final body = notification?.body ??
        data['body']?.toString() ??
        data['message']?.toString() ??
        '';

    final eventType = data['event_type']?.toString();
    final priority = data['priority']?.toString();
    final notificationId =
        data['notification_id']?.toString() ?? message.messageId;

    return PushNotificationPayload(
      notificationId: notificationId,
      title: title,
      body: body,
      eventType: eventType,
      priority: priority,
      data: data,
      receivedAt: DateTime.now(),
    );
  }

  void dispose() {
    _tokenRefreshSub?.cancel();
    _onMessageSub?.cancel();
    _onMessageOpenedAppSub?.cancel();
    _tokenRefreshController.close();
    _foregroundController.close();
    _tappedController.close();
  }
}
