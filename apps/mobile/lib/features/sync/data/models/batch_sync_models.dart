/// Batch sync request and response models for Phase 11.2 & 11.4 Batch Sync Protocol.
library batch_sync_models;

class BatchSyncPunchItemModel {
  final String localId;
  final String idempotencyKey;
  final String eventType;
  final String deviceReportedAt;
  final int? sequenceNumber;
  final String? sessionId;
  final String? locationId;
  final double? latitude;
  final double? longitude;
  final double? accuracyMeters;
  final String? wifiBssid;
  final String? wifiSsid;
  final String wifiSignalStatus;
  final String? deviceId;
  final bool? isMockLocation;
  final String? locationCapturedAt;
  final Map<String, dynamic> metadata;

  const BatchSyncPunchItemModel({
    required this.localId,
    required this.idempotencyKey,
    required this.eventType,
    required this.deviceReportedAt,
    this.sequenceNumber,
    this.sessionId,
    this.locationId,
    this.latitude,
    this.longitude,
    this.accuracyMeters,
    this.wifiBssid,
    this.wifiSsid,
    this.wifiSignalStatus = 'AVAILABLE',
    this.deviceId,
    this.isMockLocation = false,
    this.locationCapturedAt,
    this.metadata = const {},
  });

  Map<String, dynamic> toJson() {
    return {
      'local_id': localId,
      'idempotency_key': idempotencyKey,
      'event_type': eventType,
      'device_reported_at': deviceReportedAt,
      if (sequenceNumber != null) 'sequence_number': sequenceNumber,
      if (sessionId != null) 'session_id': sessionId,
      if (locationId != null) 'location_id': locationId,
      if (latitude != null) 'latitude': latitude,
      if (longitude != null) 'longitude': longitude,
      if (accuracyMeters != null) 'accuracy_meters': accuracyMeters,
      if (wifiBssid != null) 'wifi_bssid': wifiBssid,
      if (wifiSsid != null) 'wifi_ssid': wifiSsid,
      'wifi_signal_status': wifiSignalStatus,
      if (deviceId != null) 'device_id': deviceId,
      'is_mock_location': isMockLocation ?? false,
      if (locationCapturedAt != null) 'location_captured_at': locationCapturedAt,
      'metadata': metadata,
    };
  }

  factory BatchSyncPunchItemModel.fromJson(Map<String, dynamic> json) {
    return BatchSyncPunchItemModel(
      localId: json['local_id'] as String,
      idempotencyKey: json['idempotency_key'] as String,
      eventType: json['event_type'] as String,
      deviceReportedAt: json['device_reported_at'] as String,
      sequenceNumber: json['sequence_number'] as int?,
      sessionId: json['session_id'] as String?,
      locationId: json['location_id'] as String?,
      latitude: (json['latitude'] as num?)?.toDouble(),
      longitude: (json['longitude'] as num?)?.toDouble(),
      accuracyMeters: (json['accuracy_meters'] as num?)?.toDouble(),
      wifiBssid: json['wifi_bssid'] as String?,
      wifiSsid: json['wifi_ssid'] as String?,
      wifiSignalStatus: json['wifi_signal_status'] as String? ?? 'AVAILABLE',
      deviceId: json['device_id'] as String?,
      isMockLocation: json['is_mock_location'] as bool? ?? false,
      locationCapturedAt: json['location_captured_at'] as String?,
      metadata: (json['metadata'] as Map<String, dynamic>?) ?? const {},
    );
  }
}

class AttendanceBatchSyncRequestModel {
  final String? batchId;
  final String? deviceId;
  final String? employeeId;
  final List<BatchSyncPunchItemModel> items;

  const AttendanceBatchSyncRequestModel({
    this.batchId,
    this.deviceId,
    this.employeeId,
    required this.items,
  });

  Map<String, dynamic> toJson() {
    return {
      if (batchId != null) 'batch_id': batchId,
      if (deviceId != null) 'device_id': deviceId,
      if (employeeId != null) 'employee_id': employeeId,
      'items': items.map((e) => e.toJson()).toList(),
    };
  }
}

class BatchSyncReceiptItemModel {
  final String localId;
  final String idempotencyKey;
  final String status;
  final String eventType;
  final String? serverEventId;
  final String? effectiveAt;
  final String? reviewStatus;
  final String? errorCode;
  final String? errorMessage;
  final bool idempotentReplay;

  const BatchSyncReceiptItemModel({
    required this.localId,
    required this.idempotencyKey,
    required this.status,
    required this.eventType,
    this.serverEventId,
    this.effectiveAt,
    this.reviewStatus,
    this.errorCode,
    this.errorMessage,
    this.idempotentReplay = false,
  });

  bool get isAccepted => status == 'ACCEPTED';
  bool get isDuplicate => status == 'DUPLICATE';
  bool get isRequiresReview => status == 'REQUIRES_REVIEW';
  bool get isRejected => status == 'REJECTED';
  bool get isRetryable => status == 'RETRYABLE';

  factory BatchSyncReceiptItemModel.fromJson(Map<String, dynamic> json) {
    return BatchSyncReceiptItemModel(
      localId: json['local_id'] as String? ?? '',
      idempotencyKey: json['idempotency_key'] as String? ?? '',
      status: (json['status'] as String? ?? 'REJECTED').toUpperCase(),
      eventType: json['event_type'] as String? ?? 'CHECK_IN',
      serverEventId: json['server_event_id'] as String?,
      effectiveAt: json['effective_at'] as String?,
      reviewStatus: json['review_status'] as String?,
      errorCode: json['error_code'] as String?,
      errorMessage: json['error_message'] as String?,
      idempotentReplay: json['idempotent_replay'] as bool? ?? false,
    );
  }
}

class AttendanceBatchSyncResponseModel {
  final String? batchId;
  final int totalItems;
  final int acceptedCount;
  final int duplicateCount;
  final int requiresReviewCount;
  final int conflictCount;
  final int rejectedCount;
  final int retryableCount;
  final List<BatchSyncReceiptItemModel> receipts;

  const AttendanceBatchSyncResponseModel({
    this.batchId,
    required this.totalItems,
    required this.acceptedCount,
    required this.duplicateCount,
    required this.requiresReviewCount,
    this.conflictCount = 0,
    required this.rejectedCount,
    this.retryableCount = 0,
    required this.receipts,
  });

  factory AttendanceBatchSyncResponseModel.fromJson(Map<String, dynamic> json) {
    final rawReceipts = (json['receipts'] as List<dynamic>?) ??
        (json['items'] as List<dynamic>?) ??
        const [];
    return AttendanceBatchSyncResponseModel(
      batchId: json['batch_id'] as String?,
      totalItems: json['total_items'] as int? ?? 0,
      acceptedCount: json['accepted_count'] as int? ?? 0,
      duplicateCount: json['duplicate_count'] as int? ?? 0,
      requiresReviewCount: json['requires_review_count'] as int? ?? 0,
      conflictCount: json['conflict_count'] as int? ?? 0,
      rejectedCount: json['rejected_count'] as int? ?? 0,
      retryableCount: json['retryable_count'] as int? ?? 0,
      receipts: rawReceipts
          .map((e) => BatchSyncReceiptItemModel.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}

