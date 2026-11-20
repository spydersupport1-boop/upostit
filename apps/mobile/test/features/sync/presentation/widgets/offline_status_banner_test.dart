import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/features/sync/domain/entities/sync_queue_summary.dart';
import 'package:mobile/features/sync/presentation/bloc/sync_bloc.dart';
import 'package:mobile/features/sync/presentation/bloc/sync_state.dart';
import 'package:mobile/features/sync/presentation/widgets/offline_status_banner.dart';
import 'package:mocktail/mocktail.dart';

class MockSyncBloc extends Mock implements SyncBloc {}

void main() {
  late MockSyncBloc mockSyncBloc;

  setUp(() {
    mockSyncBloc = MockSyncBloc();
    when(() => mockSyncBloc.stream).thenAnswer((_) => const Stream.empty());
  });

  Widget createWidgetUnderTest({VoidCallback? onTap}) {
    return MaterialApp(
      home: Scaffold(
        body: BlocProvider<SyncBloc>.value(
          value: mockSyncBloc,
          child: OfflineStatusBanner(onTap: onTap),
        ),
      ),
    );
  }

  group('OfflineStatusBanner', () {
    testWidgets('renders SizedBox.shrink when online and 0 pending records',
        (tester) async {
      when(() => mockSyncBloc.state).thenReturn(const SyncState(
        isConnected: true,
        summary: SyncQueueSummary(),
        isSyncing: false,
      ));

      await tester.pumpWidget(createWidgetUnderTest());

      expect(find.byType(InkWell), findsNothing);
      expect(find.text('Offline Mode Active'), findsNothing);
    });

    testWidgets('renders Offline Mode banner when isConnected is false',
        (tester) async {
      when(() => mockSyncBloc.state).thenReturn(const SyncState(
        isConnected: false,
        summary: SyncQueueSummary(pendingCount: 3),
        isSyncing: false,
      ));

      await tester.pumpWidget(createWidgetUnderTest());

      expect(find.textContaining('Offline Mode — Punches are saved locally'),
          findsOneWidget);
      expect(find.text('3 pending'), findsOneWidget);
      expect(find.byIcon(Icons.cloud_off_rounded), findsOneWidget);
    });

    testWidgets('renders Synchronizing banner when isSyncing is true',
        (tester) async {
      when(() => mockSyncBloc.state).thenReturn(const SyncState(
        isConnected: true,
        summary: SyncQueueSummary(pendingCount: 2),
        isSyncing: true,
      ));

      await tester.pumpWidget(createWidgetUnderTest());

      expect(find.text('Synchronizing offline attendance records...'),
          findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
    });

    testWidgets('triggers onTap callback when tapped in offline mode',
        (tester) async {
      bool tapped = false;
      when(() => mockSyncBloc.state).thenReturn(const SyncState(
        isConnected: false,
        summary: SyncQueueSummary(pendingCount: 1),
        isSyncing: false,
      ));

      await tester.pumpWidget(createWidgetUnderTest(onTap: () {
        tapped = true;
      }));

      await tester.tap(find.byType(InkWell));
      await tester.pump();

      expect(tapped, isTrue);
    });
  });
}
