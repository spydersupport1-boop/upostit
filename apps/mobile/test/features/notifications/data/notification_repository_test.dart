import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:mobile/core/errors/app_exception.dart';
import 'package:mobile/core/errors/failure.dart';
import 'package:mobile/core/storage/secure_storage_service.dart';
import 'package:mobile/features/notifications/data/datasources/notification_remote_data_source.dart';
import 'package:mobile/features/notifications/data/models/device_token_register_request_model.dart';
import 'package:mobile/features/notifications/data/models/in_app_notification_model.dart';
import 'package:mobile/features/notifications/data/models/push_device_registration_model.dart';
import 'package:mobile/features/notifications/data/repositories/notification_repository_impl.dart';
import 'package:mobile/features/notifications/domain/entities/in_app_notification.dart';

class MockNotificationRemoteDataSource extends Mock
    implements NotificationRemoteDataSource {}

class MockSecureStorageService extends Mock implements SecureStorageService {}

void main() {
  late MockNotificationRemoteDataSource mockRemoteDataSource;
  late MockSecureStorageService mockSecureStorage;
  late NotificationRepositoryImpl repository;

  setUpAll(() {
    registerFallbackValue(const DeviceTokenRegisterRequestModel(
      platform: 'ANDROID',
      token: 'fallback_token',
    ));
  });

  setUp(() {
    mockRemoteDataSource = MockNotificationRemoteDataSource();
    mockSecureStorage = MockSecureStorageService();
    repository = NotificationRepositoryImpl(
      remoteDataSource: mockRemoteDataSource,
      secureStorage: mockSecureStorage,
    );
  });

  group('NotificationRepository - registerDeviceToken & deduplication', () {
    const rawToken = 'fcm_token_pixel_8_abc_1234567890';
    final mockRegistration = PushDeviceRegistrationModel(
      id: 'reg-1',
      tenantId: 'tenant-1',
      userId: 'user-1',
      platform: 'ANDROID',
      tokenPreview: 'device_token_hash:abc12345...',
      deviceModel: 'Pixel 8',
      osVersion: 'Android 14',
      appVersion: '1.0.0',
      status: 'ACTIVE',
      lastSeenAt: DateTime(2026, 11, 22),
      createdAt: DateTime(2026, 11, 22),
    );

    test('registers token on remote and saves token and hash in secure storage',
        () async {
      when(() => mockSecureStorage.getLastRegisteredPushToken())
          .thenAnswer((_) async => null);
      when(() => mockRemoteDataSource.registerDeviceToken(any()))
          .thenAnswer((_) async => mockRegistration);
      when(() => mockSecureStorage.saveLastRegisteredPushToken(rawToken))
          .thenAnswer((_) async {});
      when(() => mockSecureStorage.saveLastRegisteredTokenHash(
          mockRegistration.tokenPreview)).thenAnswer((_) async {});

      final result = await repository.registerDeviceToken(
        token: rawToken,
        platform: 'ANDROID',
        deviceModel: 'Pixel 8',
      );

      expect(result.isSuccess, true);
      expect(result.data!.id, 'reg-1');
      expect(result.data!.tokenPreview, 'device_token_hash:abc12345...');

      verify(() => mockRemoteDataSource.registerDeviceToken(any())).called(1);
      verify(() => mockSecureStorage.saveLastRegisteredPushToken(rawToken))
          .called(1);
      verify(() => mockSecureStorage.saveLastRegisteredTokenHash(
          mockRegistration.tokenPreview)).called(1);
    });

    test('deduplicates: returns cached registration when token is unchanged',
        () async {
      when(() => mockSecureStorage.getLastRegisteredPushToken())
          .thenAnswer((_) async => rawToken);
      when(() => mockSecureStorage.getLastRegisteredTokenHash())
          .thenAnswer((_) async => 'device_token_hash:abc12345...');

      final result = await repository.registerDeviceToken(
        token: rawToken,
        platform: 'ANDROID',
        force: false,
      );

      expect(result.isSuccess, true);
      expect(result.data!.status, 'ACTIVE');
      // Remote call must NOT have been made
      verifyNever(() => mockRemoteDataSource.registerDeviceToken(any()));
    });

    test('force re-registers with remote even if token matches cache',
        () async {
      when(() => mockSecureStorage.getLastRegisteredPushToken())
          .thenAnswer((_) async => rawToken);
      when(() => mockRemoteDataSource.registerDeviceToken(any()))
          .thenAnswer((_) async => mockRegistration);
      when(() => mockSecureStorage.saveLastRegisteredPushToken(rawToken))
          .thenAnswer((_) async {});
      when(() => mockSecureStorage.saveLastRegisteredTokenHash(
          mockRegistration.tokenPreview)).thenAnswer((_) async {});

      final result = await repository.registerDeviceToken(
        token: rawToken,
        platform: 'ANDROID',
        force: true,
      );

      expect(result.isSuccess, true);
      verify(() => mockRemoteDataSource.registerDeviceToken(any())).called(1);
    });
  });

  group('NotificationRepository - token revocation', () {
    test('revokeDeviceToken calls remote and purges secure storage keys',
        () async {
      when(() => mockRemoteDataSource.revokeDeviceToken('raw_token_xyz'))
          .thenAnswer((_) async {});
      when(() => mockSecureStorage.deleteLastRegisteredPushToken())
          .thenAnswer((_) async {});
      when(() => mockSecureStorage.deleteLastRegisteredTokenHash())
          .thenAnswer((_) async {});

      final result = await repository.revokeDeviceToken('raw_token_xyz');

      expect(result.isSuccess, true);
      verify(() => mockRemoteDataSource.revokeDeviceToken('raw_token_xyz'))
          .called(1);
      verify(() => mockSecureStorage.deleteLastRegisteredPushToken()).called(1);
      verify(() => mockSecureStorage.deleteLastRegisteredTokenHash()).called(1);
    });

    test('revokeDeviceTokenByHash calls remote and purges secure storage keys',
        () async {
      when(() => mockRemoteDataSource.revokeDeviceTokenByHash('hash_123'))
          .thenAnswer((_) async {});
      when(() => mockSecureStorage.deleteLastRegisteredPushToken())
          .thenAnswer((_) async {});
      when(() => mockSecureStorage.deleteLastRegisteredTokenHash())
          .thenAnswer((_) async {});

      final result = await repository.revokeDeviceTokenByHash('hash_123');

      expect(result.isSuccess, true);
      verify(() => mockRemoteDataSource.revokeDeviceTokenByHash('hash_123'))
          .called(1);
      verify(() => mockSecureStorage.deleteLastRegisteredPushToken()).called(1);
      verify(() => mockSecureStorage.deleteLastRegisteredTokenHash()).called(1);
    });
  });

  group('NotificationRepository - inbox & API Gap handling', () {
    test('returns remote notifications merged with local session notifications',
        () async {
      // Add a session notification
      repository.addSessionNotification(InAppNotification(
        id: 'session-notif-1',
        title: 'Session Alert',
        body: 'Alert received while app in foreground',
        eventType: 'leave_request_approved',
        createdAt: DateTime(2026, 11, 22, 10, 0),
      ));

      final remoteNotifications = [
        InAppNotificationModel(
          id: 'remote-notif-2',
          title: 'Remote Alert',
          body: 'Fetched from server',
          eventType: 'leave_request_submitted',
          createdAt: DateTime(2026, 11, 22, 9, 0),
        ),
      ];

      when(() => mockRemoteDataSource.getNotificationInbox())
          .thenAnswer((_) async => remoteNotifications);

      final result = await repository.getNotificationInbox();

      expect(result.isSuccess, true);
      final items = result.data!;
      expect(items.length, 2);
      expect(items.any((n) => n.id == 'session-notif-1'), true);
      expect(items.any((n) => n.id == 'remote-notif-2'), true);
    });

    test('translates ApiGapException into ApiGapFailure without throwing',
        () async {
      when(() => mockRemoteDataSource.getNotificationInbox())
          .thenThrow(const ApiGapException('Endpoint 404', 404));

      final result = await repository.getNotificationInbox();

      expect(result.isFailure, true);
      expect(result.failure, isA<ApiGapFailure>());
    });

    test('markNotificationAsRead updates session notification even if API gap',
        () async {
      repository.addSessionNotification(InAppNotification(
        id: 'session-1',
        title: 'Unread Alert',
        body: 'Body',
        eventType: 'test',
        createdAt: DateTime.now(),
        isRead: false,
      ));

      when(() => mockRemoteDataSource.markNotificationAsRead('session-1'))
          .thenThrow(const ApiGapException('Mark as read not supported', 404));

      final result = await repository.markNotificationAsRead('session-1');

      // Returns ApiGapFailure as documented
      expect(result.isFailure, true);
      expect(result.failure, isA<ApiGapFailure>());

      // But locally marked as read in session
      expect(repository.sessionNotifications.first.isRead, true);
    });
  });

  group('NotificationRepository - sensitive data redaction', () {
    test(
        'redacts passwords, tokens, and fraud risk scores from body and payload',
        () {
      final sensitiveNotification = InAppNotification(
        id: 'sens-1',
        title: 'Account Alert',
        body:
            'Your temporary password: SecretPassword123! token=abc_raw_token_xyz',
        eventType: 'high_risk_fraud_alert',
        createdAt: DateTime(2026, 11, 22),
        payloadJson: const {
          'safe_field': 'hello',
          'password': 'PlainTextPassword',
          'token': 'RawTokenString',
          'invitation_token': 'Invite123',
          'risk_score': 95,
          'gps_spoof_score': 88,
        },
      );

      repository.addSessionNotification(sensitiveNotification);

      final stored = repository.sessionNotifications.first;

      // Body secrets redacted
      expect(stored.body.contains('SecretPassword123!'), false);
      expect(stored.body.contains('abc_raw_token_xyz'), false);
      expect(stored.body.contains('[REDACTED]'), true);

      // Payload dictionary purged
      expect(stored.payloadJson!.containsKey('safe_field'), true);
      expect(stored.payloadJson!.containsKey('password'), false);
      expect(stored.payloadJson!.containsKey('token'), false);
      expect(stored.payloadJson!.containsKey('invitation_token'), false);
      expect(stored.payloadJson!.containsKey('risk_score'), false);
      expect(stored.payloadJson!.containsKey('gps_spoof_score'), false);
    });
  });
}
