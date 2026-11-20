import 'dart:convert';
import '../../../attendance/domain/entities/attendance_event.dart';
import '../../domain/entities/offline_sequence_conflict_bundle.dart';

/// Request DTO for POST /api/v1/attendance/offline-conflicts/submit.
class OfflineConflictBundleSubmitRequestModel {
  final String bundleId;
  final String? sessionId;
  final String? employeeNotes;
  final Map<String, dynamic> primaryRejectedEvent;
  final List<Map<String, dynamic>> dependentEvents;

  OfflineConflictBundleSubmitRequestModel({
    required this.bundleId,
    this.sessionId,
    this.employeeNotes,
    required this.primaryRejectedEvent,
    this.dependentEvents = const [],
  });

  factory OfflineConflictBundleSubmitRequestModel.fromBundle(
    OfflineSequenceConflictBundle bundle, {
    String? notes,
  }) {
    final prim = bundle.primaryRejectedEvent;
    final Map<String, dynamic> primMeta = _parseMetadata(prim.metadataJson);

    final primaryMap = <String, dynamic>{
      'local_id': prim.localId,
      'idempotency_key': prim.idempotencyKey,
      'event_type': prim.eventType.toBackendString(),
      'device_reported_at': prim.deviceReportedAt.toUtc().toIso8601String(),
      'latitude': prim.latitude,
      'longitude': prim.longitude,
      'accuracy_meters': prim.accuracyMeters,
      'device_id_hash': primMeta['device_id_hash'] ?? prim.deviceId,
      'device_model': primMeta['device_model'],
      'os_version': primMeta['os_version'],
      'is_mock_location': primMeta['is_mock_location'] == true,
      'server_rejection_code': prim.lastErrorStatusCode,
      'server_rejection_reason': prim.lastErrorMessage,
    };

    final dependentList = bundle.dependentEvents.map((dep) {
      final Map<String, dynamic> depMeta = _parseMetadata(dep.metadataJson);
      return <String, dynamic>{
        'local_id': dep.localId,
        'idempotency_key': dep.idempotencyKey,
        'event_type': dep.eventType.toBackendString(),
        'device_reported_at': dep.deviceReportedAt.toUtc().toIso8601String(),
        'latitude': dep.latitude,
        'longitude': dep.longitude,
        'accuracy_meters': dep.accuracyMeters,
        'device_id_hash': depMeta['device_id_hash'] ?? dep.deviceId,
        'device_model': depMeta['device_model'],
        'os_version': depMeta['os_version'],
        'is_mock_location': depMeta['is_mock_location'] == true,
      };
    }).toList();

    return OfflineConflictBundleSubmitRequestModel(
      bundleId: bundle.bundleId,
      sessionId: bundle.sessionId,
      employeeNotes: notes ?? bundle.employeeNotes,
      primaryRejectedEvent: primaryMap,
      dependentEvents: dependentList,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'bundle_id': bundleId,
      if (sessionId != null) 'session_id': sessionId,
      if (employeeNotes != null && employeeNotes!.trim().isNotEmpty)
        'employee_notes': employeeNotes!.trim(),
      'primary_rejected_event': primaryRejectedEvent,
      'dependent_events': dependentEvents,
    };
  }

  static Map<String, dynamic> _parseMetadata(String jsonStr) {
    if (jsonStr.isEmpty || jsonStr == '{}') return {};
    try {
      final decoded = jsonDecode(jsonStr);
      if (decoded is Map<String, dynamic>) return decoded;
    } catch (_) {}
    return {};
  }
}
