import '../../domain/entities/in_app_notification.dart';

/// Data transfer object mapping in-app notifications from backend or local push payloads.
class InAppNotificationModel extends InAppNotification {
  const InAppNotificationModel({
    required super.id,
    required super.title,
    required super.body,
    required super.eventType,
    super.channel = 'PUSH',
    super.priority = 'NORMAL',
    required super.createdAt,
    super.isRead = false,
    super.relatedEntityType,
    super.relatedEntityId,
    super.payloadJson,
  });

  factory InAppNotificationModel.fromJson(Map<String, dynamic> json) {
    // Subject fallback to title or event type
    final rawTitle = json['subject'] as String? ??
        json['title'] as String? ??
        _formatEventTypeToTitle(
            json['event_type'] as String? ?? 'Notification');

    final rawBody = json['body'] as String? ?? json['message'] as String? ?? '';

    return InAppNotificationModel(
      id: json['id'] as String? ??
          DateTime.now().millisecondsSinceEpoch.toString(),
      title: rawTitle,
      body: rawBody,
      eventType: json['event_type'] as String? ?? 'general_notification',
      channel: json['channel'] as String? ?? 'PUSH',
      priority: json['priority'] as String? ?? 'NORMAL',
      createdAt: json['created_at'] != null
          ? DateTime.parse(json['created_at'] as String)
          : (json['scheduled_for'] != null
              ? DateTime.parse(json['scheduled_for'] as String)
              : DateTime.now()),
      isRead: json['is_read'] as bool? ?? false,
      relatedEntityType: json['related_entity_type'] as String?,
      relatedEntityId: json['related_entity_id'] as String?,
      payloadJson: json['payload_json'] as Map<String, dynamic>?,
    );
  }

  static String _formatEventTypeToTitle(String eventType) {
    return eventType
        .replaceAll('_', ' ')
        .split(' ')
        .map(
            (w) => w.isNotEmpty ? '${w[0].toUpperCase()}${w.substring(1)}' : '')
        .join(' ');
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'title': title,
      'body': body,
      'event_type': eventType,
      'channel': channel,
      'priority': priority,
      'created_at': createdAt.toIso8601String(),
      'is_read': isRead,
      'related_entity_type': relatedEntityType,
      'related_entity_id': relatedEntityId,
      'payload_json': payloadJson,
    };
  }
}
