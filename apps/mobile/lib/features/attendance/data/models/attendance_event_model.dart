import '../../domain/entities/attendance_event.dart';

/// Data Transfer Object for AttendanceEvent JSON payloads.
class AttendanceEventModel extends AttendanceEvent {
  const AttendanceEventModel({
    required super.id,
    required super.tenantId,
    required super.employeeId,
    required super.eventType,
    required super.eventCategory,
    required super.serverReceivedAt,
    super.deviceReportedAt,
    required super.effectiveAt,
    super.clockDriftSeconds,
    required super.source,
    super.deviceId,
    required super.timestampVerificationStatus,
    required super.reviewStatus,
    required super.idempotencyKey,
    super.locationId,
    super.metadata,
    required super.createdAt,
  });

  factory AttendanceEventModel.fromJson(Map<String, dynamic> json) {
    return AttendanceEventModel(
      id: json['id'] as String,
      tenantId: json['tenant_id'] as String,
      employeeId: json['employee_id'] as String,
      eventType:
          AttendanceEventTypeX.fromBackendString(json['event_type'] as String),
      eventCategory: (json['event_category'] as String?) ?? 'STANDARD',
      serverReceivedAt: DateTime.parse(json['server_received_at'] as String),
      deviceReportedAt: json['device_reported_at'] != null
          ? DateTime.parse(json['device_reported_at'] as String)
          : null,
      effectiveAt: DateTime.parse(json['effective_at'] as String),
      clockDriftSeconds: (json['clock_drift_seconds'] as num?)?.toDouble(),
      source: (json['source'] as String?) ?? 'MOBILE',
      deviceId: json['device_id'] as String?,
      timestampVerificationStatus:
          (json['timestamp_verification_status'] as String?) ??
              'SERVER_AUTHORITATIVE',
      reviewStatus: (json['review_status'] as String?) ?? 'NOT_REQUIRED',
      idempotencyKey: json['idempotency_key'] as String,
      locationId: json['location_id'] as String?,
      metadata: (json['metadata'] as Map<String, dynamic>?) ??
          (json['metadata_json'] as Map<String, dynamic>?) ??
          const {},
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'tenant_id': tenantId,
      'employee_id': employeeId,
      'event_type': eventType.toBackendString(),
      'event_category': eventCategory,
      'server_received_at': serverReceivedAt.toIso8601String(),
      'device_reported_at': deviceReportedAt?.toIso8601String(),
      'effective_at': effectiveAt.toIso8601String(),
      'clock_drift_seconds': clockDriftSeconds,
      'source': source,
      'device_id': deviceId,
      'timestamp_verification_status': timestampVerificationStatus,
      'review_status': reviewStatus,
      'idempotency_key': idempotencyKey,
      'location_id': locationId,
      'metadata': metadata,
      'created_at': createdAt.toIso8601String(),
    };
  }
}
