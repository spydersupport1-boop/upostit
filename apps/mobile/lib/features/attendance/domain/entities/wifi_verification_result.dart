import 'package:equatable/equatable.dart';

/// Server-authoritative Wi-Fi match status classification.
enum WifiMatchStatus {
  matched,
  mismatched,
  unavailable,
  unsupported,
  stale,
  permissionDenied,
  unassigned,
  inactive,
  unknown;

  static WifiMatchStatus fromBackendString(String? val) {
    switch (val?.toUpperCase()) {
      case 'MATCHED':
        return WifiMatchStatus.matched;
      case 'MISMATCHED':
        return WifiMatchStatus.mismatched;
      case 'UNAVAILABLE':
        return WifiMatchStatus.unavailable;
      case 'UNSUPPORTED':
        return WifiMatchStatus.unsupported;
      case 'STALE':
        return WifiMatchStatus.stale;
      case 'PERMISSION_DENIED':
        return WifiMatchStatus.permissionDenied;
      case 'UNASSIGNED':
        return WifiMatchStatus.unassigned;
      case 'INACTIVE':
        return WifiMatchStatus.inactive;
      default:
        return WifiMatchStatus.unknown;
    }
  }

  String toDisplayString() {
    switch (this) {
      case WifiMatchStatus.matched:
        return 'Workplace Wi-Fi Verified';
      case WifiMatchStatus.mismatched:
        return 'Connected to Unrecognized Network';
      case WifiMatchStatus.unavailable:
        return 'Wi-Fi Unavailable or Disconnected';
      case WifiMatchStatus.unsupported:
        return 'Wi-Fi Verification Unsupported';
      case WifiMatchStatus.stale:
        return 'Stale Wi-Fi Telemetry';
      case WifiMatchStatus.permissionDenied:
        return 'Wi-Fi Permission Required';
      case WifiMatchStatus.unassigned:
        return 'Unassigned Workplace';
      case WifiMatchStatus.inactive:
        return 'Inactive Workplace';
      case WifiMatchStatus.unknown:
        return 'Unknown Wi-Fi Status';
    }
  }
}

/// Domain entity representing the server evaluation of an employee's Wi-Fi connection.
class WifiVerificationResult extends Equatable {
  final String locationId;
  final String locationName;
  final String locationCode;
  final String? reportedBssid;
  final String? reportedSsid;
  final WifiMatchStatus matchStatus;
  final bool isVerified;
  final String? matchedAccessPointName;
  final bool freshnessAcceptable;
  final String? applicableFallback;
  final String message;

  const WifiVerificationResult({
    required this.locationId,
    required this.locationName,
    required this.locationCode,
    this.reportedBssid,
    this.reportedSsid,
    required this.matchStatus,
    required this.isVerified,
    this.matchedAccessPointName,
    this.freshnessAcceptable = true,
    this.applicableFallback,
    required this.message,
  });

  @override
  List<Object?> get props => [
        locationId,
        locationName,
        locationCode,
        reportedBssid,
        reportedSsid,
        matchStatus,
        isVerified,
        matchedAccessPointName,
        freshnessAcceptable,
        applicableFallback,
        message,
      ];
}
