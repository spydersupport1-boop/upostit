import 'package:equatable/equatable.dart';

/// Normalized payload structure for remote push notifications received on device.
class PushNotificationPayload extends Equatable {
  final String? notificationId;
  final String title;
  final String body;
  final String? eventType;
  final String? priority;
  final Map<String, dynamic> data;
  final DateTime receivedAt;

  const PushNotificationPayload({
    this.notificationId,
    required this.title,
    required this.body,
    this.eventType,
    this.priority,
    this.data = const {},
    required this.receivedAt,
  });

  @override
  List<Object?> get props => [
        notificationId,
        title,
        body,
        eventType,
        priority,
        data,
        receivedAt,
      ];
}
