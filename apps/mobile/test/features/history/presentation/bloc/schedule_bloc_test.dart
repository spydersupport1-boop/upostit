import 'package:bloc_test/bloc_test.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:mobile/core/errors/failure.dart';
import 'package:mobile/core/errors/result.dart';
import 'package:mobile/features/attendance/domain/entities/today_shift.dart';
import 'package:mobile/features/history/domain/repositories/history_repository.dart';
import 'package:mobile/features/history/presentation/bloc/schedule_bloc.dart';
import 'package:mobile/features/history/presentation/bloc/schedule_event.dart';
import 'package:mobile/features/history/presentation/bloc/schedule_state.dart';

class MockHistoryRepository extends Mock implements HistoryRepository {}

void main() {
  late MockHistoryRepository mockRepository;

  final now = DateTime.now();
  final todayStart = DateTime(now.year, now.month, now.day);

  final activeShift = TodayShift(
    id: 's-1',
    name: 'Day Morning Shift',
    code: 'MORN',
    startTime: '08:30:00',
    endTime: '17:00:00',
    breakDurationMinutes: 45,
    effectiveFrom: todayStart.subtract(const Duration(days: 10)),
    effectiveTo: todayStart.add(const Duration(days: 20)),
  );

  final upcomingShift = TodayShift(
    id: 's-2',
    name: 'Night Shift Q1',
    code: 'NIGHT',
    startTime: '22:00:00',
    endTime: '06:00:00',
    isOvernight: true,
    effectiveFrom: todayStart.add(const Duration(days: 25)),
  );

  setUp(() {
    mockRepository = MockHistoryRepository();
  });

  group('ScheduleBloc', () {
    blocTest<ScheduleBloc, ScheduleState>(
      'emits [ScheduleLoading, ScheduleLoaded] with partitioned active and upcoming shifts',
      build: () {
        when(() => mockRepository.getShiftSchedule()).thenAnswer(
          (_) async => Result.success([activeShift, upcomingShift]),
        );
        return ScheduleBloc(historyRepository: mockRepository);
      },
      act: (bloc) => bloc.add(const ScheduleRequested()),
      expect: () => [
        const ScheduleLoading(),
        isA<ScheduleLoaded>()
            .having((s) => s.currentShift?.id, 'currentShift.id', 's-1')
            .having((s) => s.upcomingShifts.length, 'upcomingShifts.length', 1)
            .having((s) => s.upcomingShifts.first.id, 'upcomingShifts.first.id',
                's-2')
            .having((s) => s.hasAssignedShift, 'hasAssignedShift', true),
      ],
    );

    blocTest<ScheduleBloc, ScheduleState>(
      'emits [ScheduleLoading, ScheduleLoaded] with empty shifts when employee has no shifts',
      build: () {
        when(() => mockRepository.getShiftSchedule()).thenAnswer(
          (_) async => const Result.success([]),
        );
        return ScheduleBloc(historyRepository: mockRepository);
      },
      act: (bloc) => bloc.add(const ScheduleRequested()),
      expect: () => [
        const ScheduleLoading(),
        isA<ScheduleLoaded>()
            .having((s) => s.currentShift, 'currentShift', isNull)
            .having((s) => s.upcomingShifts, 'upcomingShifts', isEmpty)
            .having((s) => s.hasAssignedShift, 'hasAssignedShift', false),
      ],
    );

    blocTest<ScheduleBloc, ScheduleState>(
      'emits [ScheduleLoading, ScheduleFailure] on repository error',
      build: () {
        when(() => mockRepository.getShiftSchedule()).thenAnswer(
          (_) async =>
              const Result.failure(ServerFailure('Shift fetch failed')),
        );
        return ScheduleBloc(historyRepository: mockRepository);
      },
      act: (bloc) => bloc.add(const ScheduleRequested()),
      expect: () => [
        const ScheduleLoading(),
        const ScheduleFailure('Shift fetch failed'),
      ],
    );
  });
}
