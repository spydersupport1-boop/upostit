import 'dart:async';
import 'package:flutter/foundation.dart';
import '../../../../core/errors/app_exception.dart';
import '../../../../core/errors/failure.dart';
import '../../../../core/errors/result.dart';
import '../../../../core/storage/secure_storage_service.dart';
import '../../domain/entities/in_app_notification.dart';
import '../../domain/entities/push_device_registration.dart';
import '../../domain/repositories/notification_repository.dart';
import '../datasources/notification_remote_data_source.dart';
import '../models/device_token_register_request_model.dart';

/// Implementation of [NotificationRepository] with session caching and deduplication.
class NotificationRepositoryImpl implements NotificationRepository {
  final NotificationRemoteDataSource _remoteDataSource;
  final SecureStorageService _secureStorage;
  final List<InAppNotification> _sessionNotifications = [];
  final StreamController<InAppNotification> _notificationStreamController =
      StreamController<InAppNotification>.broadcast();

  NotificationRepositoryImpl({
    required NotificationRemoteDataSource remoteDataSource,
    required SecureStorageService secureStorage,
  })  : _remoteDataSource = remoteDataSource,
        _secureStorage = secureStorage;

  @override
  Stream<InAppNotification> get onNotificationReceived =>
      _notificationStreamController.stream;

  @override
  List<InAppNotification> get sessionNotifications =>
      List.unmodifiable(_sessionNotifications);

  @override
  void addSessionNotification(InAppNotification notification) {
    // Redact sensitive payload information before storing in session
    final sanitized = _sanitizeNotification(notification);
    // Deduplicate by ID
    final existingIndex =
        _sessionNotifications.indexWhere((n) => n.id == sanitized.id);
    if (existingIndex >= 0) {
      _sessionNotifications[existingIndex] = sanitized;
    } else {
      _sessionNotifications.insert(0, sanitized);
    }
    _notificationStreamController.add(sanitized);
  }

  @override
  Future<Result<PushDeviceRegistration>> registerDeviceToken({
    required String token,
    required String platform,
    String? deviceModel,
    String? osVersion,
    String? appVersion,
    bool force = false,
  }) async {
    try {
      // 1. Deduplication check: Avoid re-registering if token hasn't changed
      if (!force) {
        final lastToken = await _secureStorage.getLastRegisteredPushToken();
        if (lastToken != null && lastToken == token) {
          debugPrint(
              'FCM Token unchanged since last registration; skipping redundant POST');
          final lastHash = await _secureStorage.getLastRegisteredTokenHash();
          return Result.success(
            PushDeviceRegistration(
              id: 'cached',
              tenantId: 'current',
              userId: 'current',
              platform: platform,
              tokenPreview: lastHash != null && lastHash.length >= 8
                  ? 'cached:${lastHash.substring(0, 8)}...'
                  : 'cached:active',
              deviceModel: deviceModel,
              osVersion: osVersion,
              appVersion: appVersion,
              status: 'ACTIVE',
              lastSeenAt: DateTime.now(),
              createdAt: DateTime.now(),
            ),
          );
        }
      }

      // 2. Remote registration
      final request = DeviceTokenRegisterRequestModel(
        platform: platform,
        token: token,
        deviceModel: deviceModel,
        osVersion: osVersion,
        appVersion: appVersion,
      );
      final model = await _remoteDataSource.registerDeviceToken(request);

      // 3. Persist successful registration securely
      await _secureStorage.saveLastRegisteredPushToken(token);
      await _secureStorage.saveLastRegisteredTokenHash(model.tokenPreview);

      return Result.success(model);
    } on NetworkException catch (e) {
      return Result.failure(NetworkFailure(e.message));
    } on AuthException catch (e) {
      return Result.failure(AuthFailure(e.message,
          statusCode: e.statusCode,
          isSessionExpired: e.isSessionExpired,
          isReuseDetected: e.isReuseDetected));
    } on ServerException catch (e) {
      return Result.failure(ServerFailure(e.message, statusCode: e.statusCode));
    } catch (e) {
      return Result.failure(ServerFailure(e.toString()));
    }
  }

  @override
  Future<Result<List<PushDeviceRegistration>>> listActiveDeviceTokens() async {
    try {
      final models = await _remoteDataSource.listActiveDeviceTokens();
      return Result.success(models);
    } on NetworkException catch (e) {
      return Result.failure(NetworkFailure(e.message));
    } on AuthException catch (e) {
      return Result.failure(AuthFailure(e.message, statusCode: e.statusCode));
    } on ServerException catch (e) {
      return Result.failure(ServerFailure(e.message, statusCode: e.statusCode));
    } catch (e) {
      return Result.failure(ServerFailure(e.toString()));
    }
  }

