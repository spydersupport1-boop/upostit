import 'package:equatable/equatable.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_day.dart';

abstract class HistoryEvent extends Equatable {
  const HistoryEvent();

  @override
  List<Object?> get props => [];
}

class HistoryMonthRequested extends HistoryEvent {
  final DateTime month;

  const HistoryMonthRequested({required this.month});

  @override
  List<Object?> get props => [month];
}

class HistoryDaySelected extends HistoryEvent {
  final DateTime selectedDate;
  final AttendanceDay? preloadedDay;

  const HistoryDaySelected({
    required this.selectedDate,
    this.preloadedDay,
  });

  @override
  List<Object?> get props => [selectedDate, preloadedDay];
}

class HistoryRefreshed extends HistoryEvent {
  const HistoryRefreshed();
}
