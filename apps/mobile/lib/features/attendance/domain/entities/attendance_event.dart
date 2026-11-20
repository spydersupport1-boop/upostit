import 'package:equatable/equatable.dart';

/// The four atomic attendance presence actions supported by UPOSTIT.
enum AttendanceEventType {
  checkIn,
  checkOut,
  breakStart,
  breakEnd,
}

extension AttendanceEventTypeX on AttendanceEventType {
  String toBackendString() {
    switch (this) {
      case AttendanceEventType.checkIn:
        return 'CHECK_IN';
      case AttendanceEventType.checkOut:
        return 'CHECK_OUT';
      case AttendanceEventType.breakStart:
        return 'BREAK_START';
      case AttendanceEventType.breakEnd:
        return 'BREAK_END';
    }
  }

  static AttendanceEventType fromBackendString(String val) {
    switch (val.toUpperCase()) {
      case 'CHECK_IN':
        return AttendanceEventType.checkIn;
      case 'CHECK_OUT':
        return AttendanceEventType.checkOut;
      case 'BREAK_START':
        return AttendanceEventType.breakStart;
      case 'BREAK_END':
        return AttendanceEventType.breakEnd;
      default:
        throw ArgumentError('Unknown attendance event type: $val');
    }
  }

  String get displayName {
    switch (this) {
      case AttendanceEventType.checkIn:
        return 'Check In';
      case AttendanceEventType.checkOut:
        return 'Check Out';
      case AttendanceEventType.breakStart:
        return 'Start Break';
      case AttendanceEventType.breakEnd:
        return 'End Break';
    }
  }
}

/// Domain entity representing an immutable attendance event in the UPOSTIT ledger.
class AttendanceEvent extends Equatable {
  final String id;
  final String tenantId;
  final String employeeId;
  final AttendanceEventType eventType;
  final String eventCategory;
  final DateTime serverReceivedAt;
  final DateTime? deviceReportedAt;
  final DateTime effectiveAt;
  final double? clockDriftSeconds;
  final String source;
  final String? deviceId;
  final String timestampVerificationStatus;
  final String reviewStatus;
  final String idempotencyKey;
  final String? locationId;
  final Map<String, dynamic> metadata;
  final DateTime createdAt;

  const AttendanceEvent({
    required this.id,
    required this.tenantId,
    required this.employeeId,
    required this.eventType,
    required this.eventCategory,
    required this.serverReceivedAt,
    this.deviceReportedAt,
    required this.effectiveAt,
    this.clockDriftSeconds,
    required this.source,
    this.deviceId,
    required this.timestampVerificationStatus,
    required this.reviewStatus,
    required this.idempotencyKey,
    this.locationId,
    this.metadata = const {},
    required this.createdAt,
  });

  bool get isPendingReview => reviewStatus == 'PENDING_REVIEW';
  bool get isRejected => reviewStatus == 'REJECTED';
  bool get isApproved =>
      reviewStatus == 'APPROVED' || reviewStatus == 'NOT_REQUIRED';

  @override
  List<Object?> get props => [
        id,
        tenantId,
        employeeId,
        eventType,
        eventCategory,
        serverReceivedAt,
        deviceReportedAt,
        effectiveAt,
        clockDriftSeconds,
        source,
        deviceId,
        timestampVerificationStatus,
        reviewStatus,
        idempotencyKey,
        locationId,
        metadata,
        createdAt,
      ];
}
