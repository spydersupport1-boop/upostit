import 'package:bloc_test/bloc_test.dart';
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:mobile/features/attendance/domain/entities/today_shift.dart';
import 'package:mobile/features/history/presentation/bloc/schedule_bloc.dart';
import 'package:mobile/features/history/presentation/bloc/schedule_event.dart';
import 'package:mobile/features/history/presentation/bloc/schedule_state.dart';
import 'package:mobile/features/history/presentation/screens/schedule_screen.dart';

class MockScheduleBloc extends MockBloc<ScheduleEvent, ScheduleState>
    implements ScheduleBloc {}

void main() {
  late MockScheduleBloc mockScheduleBloc;

  final activeShift = TodayShift(
    id: 's-1',
    name: 'Day Morning Shift',
    code: 'MORN',
    startTime: '08:30:00',
    endTime: '17:00:00',
    breakDurationMinutes: 45,
    weeklyOffDays: const [5, 6],
    effectiveFrom: DateTime.now().subtract(const Duration(days: 5)),
  );

  final upcomingShift = TodayShift(
    id: 's-2',
    name: 'Night Shift Rotation',
    code: 'NIGHT',
    startTime: '22:00:00',
    endTime: '06:00:00',
    isOvernight: true,
    effectiveFrom: DateTime.now().add(const Duration(days: 14)),
  );

  setUp(() {
    mockScheduleBloc = MockScheduleBloc();
  });

  Widget buildTestWidget() {
    return MaterialApp(
      home: BlocProvider<ScheduleBloc>.value(
        value: mockScheduleBloc,
        child: const ScheduleScreen(),
      ),
    );
  }

  group('ScheduleScreen', () {
    testWidgets(
        'renders active shift card with timings, breaks and weekly offs',
        (tester) async {
      when(() => mockScheduleBloc.state).thenReturn(
        ScheduleLoaded(
          currentShift: activeShift,
          upcomingShifts: [upcomingShift],
          allShifts: [activeShift, upcomingShift],
        ),
      );

      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      expect(find.text('Shift Schedule'), findsOneWidget);
      expect(find.text('Day Morning Shift (MORN)'), findsOneWidget);
      expect(find.text('8:30 AM – 5:00 PM'), findsOneWidget);
      expect(find.text('45m break'), findsOneWidget);
      expect(find.text('Active Shift'), findsOneWidget);
      expect(find.text('Active Now'), findsOneWidget);
      expect(find.text('Upcoming Shifts (1)'), findsOneWidget);
      expect(find.text('Night Shift Rotation (NIGHT)'), findsOneWidget);
      expect(find.text('Overnight Shift'), findsOneWidget);
    });

    testWidgets('renders empty state when no shift is assigned',
        (tester) async {
      when(() => mockScheduleBloc.state).thenReturn(
        const ScheduleLoaded(
          currentShift: null,
          upcomingShifts: [],
          allShifts: [],
        ),
      );

      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      expect(find.text('No Assigned Shift'), findsOneWidget);
      expect(
        find.text(
            'You currently have no scheduled shift assignments. You may be on flexible hours or an off day.'),
        findsOneWidget,
      );
    });

    testWidgets('renders error banner and retry button on failure',
        (tester) async {
      when(() => mockScheduleBloc.state).thenReturn(
        const ScheduleFailure('Connection to shifts service failed'),
      );

      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      expect(find.text('Failed to Load Schedule'), findsOneWidget);
      expect(find.text('Connection to shifts service failed'), findsOneWidget);
      expect(find.text('Retry'), findsOneWidget);

      await tester.tap(find.text('Retry'));
      verify(() => mockScheduleBloc.add(const ScheduleRequested())).called(1);
    });
  });
}
