import 'dart:io' show Platform;
import 'package:network_info_plus/network_info_plus.dart';
import '../../domain/entities/wifi_evidence.dart';
import 'location_service.dart';

/// Abstract service contract for querying hardware and OS-level Wi-Fi connection telemetry.
abstract class WifiService {
  /// Queries the currently connected Wi-Fi access point and returns structured evidence.
  Future<WifiEvidence> getConnectedWifiEvidence();
}

/// Production implementation of [WifiService] backed by `network_info_plus` and OS permission checks.
class NetworkInfoWifiService implements WifiService {
  final NetworkInfo _networkInfo;
  final LocationService _locationService;
  final String Function() _platformResolver;

  NetworkInfoWifiService({
    NetworkInfo? networkInfo,
    LocationService locationService = const GeolocatorLocationService(),
    String Function()? platformResolver,
  })  : _networkInfo = networkInfo ?? NetworkInfo(),
        _locationService = locationService,
        _platformResolver = platformResolver ?? _defaultPlatformResolver;

  static String _defaultPlatformResolver() {
    try {
      return Platform.operatingSystem;
    } catch (_) {
      return 'unknown';
    }
  }

  @override
  Future<WifiEvidence> getConnectedWifiEvidence() async {
    final platform = _platformResolver();
    final now = DateTime.now().toUtc();

    // 1. Platform-Specific Pre-requisite Checks
    if (platform == 'android') {
      // Android 8+ mandates that Location Services (GPS) are toggled ON to read BSSID
      try {
        final serviceEnabled =
            await _locationService.isLocationServiceEnabled();
        if (!serviceEnabled) {
          return WifiEvidence(
            signalStatus: WifiSignalStatus.unavailable,
            deviceReportedAt: now,
            platform: platform,
            errorMessage:
                'Location services must be enabled in device settings to detect connected workplace Wi-Fi.',
          );
        }

        final perm = await _locationService.checkPermissionStatus();
        if (perm == LocationPermissionStatus.denied ||
            perm == LocationPermissionStatus.permanentlyDenied) {
          return WifiEvidence(
            signalStatus: WifiSignalStatus.permissionDenied,
            deviceReportedAt: now,
            platform: platform,
            errorMessage:
                'Location permission is required to identify the workplace Wi-Fi network.',
          );
        }
      } catch (e) {
        // Location check exception - proceed to network info with caution
      }
    } else if (platform == 'ios') {
      // iOS requires location permission to read Wi-Fi info via CNCopyCurrentNetworkInfo
      try {
        final perm = await _locationService.checkPermissionStatus();
        if (perm == LocationPermissionStatus.denied ||
            perm == LocationPermissionStatus.permanentlyDenied) {
          return WifiEvidence(
            signalStatus: WifiSignalStatus.permissionDenied,
            deviceReportedAt: now,
            platform: platform,
            errorMessage:
                'Location permission is required on iOS to access connected Wi-Fi information.',
          );
        }
      } catch (_) {}
    } else if (platform != 'ios' && platform != 'android') {
      return WifiEvidence(
        signalStatus: WifiSignalStatus.unsupported,
        deviceReportedAt: now,
        platform: platform,
        errorMessage:
            'Workplace Wi-Fi verification is not supported on $platform.',
      );
    }

    // 2. Query hardware / OS for currently connected network
    String? rawBssid;
    String? rawSsid;

    try {
      rawBssid = await _networkInfo.getWifiBSSID();
    } catch (e) {
      return WifiEvidence(
        signalStatus: WifiSignalStatus.unavailable,
        deviceReportedAt: now,
        platform: platform,
        errorMessage: 'Unable to query connected Wi-Fi BSSID: $e',
      );
    }

    try {
      rawSsid = await _networkInfo.getWifiName();
    } catch (_) {
      // SSID is optional / display only
    }

    // 3. Normalize and sanitize BSSID and SSID
    final normalizedBssid = WifiEvidence.normalizeBssid(rawBssid);
    String? cleanSsid;
    if (rawSsid != null) {
      cleanSsid = rawSsid.replaceAll('"', '').trim();
      if (cleanSsid.isEmpty || cleanSsid == '<unknown ssid>') {
        cleanSsid = null;
      }
    }

    // 4. Classify outcome
    if (normalizedBssid == null) {
      if (platform == 'ios') {
        // On iOS without Access Wi-Fi Information entitlement or on Simulator, BSSID is nil
        return WifiEvidence(
          signalStatus: WifiSignalStatus.unsupported,
          deviceReportedAt: now,
          platform: platform,
          errorMessage:
              'Connected Wi-Fi BSSID is unavailable on this iOS build or device.',
        );
      }
      return WifiEvidence(
        signalStatus: WifiSignalStatus.unavailable,
        deviceReportedAt: now,
        platform: platform,
        errorMessage: 'Device is not connected to a recognized Wi-Fi network.',
      );
    }

    return WifiEvidence(
      bssid: normalizedBssid,
      ssid: cleanSsid,
      signalStatus: WifiSignalStatus.available,
      deviceReportedAt: now,
      platform: platform,
    );
  }
}
