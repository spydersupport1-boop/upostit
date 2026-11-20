import 'package:equatable/equatable.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_day.dart';
import 'package:mobile/features/history/domain/entities/daily_attendance_detail.dart';
import 'package:mobile/features/history/domain/entities/monthly_attendance_summary.dart';

abstract class HistoryState extends Equatable {
  const HistoryState();

  @override
  List<Object?> get props => [];
}

class HistoryInitial extends HistoryState {
  const HistoryInitial();
}

class HistoryLoading extends HistoryState {
  const HistoryLoading();
}

class HistoryLoaded extends HistoryState {
  final DateTime currentMonth;
  final List<AttendanceDay> days;
  final MonthlyAttendanceSummary summary;
  final DateTime? selectedDate;
  final DailyAttendanceDetail? selectedDayDetail;
  final bool isLoadingDayDetail;
  final String? errorMessage;

  const HistoryLoaded({
    required this.currentMonth,
    required this.days,
    required this.summary,
    this.selectedDate,
    this.selectedDayDetail,
    this.isLoadingDayDetail = false,
    this.errorMessage,
  });

  HistoryLoaded copyWith({
    DateTime? currentMonth,
    List<AttendanceDay>? days,
    MonthlyAttendanceSummary? summary,
    DateTime? selectedDate,
    DailyAttendanceDetail? selectedDayDetail,
    bool? isLoadingDayDetail,
    String? errorMessage,
  }) {
    return HistoryLoaded(
      currentMonth: currentMonth ?? this.currentMonth,
      days: days ?? this.days,
      summary: summary ?? this.summary,
      selectedDate: selectedDate ?? this.selectedDate,
      selectedDayDetail: selectedDayDetail ?? this.selectedDayDetail,
      isLoadingDayDetail: isLoadingDayDetail ?? this.isLoadingDayDetail,
      errorMessage: errorMessage,
    );
  }

  @override
  List<Object?> get props => [
        currentMonth,
        days,
        summary,
        selectedDate,
        selectedDayDetail,
        isLoadingDayDetail,
        errorMessage,
      ];
}

class HistoryFailure extends HistoryState {
  final String message;

  const HistoryFailure(this.message);

  @override
  List<Object?> get props => [message];
}
