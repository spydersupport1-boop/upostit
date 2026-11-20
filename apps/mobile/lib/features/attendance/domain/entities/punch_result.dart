import 'package:equatable/equatable.dart';
import 'attendance_event.dart';

/// Domain entity representing the result of a punch operation returned by the backend ledger.
class PunchResult extends Equatable {
  final AttendanceEvent event;
  final List<AttendanceEvent> additionalEvents;
  final bool isIdempotentReplay;

  const PunchResult({
    required this.event,
    this.additionalEvents = const [],
    this.isIdempotentReplay = false,
  });

  @override
  List<Object?> get props => [event, additionalEvents, isIdempotentReplay];
}
