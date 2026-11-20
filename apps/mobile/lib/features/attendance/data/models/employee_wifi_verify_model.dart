import '../../domain/entities/wifi_verification_result.dart';

/// Request DTO for POST /api/v1/employees/me/workplaces/verify-wifi.
class EmployeeWifiVerifyRequestModel {
  final String locationId;
  final String? bssid;
  final String? ssid;
  final DateTime? deviceReportedAt;
  final String signalStatus;
  final String? platform;

  const EmployeeWifiVerifyRequestModel({
    required this.locationId,
    this.bssid,
    this.ssid,
    this.deviceReportedAt,
    this.signalStatus = 'AVAILABLE',
    this.platform,
  });

  Map<String, dynamic> toJson() {
    return {
      'location_id': locationId,
      if (bssid != null) 'bssid': bssid,
      if (ssid != null) 'ssid': ssid,
      if (deviceReportedAt != null)
        'device_reported_at': deviceReportedAt!.toUtc().toIso8601String(),
      'signal_status': signalStatus,
      if (platform != null) 'platform': platform,
    };
  }
}

/// Response DTO for POST /api/v1/employees/me/workplaces/verify-wifi.
class EmployeeWifiVerifyResponseModel extends WifiVerificationResult {
  const EmployeeWifiVerifyResponseModel({
    required super.locationId,
    required super.locationName,
    required super.locationCode,
    super.reportedBssid,
    super.reportedSsid,
    required super.matchStatus,
    required super.isVerified,
    super.matchedAccessPointName,
    super.freshnessAcceptable,
    super.applicableFallback,
    required super.message,
  });

  factory EmployeeWifiVerifyResponseModel.fromJson(Map<String, dynamic> json) {
    return EmployeeWifiVerifyResponseModel(
      locationId: (json['location_id'] ?? '').toString(),
      locationName: (json['location_name'] ?? '').toString(),
      locationCode: (json['location_code'] ?? '').toString(),
      reportedBssid: json['reported_bssid'] as String?,
      reportedSsid: json['reported_ssid'] as String?,
      matchStatus:
          WifiMatchStatus.fromBackendString(json['match_status'] as String?),
      isVerified: (json['is_verified'] as bool?) ?? false,
      matchedAccessPointName: json['matched_access_point_name'] as String?,
      freshnessAcceptable: (json['freshness_acceptable'] as bool?) ?? true,
      applicableFallback: json['applicable_fallback'] as String?,
      message: (json['message'] ?? '').toString(),
    );
  }
}
