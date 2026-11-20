import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:mobile/features/history/domain/entities/monthly_attendance_summary.dart';
import 'package:mobile/features/history/domain/repositories/history_repository.dart';
import 'history_event.dart';
import 'history_state.dart';

class HistoryBloc extends Bloc<HistoryEvent, HistoryState> {
  final HistoryRepository _historyRepository;

  HistoryBloc({required HistoryRepository historyRepository})
      : _historyRepository = historyRepository,
        super(const HistoryInitial()) {
    on<HistoryMonthRequested>(_onMonthRequested);
    on<HistoryDaySelected>(_onDaySelected);
    on<HistoryRefreshed>(_onRefreshed);
  }

  Future<void> _onMonthRequested(
    HistoryMonthRequested event,
    Emitter<HistoryState> emit,
  ) async {
    emit(const HistoryLoading());
    final result = await _historyRepository.getMonthlyAttendance(
      year: event.month.year,
      month: event.month.month,
    );

    result.fold(
      (failure) {
        emit(HistoryFailure(failure.message));
      },
      (days) {
        final summary = MonthlyAttendanceSummary.fromDays(days);
        emit(
          HistoryLoaded(
            currentMonth: DateTime(event.month.year, event.month.month, 1),
            days: days,
            summary: summary,
          ),
        );
      },
    );
  }

  Future<void> _onDaySelected(
    HistoryDaySelected event,
    Emitter<HistoryState> emit,
  ) async {
    if (state is! HistoryLoaded) return;
    final currentState = state as HistoryLoaded;

    emit(currentState.copyWith(
      selectedDate: event.selectedDate,
      isLoadingDayDetail: true,
    ));

    final detailResult = await _historyRepository.getDailyAttendanceDetail(
      event.selectedDate,
      preloadedDay: event.preloadedDay,
    );

    detailResult.fold(
      (failure) {
        emit(currentState.copyWith(
          isLoadingDayDetail: false,
          errorMessage: failure.message,
        ));
      },
      (detail) {
        emit(currentState.copyWith(
          selectedDate: event.selectedDate,
          selectedDayDetail: detail,
          isLoadingDayDetail: false,
        ));
      },
    );
  }

  Future<void> _onRefreshed(
    HistoryRefreshed event,
    Emitter<HistoryState> emit,
  ) async {
    final month = (state is HistoryLoaded)
        ? (state as HistoryLoaded).currentMonth
        : DateTime.now();
    add(HistoryMonthRequested(month: month));
  }
}
