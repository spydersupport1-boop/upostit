import '../../domain/entities/punch_result.dart';
import 'attendance_event_model.dart';

/// Data Transfer Object for PunchResponse JSON payload.
class PunchResponseModel extends PunchResult {
  const PunchResponseModel({
    required super.event,
    super.additionalEvents,
    super.isIdempotentReplay,
  });

  factory PunchResponseModel.fromJson(Map<String, dynamic> json) {
    final eventJson = json['event'] as Map<String, dynamic>;
    final additionalEventsJson =
        (json['additional_events'] as List<dynamic>?) ?? [];

    return PunchResponseModel(
      event: AttendanceEventModel.fromJson(eventJson),
      additionalEvents: additionalEventsJson
          .map((e) => AttendanceEventModel.fromJson(e as Map<String, dynamic>))
          .toList(),
      isIdempotentReplay: (json['idempotent_replay'] as bool?) ?? false,
    );
  }
}