  @override
  Future<Result<void>> revokeDeviceToken(String token) async {
    try {
      await _remoteDataSource.revokeDeviceToken(token);
      await _secureStorage.deleteLastRegisteredPushToken();
      await _secureStorage.deleteLastRegisteredTokenHash();
      return const Result.success(null);
    } on NetworkException catch (e) {
      return Result.failure(NetworkFailure(e.message));
    } on AuthException catch (e) {
      return Result.failure(AuthFailure(e.message, statusCode: e.statusCode));
    } on ServerException catch (e) {
      return Result.failure(ServerFailure(e.message, statusCode: e.statusCode));
    } catch (e) {
      return Result.failure(ServerFailure(e.toString()));
    }
  }

  @override
  Future<Result<void>> revokeDeviceTokenByHash(String tokenHash) async {
    try {
      await _remoteDataSource.revokeDeviceTokenByHash(tokenHash);
      await _secureStorage.deleteLastRegisteredPushToken();
      await _secureStorage.deleteLastRegisteredTokenHash();
      return const Result.success(null);
    } on NetworkException catch (e) {
      return Result.failure(NetworkFailure(e.message));
    } on AuthException catch (e) {
      return Result.failure(AuthFailure(e.message, statusCode: e.statusCode));
    } on ServerException catch (e) {
      return Result.failure(ServerFailure(e.message, statusCode: e.statusCode));
    } catch (e) {
      return Result.failure(ServerFailure(e.toString()));
    }
  }

  @override
  Future<Result<List<InAppNotification>>> getNotificationInbox() async {
    try {
      final remoteList = await _remoteDataSource.getNotificationInbox();
      final sanitizedList =
          remoteList.map((n) => _sanitizeNotification(n)).toList();

      // Merge with in-memory session notifications
      for (final sessionItem in _sessionNotifications) {
        if (!sanitizedList.any((r) => r.id == sessionItem.id)) {
          sanitizedList.insert(0, sessionItem);
        }
      }
      return Result.success(sanitizedList);
    } on ApiGapException catch (e) {
      // Backend does not currently support user inbox listing
      debugPrint('Backend API Gap: ${e.message}');
      return Result.failure(ApiGapFailure(e.message, e.statusCode));
    } on NetworkException catch (e) {
      return Result.failure(NetworkFailure(e.message));
    } on AuthException catch (e) {
      return Result.failure(AuthFailure(e.message, statusCode: e.statusCode));
    } on ServerException catch (e) {
      return Result.failure(ServerFailure(e.message, statusCode: e.statusCode));
    } catch (e) {
      return Result.failure(ServerFailure(e.toString()));
    }
  }

  @override
  Future<Result<void>> markNotificationAsRead(String notificationId) async {
    try {
      await _remoteDataSource.markNotificationAsRead(notificationId);
      // Mark locally if remote succeeds
      _markLocallyAsRead(notificationId);
      return const Result.success(null);
    } on ApiGapException catch (e) {
      // Server does not support mark-as-read API.
      // Per instructions: document API gap instead of pretending operation succeeded.
      debugPrint('Backend API Gap: ${e.message}');
      _markLocallyAsRead(notificationId);
      return Result.failure(ApiGapFailure(
          'Mark-as-read is not supported by the backend API. Updated locally for current session only.',
          e.statusCode));
    } on NetworkException catch (e) {
      return Result.failure(NetworkFailure(e.message));
    } on AuthException catch (e) {
      return Result.failure(AuthFailure(e.message, statusCode: e.statusCode));
    } on ServerException catch (e) {
      return Result.failure(ServerFailure(e.message, statusCode: e.statusCode));
    } catch (e) {
      return Result.failure(ServerFailure(e.toString()));
    }
  }

  void _markLocallyAsRead(String notificationId) {
    final index =
        _sessionNotifications.indexWhere((n) => n.id == notificationId);
    if (index >= 0) {
      _sessionNotifications[index] =
          _sessionNotifications[index].copyWith(isRead: true);
    }
  }

  /// Strips potential secrets, passwords, invitation tokens, or raw fraud telemetry
  InAppNotification _sanitizeNotification(InAppNotification notification) {
    var body = notification.body;
    // Redact password or token strings if accidentally included
    body = body.replaceAll(
        RegExp(r'(password|token|secret)[:=]\s*\S+', caseSensitive: false),
        r'$1: [REDACTED]');

    Map<String, dynamic>? sanitizedPayload;
    if (notification.payloadJson != null) {
      sanitizedPayload = Map<String, dynamic>.from(notification.payloadJson!);
      sanitizedPayload.remove('password');
      sanitizedPayload.remove('token');
      sanitizedPayload.remove('invitation_token');
      sanitizedPayload.remove('raw_token');
      sanitizedPayload.remove('risk_score');
      sanitizedPayload.remove('gps_spoof_score');
    }

    return notification.copyWith(
      body: body,
      payloadJson: sanitizedPayload,
    );
  }

  void dispose() {
    _notificationStreamController.close();
  }
}
