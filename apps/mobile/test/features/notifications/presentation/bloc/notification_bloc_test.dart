import 'package:bloc_test/bloc_test.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:mobile/core/errors/failure.dart';
import 'package:mobile/core/errors/result.dart';
import 'package:mobile/features/devices/data/services/device_identity_service.dart';
import 'package:mobile/features/notifications/data/services/mock_push_notification_service.dart';
import 'package:mobile/features/notifications/domain/entities/in_app_notification.dart';
import 'package:mobile/features/notifications/domain/entities/push_device_registration.dart';
import 'package:mobile/features/notifications/domain/entities/push_notification_payload.dart';
import 'package:mobile/features/notifications/domain/repositories/notification_repository.dart';
import 'package:mobile/features/notifications/presentation/bloc/notification_bloc.dart';
import 'package:mobile/features/notifications/presentation/bloc/notification_event.dart';
import 'package:mobile/features/notifications/presentation/bloc/notification_state.dart';

class MockNotificationRepository extends Mock
    implements NotificationRepository {}

class MockDeviceIdentityService extends Mock implements DeviceIdentityService {}

class FakeInAppNotification extends Fake implements InAppNotification {}

void main() {
  setUpAll(() {
    registerFallbackValue(FakeInAppNotification());
  });

  late MockNotificationRepository mockRepository;
  late MockPushNotificationService mockPushService;
  late MockDeviceIdentityService mockDeviceIdentityService;
  late NotificationBloc bloc;

  final testRegistration = PushDeviceRegistration(
    id: 'reg-1',
    tenantId: 'tenant-1',
    userId: 'user-1',
    platform: 'ANDROID',
    tokenPreview: 'device_token_hash:123...',
    deviceModel: 'Pixel 8',
    osVersion: 'Android 14',
    appVersion: '1.0.0',
    status: 'ACTIVE',
    lastSeenAt: DateTime(2026, 11, 22),
    createdAt: DateTime(2026, 11, 22),
  );

  const testMetadata = DevicePlatformInfo(
    platform: 'ANDROID',
    deviceModel: 'Pixel 8',
    osVersion: 'Android 14',
    appVersion: '1.0.0',
  );

  final testNotification = InAppNotification(
    id: 'notif-1',
    title: 'Leave Request Approved',
    body: 'Your annual leave request has been approved by your supervisor.',
    eventType: 'leave_request_approved',
    channel: 'PUSH',
    priority: 'NORMAL',
    createdAt: DateTime(2026, 11, 22, 10, 0),
    isRead: false,
  );

  setUp(() {
    mockRepository = MockNotificationRepository();
    mockPushService = MockPushNotificationService();
    mockDeviceIdentityService = MockDeviceIdentityService();

    when(() => mockDeviceIdentityService.getPlatformMetadata())
        .thenAnswer((_) async => testMetadata);
    when(() => mockRepository.sessionNotifications).thenReturn([]);

    bloc = NotificationBloc(
      repository: mockRepository,
      pushService: mockPushService,
      deviceIdentityService: mockDeviceIdentityService,
      isUserAuthenticated: () => true,
    );
  });

  tearDown(() {
    bloc.close();
    mockPushService.dispose();
  });

  test('initial state is NotificationInitial', () {
    expect(bloc.state, const NotificationInitial());
  });

  group('NotificationBloc - InitializePushNotifications', () {
    blocTest<NotificationBloc, NotificationState>(
      'registers token and fetches inbox when initialized with permissions',
      build: () {
        when(() => mockRepository.registerDeviceToken(
              token: any(named: 'token'),
              platform: any(named: 'platform'),
              deviceModel: any(named: 'deviceModel'),
              osVersion: any(named: 'osVersion'),
              appVersion: any(named: 'appVersion'),
              force: any(named: 'force'),
            )).thenAnswer((_) async => Result.success(testRegistration));
        when(() => mockRepository.getNotificationInbox())
            .thenAnswer((_) async => Result.success([testNotification]));
        return bloc;
      },
      act: (b) => b.add(const InitializePushNotifications()),
      expect: () => [
        const NotificationLoading(
            message: 'Initializing push notifications...'),
        NotificationLoaded(
          isPushConfigured: true,
          isPermissionGranted: true,
          activeRegistration: testRegistration,
        ),
        const NotificationLoading(message: 'Loading notifications...'),
        NotificationLoaded(
          isPushConfigured: true,
          isPermissionGranted: true,
          activeRegistration: testRegistration,
          notifications: [testNotification],
          unreadCount: 1,
          hasApiGap: false,
        ),
      ],
    );

    blocTest<NotificationBloc, NotificationState>(
      'emits isPushConfigured: false when push service fails initialization',
      build: () {
        mockPushService.shouldFailInitialization = true;
        when(() => mockRepository.getNotificationInbox())
            .thenAnswer((_) async => const Result.success([]));
        return bloc;
      },
      act: (b) => b.add(const InitializePushNotifications()),
      expect: () => [
        const NotificationLoading(
            message: 'Initializing push notifications...'),
        const NotificationLoaded(
          isPushConfigured: false,
          isPermissionGranted: false,
          noticeMessage:
              'Firebase push configuration not detected. Mock/local notification mode active.',
        ),
        const NotificationLoading(message: 'Loading notifications...'),
        const NotificationLoaded(
          isPushConfigured: false,
          isPermissionGranted: false,
          notifications: [],
          unreadCount: 0,
          hasApiGap: false,
        ),
      ],
    );

    blocTest<NotificationBloc, NotificationState>(
      'emits isPermissionGranted: false when user denies permission',
      build: () {
        mockPushService.isPermissionGranted = false;
        when(() => mockRepository.getNotificationInbox())
            .thenAnswer((_) async => const Result.success([]));
        return bloc;
      },
      act: (b) => b.add(const InitializePushNotifications()),
      expect: () => [
        const NotificationLoading(
            message: 'Initializing push notifications...'),
        const NotificationLoaded(
          isPushConfigured: true,
          isPermissionGranted: false,
          noticeMessage:
              'Notification permissions were denied by user or system.',
        ),
        const NotificationLoading(message: 'Loading notifications...'),
        const NotificationLoaded(
          isPushConfigured: true,
          isPermissionGranted: false,
          notifications: [],
          unreadCount: 0,
          hasApiGap: false,
        ),
      ],
    );

    blocTest<NotificationBloc, NotificationState>(
      'does not register token with backend when user is logged out',
      build: () {
        final loggedOutBloc = NotificationBloc(
          repository: mockRepository,
          pushService: mockPushService,
          deviceIdentityService: mockDeviceIdentityService,
          isUserAuthenticated: () => false,
        );
        return loggedOutBloc;
      },
      act: (b) => b.add(const InitializePushNotifications()),
      expect: () => [
        const NotificationLoading(
            message: 'Initializing push notifications...'),
        const NotificationLoaded(
          isPushConfigured: true,
          isPermissionGranted: true,
        ),
      ],
      verify: (_) {
        verifyNever(() => mockRepository.registerDeviceToken(
              token: any(named: 'token'),
              platform: any(named: 'platform'),
            ));
      },
    );
  });

  group('NotificationBloc - Token Refresh', () {
    blocTest<NotificationBloc, NotificationState>(
      're-registers new token with force: true on provider token refresh',
      build: () {
        when(() => mockRepository.registerDeviceToken(
              token: 'new_refreshed_token_xyz',
              platform: any(named: 'platform'),
              deviceModel: any(named: 'deviceModel'),
              osVersion: any(named: 'osVersion'),
              appVersion: any(named: 'appVersion'),
              force: true,
            )).thenAnswer((_) async => Result.success(testRegistration));
        return bloc;
      },
      seed: () => NotificationLoaded(activeRegistration: testRegistration),
      act: (b) => b.add(const TokenRefreshed('new_refreshed_token_xyz')),
      verify: (_) {
        verify(() => mockRepository.registerDeviceToken(
              token: 'new_refreshed_token_xyz',
              platform: 'ANDROID',
              deviceModel: 'Pixel 8',
              osVersion: 'Android 14',
              appVersion: '1.0.0',
              force: true,
            )).called(1);
      },
    );
  });

  group('NotificationBloc - Logout & Token Revocation', () {
    blocTest<NotificationBloc, NotificationState>(
      'revokes device token and deletes local token on logout',
      build: () {
        when(() => mockRepository.revokeDeviceToken(any()))
            .thenAnswer((_) async => const Result.success(null));
        return bloc;
      },
      seed: () => NotificationLoaded(activeRegistration: testRegistration),
      act: (b) => b.add(const RevokeDeviceTokenRequested()),
      expect: () => [
        const NotificationLoaded(activeRegistration: null),
      ],
      verify: (_) {
        expect(mockPushService.deleteTokenCallCount, 1);
        verify(() => mockRepository.revokeDeviceToken(any())).called(1);
      },
    );

    blocTest<NotificationBloc, NotificationState>(
      'clears notifications list on ClearNotificationSession',
      build: () => bloc,
      seed: () => NotificationLoaded(
        notifications: [testNotification],
        unreadCount: 1,
        activeRegistration: testRegistration,
      ),
      act: (b) => b.add(const ClearNotificationSession()),
      expect: () => [
        const NotificationLoaded(
          notifications: [],
          unreadCount: 0,
          activeRegistration: null,
        ),
      ],
    );
  });

  group('NotificationBloc - Push Interactions & Taps', () {
    blocTest<NotificationBloc, NotificationState>(
      'adds foreground notification to list and increments unread count',
      build: () {
        when(() => mockRepository.addSessionNotification(any()))
            .thenAnswer((_) {});
        return bloc;
      },
      seed: () => const NotificationLoaded(notifications: [], unreadCount: 0),
      act: (b) {
        mockPushService.simulateForegroundMessage(PushNotificationPayload(
          notificationId: 'notif-fg-1',
          title: 'Shift Reminder',
          body: 'Your shift starts in 15 minutes',
          eventType: 'shift_reminder',
          receivedAt: DateTime(2026, 11, 22),
        ));
      },
      verify: (_) {
        verify(() => mockRepository.addSessionNotification(any())).called(1);
      },
    );

    blocTest<NotificationBloc, NotificationState>(
      'navigates to safe deep link when notification is tapped',
      build: () {
        when(() => mockRepository.markNotificationAsRead('notif-1'))
            .thenAnswer((_) async => const Result.success(null));
        return bloc;
      },
      seed: () => NotificationLoaded(
        notifications: [testNotification],
        unreadCount: 1,
      ),
      act: (b) => b.add(NotificationTappedEvent(testNotification)),
      expect: () => [
        NotificationLoaded(
          notifications: [testNotification.copyWith(isRead: true)],
          unreadCount: 0,
          navigationRoute: '/leave',
        ),
      ],
    );

    blocTest<NotificationBloc, NotificationState>(
      'rejects arbitrary external URLs or untrusted deep links',
      build: () {
        when(() => mockRepository.markNotificationAsRead('evil-1'))
            .thenAnswer((_) async => const Result.success(null));
        return bloc;
      },
      seed: () => NotificationLoaded(
        notifications: [
          InAppNotification(
            id: 'evil-1',
            title: 'Malicious',
            body: 'Body',
            eventType: 'unknown',
            createdAt: DateTime.now(),
            relatedEntityType: 'https://evil.com',
          ),
        ],
        unreadCount: 1,
      ),
      act: (b) {
        final evilNotification = InAppNotification(
          id: 'evil-1',
          title: 'Malicious',
          body: 'Body',
          eventType: 'unknown',
          createdAt: DateTime.now(),
        );
        b.add(NotificationTappedEvent(evilNotification));
      },
      verify: (b) {
        final state = b.state as NotificationLoaded;
        expect(state.navigationRoute, null);
      },
    );
  });

  group('NotificationBloc - API Gap handling in Inbox', () {
    blocTest<NotificationBloc, NotificationState>(
      'sets hasApiGap: true and falls back to session notifications when 404',
      build: () {
        when(() => mockRepository.getNotificationInbox()).thenAnswer(
            (_) async => const Result.failure(ApiGapFailure('API Gap 404')));
        when(() => mockRepository.sessionNotifications)
            .thenReturn([testNotification]);
        return bloc;
      },
      act: (b) => b.add(const FetchNotificationInboxRequested()),
      expect: () => [
        const NotificationLoading(message: 'Loading notifications...'),
        NotificationLoaded(
          notifications: [testNotification],
          unreadCount: 1,
          hasApiGap: true,
          apiGapMessage: 'API Gap 404',
        ),
      ],
    );
  });
}
