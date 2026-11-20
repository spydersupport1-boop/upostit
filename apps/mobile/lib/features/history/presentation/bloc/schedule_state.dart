import 'package:equatable/equatable.dart';
import 'package:mobile/features/attendance/domain/entities/today_shift.dart';

abstract class ScheduleState extends Equatable {
  const ScheduleState();

  @override
  List<Object?> get props => [];
}

class ScheduleInitial extends ScheduleState {
  const ScheduleInitial();
}

class ScheduleLoading extends ScheduleState {
  const ScheduleLoading();
}

class ScheduleLoaded extends ScheduleState {
  final TodayShift? currentShift;
  final List<TodayShift> upcomingShifts;
  final List<TodayShift> allShifts;

  const ScheduleLoaded({
    this.currentShift,
    this.upcomingShifts = const [],
    this.allShifts = const [],
  });

  bool get hasAssignedShift =>
      currentShift != null || upcomingShifts.isNotEmpty;

  @override
  List<Object?> get props => [currentShift, upcomingShifts, allShifts];
}

class ScheduleFailure extends ScheduleState {
  final String message;

  const ScheduleFailure(this.message);

  @override
  List<Object?> get props => [message];
}
