import 'package:bloc_test/bloc_test.dart';
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:mobile/features/attendance/data/models/attendance_day_model.dart';
import 'package:mobile/features/history/domain/entities/monthly_attendance_summary.dart';
import 'package:mobile/features/history/presentation/bloc/history_bloc.dart';
import 'package:mobile/features/history/presentation/bloc/history_event.dart';
import 'package:mobile/features/history/presentation/bloc/history_state.dart';
import 'package:mobile/features/history/presentation/screens/history_screen.dart';

class MockHistoryBloc extends MockBloc<HistoryEvent, HistoryState>
    implements HistoryBloc {}

void main() {
  late MockHistoryBloc mockHistoryBloc;

  final sampleDays = [
    AttendanceDayModel(
      id: 'day-1',
      tenantId: 't-1',
      employeeId: 'emp-1',
      attendanceDate: DateTime(2026, 11, 2),
      status: 'PRESENT',
      calculationStatus: 'CALCULATED',
      totalWorkingMinutes: 480,
      totalBreakMinutes: 60,
      netWorkingMinutes: 420,
      lateArrivalMinutes: 0,
      earlyDepartureMinutes: 0,
      lastCalculatedAt: DateTime(2026, 11, 2, 18, 0),
    ),
    AttendanceDayModel(
      id: 'day-2',
      tenantId: 't-1',
      employeeId: 'emp-1',
      attendanceDate: DateTime(2026, 11, 3),
      status: 'LATE',
      calculationStatus: 'CALCULATED',
      totalWorkingMinutes: 450,
      totalBreakMinutes: 60,
      netWorkingMinutes: 390,
      lateArrivalMinutes: 30,
      earlyDepartureMinutes: 0,
      lastCalculatedAt: DateTime(2026, 11, 3, 18, 0),
    ),
  ];

  setUpAll(() {
    registerFallbackValue(HistoryMonthRequested(month: DateTime(2026, 11, 1)));
  });

  setUp(() {
    mockHistoryBloc = MockHistoryBloc();
  });

  Widget buildTestWidget() {
    return MaterialApp(
      home: BlocProvider<HistoryBloc>.value(
        value: mockHistoryBloc,
        child: const HistoryScreen(),
      ),
    );
  }

  group('HistoryScreen', () {
    testWidgets('renders monthly metrics, calendar grid, and monthly list',
        (tester) async {
      final summary = MonthlyAttendanceSummary.fromDays(sampleDays);
      when(() => mockHistoryBloc.state).thenReturn(
        HistoryLoaded(
          currentMonth: DateTime(2026, 11, 1),
          days: sampleDays,
          summary: summary,
        ),
      );

      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      expect(find.text('Attendance History'), findsOneWidget);
      expect(find.text('Present'), findsNWidgets(2));
      expect(find.text('Late'), findsNWidgets(2));
      expect(find.text('November 2026'), findsOneWidget);
      expect(find.text('Monthly Records'), findsOneWidget);
      expect(
          find.byKey(const Key('calendar_prev_month_button')), findsOneWidget);
      expect(
          find.byKey(const Key('calendar_next_month_button')), findsOneWidget);
    });

    testWidgets(
        'dispatches HistoryMonthRequested on prev/next month button tap',
        (tester) async {
      final summary = MonthlyAttendanceSummary.fromDays(sampleDays);
      when(() => mockHistoryBloc.state).thenReturn(
        HistoryLoaded(
          currentMonth: DateTime(2026, 11, 1),
          days: sampleDays,
          summary: summary,
        ),
      );

      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('calendar_prev_month_button')));
      verify(() => mockHistoryBloc.add(
            HistoryMonthRequested(month: DateTime(2026, 10, 1)),
          )).called(1);

      await tester.tap(find.byKey(const Key('calendar_next_month_button')));
      verify(() => mockHistoryBloc.add(
            HistoryMonthRequested(month: DateTime(2026, 12, 1)),
          )).called(1);
    });

    testWidgets('renders failure state and retries on tap', (tester) async {
      when(() => mockHistoryBloc.state).thenReturn(
        const HistoryFailure('Server disconnected'),
      );

      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      expect(find.text('Failed to Load History'), findsOneWidget);
      expect(find.text('Server disconnected'), findsOneWidget);
      expect(find.byKey(const Key('history_retry_button')), findsOneWidget);

      await tester.tap(find.byKey(const Key('history_retry_button')));
      verify(() => mockHistoryBloc.add(any(that: isA<HistoryMonthRequested>())))
          .called(1);
    });
  });
}
