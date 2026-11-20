import 'package:equatable/equatable.dart';
import '../../../attendance/domain/entities/attendance_event.dart';
import 'sync_status.dart';

/// Represents an offline-persisted attendance punch queued for synchronization.
class LocalQueueItem extends Equatable {
  final String localId;
  final String idempotencyKey;
  final String? sessionId;
  final String tenantId;
  final String employeeId;
  final String userId;
  final AttendanceEventType eventType;
  final DateTime deviceReportedAt;
  final int timezoneOffsetMinutes;
  final int monotonicBootTimeMs;
  final String bootSessionId;
  final bool isRebootDetected;

  final String? locationId;
  final double? latitude;
  final double? longitude;
  final double? accuracyMeters;
  final String? wifiBssid;
  final String? wifiSsid;
  final String wifiSignalStatus;
  final String? encryptedPayloadBlob;

  final int appliedPolicyVersion;
  final String appliedPolicyMode;
  final String? deviceId;
  final String metadataJson;

  final int sequenceNumber;
  final SyncStatus syncStatus;
  final String? conflictBundleId;
  final int retryCount;
  final DateTime? lastAttemptedAt;
  final String? lastErrorMessage;
  final int? lastErrorStatusCode;
  final String? serverEventId;

  final DateTime createdAt;
  final DateTime updatedAt;

  const LocalQueueItem({
    required this.localId,
    required this.idempotencyKey,
    this.sessionId,
    required this.tenantId,
    required this.employeeId,
    required this.userId,
    required this.eventType,
    required this.deviceReportedAt,
    required this.timezoneOffsetMinutes,
    required this.monotonicBootTimeMs,
    required this.bootSessionId,
    this.isRebootDetected = false,
    this.locationId,
    this.latitude,
    this.longitude,
    this.accuracyMeters,
    this.wifiBssid,
    this.wifiSsid,
    this.wifiSignalStatus = 'AVAILABLE',
    this.encryptedPayloadBlob,
    required this.appliedPolicyVersion,
    required this.appliedPolicyMode,
    this.deviceId,
    this.metadataJson = '{}',
    required this.sequenceNumber,
    this.syncStatus = SyncStatus.pendingSync,
    this.conflictBundleId,
    this.retryCount = 0,
    this.lastAttemptedAt,
    this.lastErrorMessage,
    this.lastErrorStatusCode,
    this.serverEventId,
    required this.createdAt,
    required this.updatedAt,
  });

  LocalQueueItem copyWith({
    String? localId,
    String? idempotencyKey,
    String? sessionId,
    String? tenantId,
    String? employeeId,
    String? userId,
    AttendanceEventType? eventType,
    DateTime? deviceReportedAt,
    int? timezoneOffsetMinutes,
    int? monotonicBootTimeMs,
    String? bootSessionId,
    bool? isRebootDetected,
    String? locationId,
    double? latitude,
    double? longitude,
    double? accuracyMeters,
    String? wifiBssid,
    String? wifiSsid,
    String? wifiSignalStatus,
    String? encryptedPayloadBlob,
    int? appliedPolicyVersion,
    String? appliedPolicyMode,
    String? deviceId,
    String? metadataJson,
    int? sequenceNumber,
    SyncStatus? syncStatus,
    String? conflictBundleId,
    int? retryCount,
    DateTime? lastAttemptedAt,
    String? lastErrorMessage,
    int? lastErrorStatusCode,
    String? serverEventId,
    DateTime? createdAt,
    DateTime? updatedAt,
  }) {
    return LocalQueueItem(
      localId: localId ?? this.localId,
      idempotencyKey: idempotencyKey ?? this.idempotencyKey,
      sessionId: sessionId ?? this.sessionId,
      tenantId: tenantId ?? this.tenantId,
      employeeId: employeeId ?? this.employeeId,
      userId: userId ?? this.userId,
      eventType: eventType ?? this.eventType,
      deviceReportedAt: deviceReportedAt ?? this.deviceReportedAt,
      timezoneOffsetMinutes:
          timezoneOffsetMinutes ?? this.timezoneOffsetMinutes,
      monotonicBootTimeMs: monotonicBootTimeMs ?? this.monotonicBootTimeMs,
      bootSessionId: bootSessionId ?? this.bootSessionId,
      isRebootDetected: isRebootDetected ?? this.isRebootDetected,
      locationId: locationId ?? this.locationId,
      latitude: latitude ?? this.latitude,
      longitude: longitude ?? this.longitude,
      accuracyMeters: accuracyMeters ?? this.accuracyMeters,
      wifiBssid: wifiBssid ?? this.wifiBssid,
      wifiSsid: wifiSsid ?? this.wifiSsid,
      wifiSignalStatus: wifiSignalStatus ?? this.wifiSignalStatus,
      encryptedPayloadBlob: encryptedPayloadBlob ?? this.encryptedPayloadBlob,
      appliedPolicyVersion: appliedPolicyVersion ?? this.appliedPolicyVersion,
      appliedPolicyMode: appliedPolicyMode ?? this.appliedPolicyMode,
      deviceId: deviceId ?? this.deviceId,
      metadataJson: metadataJson ?? this.metadataJson,
      sequenceNumber: sequenceNumber ?? this.sequenceNumber,
      syncStatus: syncStatus ?? this.syncStatus,
      conflictBundleId: conflictBundleId ?? this.conflictBundleId,
      retryCount: retryCount ?? this.retryCount,
      lastAttemptedAt: lastAttemptedAt ?? this.lastAttemptedAt,
      lastErrorMessage: lastErrorMessage ?? this.lastErrorMessage,
      lastErrorStatusCode: lastErrorStatusCode ?? this.lastErrorStatusCode,
      serverEventId: serverEventId ?? this.serverEventId,
      createdAt: createdAt ?? this.createdAt,
      updatedAt: updatedAt ?? this.updatedAt,
    );
  }

  @override
  List<Object?> get props => [
        localId,
        idempotencyKey,
        sessionId,
        tenantId,
        employeeId,
        userId,
        eventType,
        deviceReportedAt,
        timezoneOffsetMinutes,
        monotonicBootTimeMs,
        bootSessionId,
        isRebootDetected,
        locationId,
        latitude,
        longitude,
        accuracyMeters,
        wifiBssid,
        wifiSsid,
        wifiSignalStatus,
        encryptedPayloadBlob,
        appliedPolicyVersion,
        appliedPolicyMode,
        deviceId,
        metadataJson,
        sequenceNumber,
        syncStatus,
        conflictBundleId,
        retryCount,
        lastAttemptedAt,
        lastErrorMessage,
        lastErrorStatusCode,
        serverEventId,
        createdAt,
        updatedAt,
      ];
}
