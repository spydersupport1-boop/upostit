import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:mobile/features/attendance/domain/entities/today_shift.dart';
import 'package:mobile/features/history/domain/repositories/history_repository.dart';
import 'schedule_event.dart';
import 'schedule_state.dart';

class ScheduleBloc extends Bloc<ScheduleEvent, ScheduleState> {
  final HistoryRepository _historyRepository;

  ScheduleBloc({required HistoryRepository historyRepository})
      : _historyRepository = historyRepository,
        super(const ScheduleInitial()) {
    on<ScheduleRequested>(_onScheduleRequested);
  }

  Future<void> _onScheduleRequested(
    ScheduleRequested event,
    Emitter<ScheduleState> emit,
  ) async {
    emit(const ScheduleLoading());
    final result = await _historyRepository.getShiftSchedule();

    result.fold(
      (failure) {
        emit(ScheduleFailure(failure.message));
      },
      (shifts) {
        final now = DateTime.now();
        TodayShift? current;
        final List<TodayShift> upcoming = [];

        for (final shift in shifts) {
          if (shift.isActiveOn(now) && current == null) {
            current = shift;
          } else if (shift.isUpcoming(now)) {
            upcoming.add(shift);
          }
        }

        // If no shift is specifically active today, but shifts exist, use the first as current or fallback
        if (current == null && shifts.isNotEmpty && upcoming.isEmpty) {
          current = shifts.first;
        }

        emit(
          ScheduleLoaded(
            currentShift: current,
            upcomingShifts: upcoming,
            allShifts: shifts,
          ),
        );
      },
    );
  }
}
