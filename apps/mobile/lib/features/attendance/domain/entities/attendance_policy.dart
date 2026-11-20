import 'package:equatable/equatable.dart';

/// Supported operational attendance policy modes.
enum PolicyVerificationMode {
  manual,
  gpsOnly,
  wifiOnly,
  biometricOnly,
  faceRecognition,
  combined,
  unknown,
}

/// Domain entity representing the active company attendance policy.
class AttendancePolicy extends Equatable {
  final String tenantId;
  final int version;
  final String defaultMode;
  final List<String> allowedMethods;
  final List<String> requiredMethods;
  final String combinationRule;
  final bool requiresGps;
  final bool requiresWifi;
  final bool requiresBiometric;
  final bool requiresFace;
  final int maxAccuracyMeters;
  final int maxLocationAgeSeconds;
  final int maxWifiAgeSeconds;
  final String wifiFallbackAction;
  final List<String> allowedFallbackMethods;

  const AttendancePolicy({
    required this.tenantId,
    required this.version,
    required this.defaultMode,
    required this.allowedMethods,
    required this.requiredMethods,
    required this.combinationRule,
    required this.requiresGps,
    this.requiresWifi = false,
    this.requiresBiometric = false,
    this.requiresFace = false,
    this.maxAccuracyMeters = 100,
    this.maxLocationAgeSeconds = 30,
    this.maxWifiAgeSeconds = 30,
    this.wifiFallbackAction = 'REJECT',
    this.allowedFallbackMethods = const [],
  });

  /// Factory for a default MANUAL policy when not configured or offline.
  factory AttendancePolicy.defaultManual({String tenantId = ''}) {
    return AttendancePolicy(
      tenantId: tenantId,
      version: 1,
      defaultMode: 'MANUAL',
      allowedMethods: const ['MANUAL'],
      requiredMethods: const ['MANUAL'],
      combinationRule: 'OR',
      requiresGps: false,
      requiresWifi: false,
      maxAccuracyMeters: 100,
      maxLocationAgeSeconds: 30,
      maxWifiAgeSeconds: 30,
      wifiFallbackAction: 'REJECT',
      allowedFallbackMethods: const [],
    );
  }

  PolicyVerificationMode get mode {
    switch (defaultMode) {
      case 'MANUAL':
        return PolicyVerificationMode.manual;
      case 'GPS_ONLY':
        return PolicyVerificationMode.gpsOnly;
      case 'WIFI_ONLY':
        return PolicyVerificationMode.wifiOnly;
      case 'BIOMETRIC_ONLY':
        return PolicyVerificationMode.biometricOnly;
      case 'FACE_RECOGNITION':
        return PolicyVerificationMode.faceRecognition;
      case 'COMBINED':
        return PolicyVerificationMode.combined;
      default:
        return PolicyVerificationMode.unknown;
    }
  }

  /// Whether this policy mode is supported in the current mobile client release.
  bool get isSupportedInThisRelease {
    return mode == PolicyVerificationMode.manual ||
        mode == PolicyVerificationMode.gpsOnly ||
        mode == PolicyVerificationMode.wifiOnly ||
        mode == PolicyVerificationMode.combined;
  }

  /// User-friendly explanation when a company policy cannot be served on this mobile version.
  String? get unsupportedMessage {
    switch (mode) {
      case PolicyVerificationMode.biometricOnly:
        return 'Dedicated biometric terminal attendance is not supported on mobile devices.';
      case PolicyVerificationMode.faceRecognition:
        return 'Facial recognition attendance is not yet supported in this mobile release.';
      case PolicyVerificationMode.unknown:
        return 'Attendance verification method "$defaultMode" is not supported.';
      default:
        return null;
    }
  }

  @override
  List<Object?> get props => [
        tenantId,
        version,
        defaultMode,
        allowedMethods,
        requiredMethods,
        combinationRule,
        requiresGps,
        requiresWifi,
        requiresBiometric,
        requiresFace,
        maxAccuracyMeters,
        maxLocationAgeSeconds,
        maxWifiAgeSeconds,
        wifiFallbackAction,
        allowedFallbackMethods,
      ];
}
