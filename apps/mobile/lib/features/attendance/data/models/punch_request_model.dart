import '../../domain/entities/attendance_event.dart';

/// Data Transfer Object for POST /api/v1/attendance/punch.
class PunchRequestModel {
  final AttendanceEventType eventType;
  final String idempotencyKey;
  final DateTime? deviceReportedAt;
  final String? employeeId;
  final String? locationId;
  final double? latitude;
  final double? longitude;
  final double? accuracyMeters;
  final String? wifiBssid;
  final String? wifiSsid;
  final String? wifiSignalStatus;
  final String? deviceId;
  final bool? isMockLocation;
  final DateTime? locationCapturedAt;
  final Map<String, dynamic> metadata;

  const PunchRequestModel({
    required this.eventType,
    required this.idempotencyKey,
    this.deviceReportedAt,
    this.employeeId,
    this.locationId,
    this.latitude,
    this.longitude,
    this.accuracyMeters,
    this.wifiBssid,
    this.wifiSsid,
    this.wifiSignalStatus,
    this.deviceId,
    this.isMockLocation,
    this.locationCapturedAt,
    this.metadata = const {},
  });

  Map<String, dynamic> toJson() {
    return {
      'event_type': eventType.toBackendString(),
      'idempotency_key': idempotencyKey,
      if (deviceReportedAt != null)
        'device_reported_at': deviceReportedAt!.toUtc().toIso8601String(),
      if (employeeId != null) 'employee_id': employeeId,
      if (locationId != null) 'location_id': locationId,
      if (latitude != null) 'latitude': latitude,
      if (longitude != null) 'longitude': longitude,
      if (accuracyMeters != null) 'accuracy_meters': accuracyMeters,
      if (wifiBssid != null) 'wifi_bssid': wifiBssid,
      if (wifiSsid != null) 'wifi_ssid': wifiSsid,
      if (wifiSignalStatus != null) 'wifi_signal_status': wifiSignalStatus,
      if (deviceId != null) 'device_id': deviceId,
      if (isMockLocation != null) 'is_mock_location': isMockLocation,
      if (locationCapturedAt != null)
        'location_captured_at': locationCapturedAt!.toUtc().toIso8601String(),
      'metadata': metadata,
    };
  }
}
