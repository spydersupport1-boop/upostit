import 'package:equatable/equatable.dart';
import '../../domain/entities/attendance_event.dart';

abstract class AttendanceBlocEvent extends Equatable {
  const AttendanceBlocEvent();

  @override
  List<Object?> get props => [];
}

/// Dispatched to load or refresh the employee's attendance dashboard.
class AttendanceDashboardRequested extends AttendanceBlocEvent {
  const AttendanceDashboardRequested();
}

/// Dispatched when the user initiates a punch action (Check-In, Check-Out, Start Break, End Break).
class PunchActionSubmitted extends AttendanceBlocEvent {
  final AttendanceEventType eventType;
  final String?
      customIdempotencyKey; // Provided mainly for testing key override

  const PunchActionSubmitted({
    required this.eventType,
    this.customIdempotencyKey,
  });

  @override
  List<Object?> get props => [eventType, customIdempotencyKey];
}

/// Dispatched when the user taps 'Retry' after a failed punch attempt.
///
/// MUST reuse the exact same idempotency key from the failed attempt.
class PunchRetryRequested extends AttendanceBlocEvent {
  const PunchRetryRequested();
}

/// Internal event fired every second by the elapsed timer ticker.
class LiveTimerTicked extends AttendanceBlocEvent {
  const LiveTimerTicked();
}

/// Dispatched to dismiss error/success banners in the UI.
class DismissFeedbackNotice extends AttendanceBlocEvent {
  const DismissFeedbackNotice();
}

/// Dispatched to prompt for location permissions or open device settings when required by policy.
class LocationPermissionResolutionRequested extends AttendanceBlocEvent {
  const LocationPermissionResolutionRequested();
}

/// Dispatched to query device location and calculate proximity to assigned workplace.
class LocationProbeRequested extends AttendanceBlocEvent {
  const LocationProbeRequested();
}

/// Dispatched to inspect connected Wi-Fi and probe verification against assigned workplace.
class WifiProbeRequested extends AttendanceBlocEvent {
  const WifiProbeRequested();
}
