import 'package:equatable/equatable.dart';

/// Represents a notification record presented within the in-app notification center.
class InAppNotification extends Equatable {
  final String id;
  final String title;
  final String body;
  final String eventType;
  final String channel;
  final String priority;
  final DateTime createdAt;
  final bool isRead;
  final String? relatedEntityType;
  final String? relatedEntityId;
  final Map<String, dynamic>? payloadJson;

  const InAppNotification({
    required this.id,
    required this.title,
    required this.body,
    required this.eventType,
    this.channel = 'PUSH',
    this.priority = 'NORMAL',
    required this.createdAt,
    this.isRead = false,
    this.relatedEntityType,
    this.relatedEntityId,
    this.payloadJson,
  });

  /// Returns a copy of the notification with updated fields (e.g. marking as read).
  InAppNotification copyWith({
    String? id,
    String? title,
    String? body,
    String? eventType,
    String? channel,
    String? priority,
    DateTime? createdAt,
    bool? isRead,
    String? relatedEntityType,
    String? relatedEntityId,
    Map<String, dynamic>? payloadJson,
  }) {
    return InAppNotification(
      id: id ?? this.id,
      title: title ?? this.title,
      body: body ?? this.body,
      eventType: eventType ?? this.eventType,
      channel: channel ?? this.channel,
      priority: priority ?? this.priority,
      createdAt: createdAt ?? this.createdAt,
      isRead: isRead ?? this.isRead,
      relatedEntityType: relatedEntityType ?? this.relatedEntityType,
      relatedEntityId: relatedEntityId ?? this.relatedEntityId,
      payloadJson: payloadJson ?? this.payloadJson,
    );
  }

  /// Maps event types to human-readable category badges.
  String get categoryLabel {
    final type = eventType.toLowerCase();
    if (type.contains('leave')) {
      return 'Leave';
    }
    if (type.contains('conflict') || type.contains('attendance')) {
      return 'Attendance';
    }
    if (type.contains('fraud') ||
        type.contains('gps') ||
        type.contains('travel')) {
      return 'Security';
    }
    if (type.contains('invitation')) {
      return 'Organization';
    }
    if (type.contains('password') || type.contains('auth')) {
      return 'Account';
    }
    return 'Notification';
  }

  /// Safe deep link route based on event type and related entity.
  String? get deepLinkRoute {
    final type = eventType.toLowerCase();
    if (type.contains('leave')) {
      if (type.contains('submitted') || type.contains('approval')) {
        return '/leave/approvals';
      }
      return '/leave';
    }
    if (type.contains('conflict')) {
      return '/sync';
    }
    if (type.contains('fraud') ||
        type.contains('gps') ||
        type.contains('travel')) {
      return '/home';
    }
    return null;
  }

  @override
  List<Object?> get props => [
        id,
        title,
        body,
        eventType,
        channel,
        priority,
        createdAt,
        isRead,
        relatedEntityType,
        relatedEntityId,
        payloadJson,
      ];
}
