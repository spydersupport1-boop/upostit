import 'package:equatable/equatable.dart';

/// Telemetry status of client Wi-Fi capabilities and connectivity.
enum WifiSignalStatus {
  available,
  unavailable,
  unsupported,
  permissionDenied,
  error;

  String toBackendString() {
    switch (this) {
      case WifiSignalStatus.available:
        return 'AVAILABLE';
      case WifiSignalStatus.unavailable:
        return 'UNAVAILABLE';
      case WifiSignalStatus.unsupported:
        return 'UNSUPPORTED';
      case WifiSignalStatus.permissionDenied:
        return 'PERMISSION_DENIED';
      case WifiSignalStatus.error:
        // Backend maps errors to UNAVAILABLE
        return 'UNAVAILABLE';
    }
  }

  static WifiSignalStatus fromBackendString(String? val) {
    switch (val?.toUpperCase()) {
      case 'AVAILABLE':
        return WifiSignalStatus.available;
      case 'UNAVAILABLE':
        return WifiSignalStatus.unavailable;
      case 'UNSUPPORTED':
        return WifiSignalStatus.unsupported;
      case 'PERMISSION_DENIED':
        return WifiSignalStatus.permissionDenied;
      default:
        return WifiSignalStatus.unavailable;
    }
  }
}

/// Structured hardware Wi-Fi telemetry evidence captured at the moment of attendance.
class WifiEvidence extends Equatable {
  final String? bssid;
  final String? ssid;
  final WifiSignalStatus signalStatus;
  final DateTime deviceReportedAt;
  final String platform;
  final String? errorMessage;

  static final RegExp _bssidPattern =
      RegExp(r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$');

  const WifiEvidence({
    this.bssid,
    this.ssid,
    required this.signalStatus,
    required this.deviceReportedAt,
    required this.platform,
    this.errorMessage,
  });

  /// Factory creating an empty or disconnected Wi-Fi evidence record.
  factory WifiEvidence.unavailable({
    required String platform,
    String? errorMessage,
  }) {
    return WifiEvidence(
      signalStatus: WifiSignalStatus.unavailable,
      deviceReportedAt: DateTime.now().toUtc(),
      platform: platform,
      errorMessage: errorMessage,
    );
  }

  /// Factory creating an unsupported platform evidence record.
  factory WifiEvidence.unsupported({
    required String platform,
    String? errorMessage,
  }) {
    return WifiEvidence(
      signalStatus: WifiSignalStatus.unsupported,
      deviceReportedAt: DateTime.now().toUtc(),
      platform: platform,
      errorMessage: errorMessage,
    );
  }

  /// Factory creating a permission denied evidence record.
  factory WifiEvidence.permissionDenied({
    required String platform,
    String? errorMessage,
  }) {
    return WifiEvidence(
      signalStatus: WifiSignalStatus.permissionDenied,
      deviceReportedAt: DateTime.now().toUtc(),
      platform: platform,
      errorMessage: errorMessage,
    );
  }

  /// Normalizes any raw BSSID string to uppercase colon-separated format (XX:XX:XX:XX:XX:XX).
  static String? normalizeBssid(String? raw) {
    if (raw == null) return null;
    final clean = raw.trim().toUpperCase().replaceAll('-', ':');
    if (!_bssidPattern.hasMatch(clean)) {
      return null;
    }
    // Filter out Android/dummy placeholder MAC addresses
    if (clean == '02:00:00:00:00:00' || clean == '00:00:00:00:00:00') {
      return null;
    }
    return clean;
  }

  /// Whether valid positive Wi-Fi presence evidence was acquired.
  bool get isAvailable =>
      signalStatus == WifiSignalStatus.available &&
      bssid != null &&
      bssid!.isNotEmpty;

  /// Checks whether this Wi-Fi telemetry reading exceeds allowable age.
  bool isStale({int maxAgeSeconds = 30}) {
    final now = DateTime.now().toUtc();
    final age = now.difference(deviceReportedAt.toUtc()).inSeconds.abs();
    return age > maxAgeSeconds;
  }

  /// Sanitized representation of BSSID for employee diagnostics without leaking raw MAC.
  String get maskedBssid {
    if (bssid == null || bssid!.length < 17) return 'N/A';
    return '${bssid!.substring(0, 5)}:***:${bssid!.substring(12)}';
  }

  @override
  List<Object?> get props => [
        bssid,
        ssid,
        signalStatus,
        deviceReportedAt,
        platform,
        errorMessage,
      ];
}
