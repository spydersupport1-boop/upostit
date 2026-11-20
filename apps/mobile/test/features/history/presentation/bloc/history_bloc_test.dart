import 'package:bloc_test/bloc_test.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:mobile/core/errors/failure.dart';
import 'package:mobile/core/errors/result.dart';
import 'package:mobile/features/attendance/data/models/attendance_day_model.dart';
import 'package:mobile/features/history/domain/entities/daily_attendance_detail.dart';
import 'package:mobile/features/history/domain/entities/monthly_attendance_summary.dart';
import 'package:mobile/features/history/domain/repositories/history_repository.dart';
import 'package:mobile/features/history/presentation/bloc/history_bloc.dart';
import 'package:mobile/features/history/presentation/bloc/history_event.dart';
import 'package:mobile/features/history/presentation/bloc/history_state.dart';

class MockHistoryRepository extends Mock implements HistoryRepository {}

void main() {
  late MockHistoryRepository mockRepository;

  final sampleDays = [
    AttendanceDayModel(
      id: 'day-1',
      tenantId: 'tenant-1',
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
      tenantId: 'tenant-1',
      employeeId: 'emp-1',
      attendanceDate: DateTime(2026, 11, 3),
      status: 'LATE',
      calculationStatus: 'CALCULATED',
      totalWorkingMinutes: 460,
      totalBreakMinutes: 60,
      netWorkingMinutes: 400,
      lateArrivalMinutes: 20,
      earlyDepartureMinutes: 0,
      lastCalculatedAt: DateTime(2026, 11, 3, 18, 0),
    ),
    AttendanceDayModel(
      id: 'day-3',
      tenantId: 'tenant-1',
      employeeId: 'emp-1',
      attendanceDate: DateTime(2026, 11, 4),
      status: 'ABSENT',
      calculationStatus: 'CALCULATED',
      totalWorkingMinutes: 0,
      totalBreakMinutes: 0,
      netWorkingMinutes: 0,
      lateArrivalMinutes: 0,
      earlyDepartureMinutes: 0,
      lastCalculatedAt: DateTime(2026, 11, 4, 18, 0),
    ),
  ];

  final sampleDetail = DailyAttendanceDetail(
    date: DateTime(2026, 11, 2),
    dayRecord: sampleDays[0],
    events: const [],
  );

  setUp(() {
    mockRepository = MockHistoryRepository();
  });

  group('HistoryBloc', () {
    blocTest<HistoryBloc, HistoryState>(
      'emits [HistoryLoading, HistoryLoaded] with accurate monthly summary metrics when HistoryMonthRequested succeeds',
      build: () {
        when(() => mockRepository.getMonthlyAttendance(
              year: 2026,
              month: 11,
            )).thenAnswer((_) async => Result.success(sampleDays));
        return HistoryBloc(historyRepository: mockRepository);
      },
      act: (bloc) =>
          bloc.add(HistoryMonthRequested(month: DateTime(2026, 11, 1))),
      expect: () => [
        const HistoryLoading(),
        isA<HistoryLoaded>()
            .having((s) => s.days.length, 'days.length', 3)
            .having((s) => s.summary.presentCount, 'presentCount', 1)
            .having((s) => s.summary.lateCount, 'lateCount', 1)
            .having((s) => s.summary.absentCount, 'absentCount', 1)
            .having((s) => s.summary.formattedTotalHours, 'formattedTotalHours',
                '13h 40m')
            .having((s) => s.summary.totalWorkingDuration.inMinutes,
                'totalWorkingDuration.inMinutes', 820),
      ],
    );

    blocTest<HistoryBloc, HistoryState>(
      'emits [HistoryLoading, HistoryFailure] when HistoryMonthRequested returns failure',
      build: () {
        when(() => mockRepository.getMonthlyAttendance(
              year: 2026,
              month: 11,
            )).thenAnswer(
          (_) async => const Result.failure(
              ServerFailure('Unable to load history records')),
        );
        return HistoryBloc(historyRepository: mockRepository);
      },
      act: (bloc) =>
          bloc.add(HistoryMonthRequested(month: DateTime(2026, 11, 1))),
      expect: () => [
        const HistoryLoading(),
        const HistoryFailure('Unable to load history records'),
      ],
    );

    blocTest<HistoryBloc, HistoryState>(
      'fetches daily attendance detail and emits updated HistoryLoaded on HistoryDaySelected',
      build: () {
        when(() => mockRepository.getDailyAttendanceDetail(
              DateTime(2026, 11, 2),
              preloadedDay: any(named: 'preloadedDay'),
            )).thenAnswer((_) async => Result.success(sampleDetail));
        return HistoryBloc(historyRepository: mockRepository);
      },
      seed: () => HistoryLoaded(
        currentMonth: DateTime(2026, 11, 1),
        days: sampleDays,
        summary: MonthlyAttendanceSummary.fromDays(sampleDays),
      ),
      act: (bloc) =>
          bloc.add(HistoryDaySelected(selectedDate: DateTime(2026, 11, 2))),
      expect: () => [
        isA<HistoryLoaded>()
            .having(
                (s) => s.selectedDate, 'selectedDate', DateTime(2026, 11, 2))
            .having((s) => s.isLoadingDayDetail, 'isLoadingDayDetail', true),
        isA<HistoryLoaded>()
            .having(
                (s) => s.selectedDate, 'selectedDate', DateTime(2026, 11, 2))
            .having(
                (s) => s.selectedDayDetail, 'selectedDayDetail', sampleDetail)
            .having((s) => s.isLoadingDayDetail, 'isLoadingDayDetail', false),
      ],
    );
  });
}
