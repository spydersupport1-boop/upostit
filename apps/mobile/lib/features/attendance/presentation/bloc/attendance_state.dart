import 'package:equatable/equatable.dart';
import '../../data/services/location_service.dart';
import '../../domain/entities/attendance_dashboard.dart';
import '../../domain/entities/attendance_event.dart';
import '../../domain/entities/attendance_status.dart';
import '../../domain/entities/punch_result.dart';
import '../../domain/entities/wifi_evidence.dart';
import '../../domain/entities/wifi_verification_result.dart';

abstract class AttendanceState extends Equatable {
  const AttendanceState();

  @override
  List<Object?> get props => [];
}

/// Initial state before any dashboard fetch has commenced.
class AttendanceInitial extends AttendanceState {
  const AttendanceInitial();
}

/// State while fetching the dashboard initially.
class AttendanceLoading extends AttendanceState {
  const AttendanceLoading();
}

/// State representing an active, server-synchronized attendance dashboard.
class AttendanceLoaded extends AttendanceState {
  final AttendanceDashboard dashboard;
  final bool isSubmittingPunch;
  final AttendanceEventType? inFlightEventType;
  final String? inFlightIdempotencyKey;
  final LocationReading? inFlightLocationReading;
  final WifiEvidence? inFlightWifiEvidence;
  final PunchResult? lastPunchResult;
  final String? errorMessage;
  final bool isRetriable;
  final String? successNotice;
  final String? pendingReviewNotice;
  final String? offlineNotice;
  final String? locationStatusMessage;
  final LocationReading? lastLocationReading;
  final double? advisoryDistanceMeters;
  final bool? isInsideGeofence;
  final bool isLocationPermissionDenied;
  final bool isLocationServiceDisabled;
  final WifiEvidence? lastWifiEvidence;
  final WifiVerificationResult? lastWifiVerificationResult;
  final String? wifiStatusMessage;
  final bool isWifiProbing;
  final bool isWifiPermissionDenied;

  const AttendanceLoaded({
    required this.dashboard,
    this.isSubmittingPunch = false,
    this.inFlightEventType,
    this.inFlightIdempotencyKey,
    this.inFlightLocationReading,
    this.inFlightWifiEvidence,
    this.lastPunchResult,
    this.errorMessage,
    this.isRetriable = false,
    this.successNotice,
    this.pendingReviewNotice,
    this.offlineNotice,
    this.locationStatusMessage,
    this.lastLocationReading,
    this.advisoryDistanceMeters,
    this.isInsideGeofence,
    this.isLocationPermissionDenied = false,
    this.isLocationServiceDisabled = false,
    this.lastWifiEvidence,
    this.lastWifiVerificationResult,
    this.wifiStatusMessage,
    this.isWifiProbing = false,
    this.isWifiPermissionDenied = false,
  });

  AttendanceStatus get status => dashboard.status;
  Duration get workingDuration => dashboard.workingDuration;
  Duration get breakDuration => dashboard.breakDuration;

  AttendanceLoaded copyWith({
    AttendanceDashboard? dashboard,
    bool? isSubmittingPunch,
    AttendanceEventType? inFlightEventType,
    String? inFlightIdempotencyKey,
    LocationReading? inFlightLocationReading,
    WifiEvidence? inFlightWifiEvidence,
    PunchResult? lastPunchResult,
    String? errorMessage,
    bool? isRetriable,
    String? successNotice,
    String? pendingReviewNotice,
    String? offlineNotice,
    String? locationStatusMessage,
    LocationReading? lastLocationReading,
    double? advisoryDistanceMeters,
    bool? isInsideGeofence,
    bool? isLocationPermissionDenied,
    bool? isLocationServiceDisabled,
    WifiEvidence? lastWifiEvidence,
    WifiVerificationResult? lastWifiVerificationResult,
    String? wifiStatusMessage,
    bool? isWifiProbing,
    bool? isWifiPermissionDenied,
    bool clearError = false,
    bool clearNotices = false,
    bool clearLocationStatus = false,
    bool clearWifiStatus = false,
    bool clearInFlight = false,
  }) {
    return AttendanceLoaded(
      dashboard: dashboard ?? this.dashboard,
      isSubmittingPunch: isSubmittingPunch ?? this.isSubmittingPunch,
      inFlightEventType:
          clearInFlight ? null : (inFlightEventType ?? this.inFlightEventType),
      inFlightIdempotencyKey: clearInFlight
          ? null
          : (inFlightIdempotencyKey ?? this.inFlightIdempotencyKey),
      inFlightLocationReading: clearInFlight
          ? null
          : (inFlightLocationReading ?? this.inFlightLocationReading),
      inFlightWifiEvidence: clearInFlight
          ? null
          : (inFlightWifiEvidence ?? this.inFlightWifiEvidence),
      lastPunchResult: lastPunchResult ?? this.lastPunchResult,
      errorMessage: clearError ? null : (errorMessage ?? this.errorMessage),
      isRetriable: clearError ? false : (isRetriable ?? this.isRetriable),
      successNotice:
          clearNotices ? null : (successNotice ?? this.successNotice),
      pendingReviewNotice: clearNotices
          ? null
          : (pendingReviewNotice ?? this.pendingReviewNotice),
      offlineNotice:
          clearNotices ? null : (offlineNotice ?? this.offlineNotice),
      locationStatusMessage: clearLocationStatus
          ? null
          : (locationStatusMessage ?? this.locationStatusMessage),
      lastLocationReading: lastLocationReading ?? this.lastLocationReading,
      advisoryDistanceMeters:
          advisoryDistanceMeters ?? this.advisoryDistanceMeters,
      isInsideGeofence: isInsideGeofence ?? this.isInsideGeofence,
      isLocationPermissionDenied:
          isLocationPermissionDenied ?? this.isLocationPermissionDenied,
      isLocationServiceDisabled:
          isLocationServiceDisabled ?? this.isLocationServiceDisabled,
      lastWifiEvidence: lastWifiEvidence ?? this.lastWifiEvidence,
      lastWifiVerificationResult:
          lastWifiVerificationResult ?? this.lastWifiVerificationResult,
      wifiStatusMessage: clearWifiStatus
          ? null
          : (wifiStatusMessage ?? this.wifiStatusMessage),
      isWifiProbing: isWifiProbing ?? this.isWifiProbing,
      isWifiPermissionDenied:
          isWifiPermissionDenied ?? this.isWifiPermissionDenied,
    );
  }

  @override
  List<Object?> get props => [
        dashboard,
        isSubmittingPunch,
        inFlightEventType,
        inFlightIdempotencyKey,
        lastPunchResult,
        errorMessage,
        isRetriable,
        successNotice,
        pendingReviewNotice,
        offlineNotice,
        locationStatusMessage,
        lastLocationReading,
        advisoryDistanceMeters,
        isInsideGeofence,
        isLocationPermissionDenied,
        isLocationServiceDisabled,
        lastWifiEvidence,
        lastWifiVerificationResult,
        wifiStatusMessage,
        isWifiProbing,
        isWifiPermissionDenied,
      ];
}

/// State when the dashboard could not be loaded at all (e.g. initial offline load).
class AttendanceLoadFailure extends AttendanceState {
  final String message;
  final bool isNetworkError;

  const AttendanceLoadFailure({
    required this.message,
    this.isNetworkError = false,
  });

  @override
  List<Object?> get props => [message, isNetworkError];
}
