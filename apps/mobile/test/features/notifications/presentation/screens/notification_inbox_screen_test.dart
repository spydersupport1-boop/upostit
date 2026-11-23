import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/theme/app_theme.dart';
import 'package:mobile/features/notifications/domain/entities/in_app_notification.dart';
import 'package:mobile/features/notifications/presentation/bloc/notification_bloc.dart';
import 'package:mobile/features/notifications/presentation/bloc/notification_event.dart';
import 'package:mobile/features/notifications/presentation/bloc/notification_state.dart';
import 'package:mobile/features/notifications/presentation/screens/notification_inbox_screen.dart';
import 'package:mobile/features/notifications/presentation/widgets/notification_api_gap_banner.dart';
import 'package:mobile/features/notifications/presentation/widgets/notification_tile.dart';
import 'package:mobile/shared/widgets/empty_state_view.dart';
import 'package:mobile/shared/widgets/error_banner.dart';
import 'package:mobile/shared/widgets/loading_indicator.dart';
import 'package:mocktail/mocktail.dart';

class MockNotificationBloc extends Mock implements NotificationBloc {}

class FakeNotificationEvent extends Fake implements NotificationEvent {}

void main() {
  setUpAll(() {
    registerFallbackValue(FakeNotificationEvent());
  });

  late MockNotificationBloc mockNotificationBloc;

  final testNotification1 = InAppNotification(
    id: 'notif-1',
    title: 'Leave Request Approved',
    body: 'Your annual leave request has been approved by your supervisor.',
    eventType: 'leave_request_approved',
    channel: 'PUSH',
    priority: 'NORMAL',
    createdAt: DateTime.now().subtract(const Duration(minutes: 5)),
    isRead: false,
    relatedEntityType: 'leave_request',
    relatedEntityId: 'leave-123',
  );

  final testNotification2 = InAppNotification(
    id: 'notif-2',
    title: 'Fraud Alert Warning',
    body: 'Suspicious attendance check-in detected.',
    eventType: 'fraud_score_high',
    channel: 'PUSH',
    priority: 'HIGH',
    createdAt: DateTime.now().subtract(const Duration(hours: 2)),
    isRead: true,
    relatedEntityType: 'attendance',
    relatedEntityId: 'att-456',
  );

  setUp(() {
    mockNotificationBloc = MockNotificationBloc();
    when(() => mockNotificationBloc.stream)
        .thenAnswer((_) => const Stream.empty());
  });

  Widget buildTestWidget() {
    return MaterialApp(
      theme: AppTheme.lightTheme,
      home: BlocProvider<NotificationBloc>.value(
        value: mockNotificationBloc,
        child: const NotificationInboxScreen(),
      ),
    );
  }

  testWidgets('renders loading state when NotificationLoading', (tester) async {
    when(() => mockNotificationBloc.state).thenReturn(
      const NotificationLoading(message: 'Loading notifications...'),
    );

    await tester.pumpWidget(buildTestWidget());

    expect(find.byType(LoadingIndicator), findsOneWidget);
    expect(find.text('Loading notifications...'), findsOneWidget);
  });

  testWidgets('renders error banner and retry button when NotificationError',
      (tester) async {
    when(() => mockNotificationBloc.state).thenReturn(
      const NotificationError('Failed to fetch notifications from backend'),
    );

    await tester.pumpWidget(buildTestWidget());

    expect(find.byType(ErrorBanner), findsOneWidget);
    expect(find.text('Failed to fetch notifications from backend'),
        findsOneWidget);
    expect(find.text('Try Again'), findsOneWidget);

    await tester.tap(find.text('Try Again'));
    await tester.pump();

    verify(() => mockNotificationBloc
            .add(any(that: isA<FetchNotificationInboxRequested>())))
        .called(greaterThanOrEqualTo(1));
  });

  testWidgets(
      'renders empty state when NotificationLoaded has no notifications',
      (tester) async {
    when(() => mockNotificationBloc.state).thenReturn(
      const NotificationLoaded(
        notifications: [],
        unreadCount: 0,
      ),
    );

    await tester.pumpWidget(buildTestWidget());

    expect(find.byType(EmptyStateView), findsOneWidget);
    expect(find.text('No Notifications'), findsOneWidget);
    expect(
      find.text('You have no outbound notifications or alerts at this time.'),
      findsOneWidget,
    );
  });

  testWidgets('renders notification tiles and unread badge count when loaded',
      (tester) async {
    when(() => mockNotificationBloc.state).thenReturn(
      NotificationLoaded(
        notifications: [testNotification1, testNotification2],
        unreadCount: 1,
      ),
    );

    await tester.pumpWidget(buildTestWidget());

    expect(find.byType(NotificationTile), findsNWidgets(2));
    expect(find.text('Leave Request Approved'), findsOneWidget);
    expect(find.text('Fraud Alert Warning'), findsOneWidget);
    expect(find.text('All (2)'), findsOneWidget);
    expect(find.text('Unread (1)'), findsOneWidget);
  });

  testWidgets('renders NotificationApiGapBanner when hasApiGap is true',
      (tester) async {
    when(() => mockNotificationBloc.state).thenReturn(
      NotificationLoaded(
        notifications: [testNotification1],
        unreadCount: 1,
        hasApiGap: true,
        apiGapMessage:
            'Backend GET /api/v1/notifications/inbox endpoint is not yet available.',
      ),
    );

    await tester.pumpWidget(buildTestWidget());

    expect(find.byType(NotificationApiGapBanner), findsOneWidget);
    expect(
      find.text(
          'Backend GET /api/v1/notifications/inbox endpoint is not yet available.'),
      findsOneWidget,
    );
  });

  testWidgets('filters list by unread when unread choice chip is tapped',
      (tester) async {
    when(() => mockNotificationBloc.state).thenReturn(
      NotificationLoaded(
        notifications: [testNotification1, testNotification2],
        unreadCount: 1,
      ),
    );

    await tester.pumpWidget(buildTestWidget());

    expect(find.byType(NotificationTile), findsNWidgets(2));

    await tester.tap(find.byKey(const Key('filter_chip_unread')));
    await tester.pumpAndSettle();

    // Only unread notification (testNotification1) is displayed
    expect(find.byType(NotificationTile), findsOneWidget);
    expect(find.text('Leave Request Approved'), findsOneWidget);
    expect(find.text('Fraud Alert Warning'), findsNothing);

    // Switch back to All
    await tester.tap(find.byKey(const Key('filter_chip_all')));
    await tester.pumpAndSettle();

    expect(find.byType(NotificationTile), findsNWidgets(2));
  });

  testWidgets(
      'tapping refresh icon dispatches FetchNotificationInboxRequested(isRefresh: true)',
      (tester) async {
    when(() => mockNotificationBloc.state).thenReturn(
      NotificationLoaded(
        notifications: [testNotification1],
        unreadCount: 1,
      ),
    );

    await tester.pumpWidget(buildTestWidget());

    await tester
        .tap(find.byKey(const Key('refresh_notifications_icon_button')));
    await tester.pump();

    verify(() => mockNotificationBloc.add(
          const FetchNotificationInboxRequested(isRefresh: true),
        )).called(1);
  });

  testWidgets(
      'tapping a notification dispatches NotificationTappedEvent and opens dialog',
      (tester) async {
    when(() => mockNotificationBloc.state).thenReturn(
      NotificationLoaded(
        notifications: [testNotification1],
        unreadCount: 1,
      ),
    );

    await tester.pumpWidget(buildTestWidget());

    await tester.tap(find.byKey(const Key('notification_tile_notif-1')));
    await tester.pumpAndSettle();

    verify(() => mockNotificationBloc.add(
          NotificationTappedEvent(testNotification1),
        )).called(1);

    // Dialog should be visible
    expect(find.text('Leave Request Approved'),
        findsNWidgets(2)); // in tile and in dialog
    expect(find.text('Close'), findsOneWidget);
    expect(find.text('View Leave'), findsOneWidget);
  });
}
