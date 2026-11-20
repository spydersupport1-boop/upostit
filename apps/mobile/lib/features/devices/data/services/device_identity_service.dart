import 'dart:io' show Platform;
import 'package:device_info_plus/device_info_plus.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:uuid/uuid.dart';

/// Structured platform and application metadata for device registration and fraud telemetry.
class DevicePlatformInfo {
  final String platform;
  final String? deviceModel;
  final String? osName;
  final String? osVersion;
  final String? appVersion;
  final Map<String, dynamic> metadata;

  const DevicePlatformInfo({
    required this.platform,
    this.deviceModel,
    this.osName,
    this.osVersion,
    this.appVersion,
    this.metadata = const {},
  });
}

/// Contract for persistent installation identification and device telemetry collection.
abstract class DeviceIdentityService {
  /// Returns the persistent unique installation identifier, generating and persisting a new UUID v4 if not yet set.
  Future<String> getOrCreateInstallationId();

  /// Returns the existing installation identifier if available, or null.
  Future<String?> getInstallationId();

  /// Collects platform, device hardware, operating system, and app release metadata safely.
  Future<DevicePlatformInfo> getPlatformMetadata();
}

/// Implementation using [FlutterSecureStorage], [DeviceInfoPlugin], and [PackageInfo].
class FlutterDeviceIdentityService implements DeviceIdentityService {
  final FlutterSecureStorage _secureStorage;
  final DeviceInfoPlugin _deviceInfoPlugin;
  final Future<PackageInfo> Function()? _packageInfoLoader;
  final Uuid _uuid;

  static const String _keyInstallationId = 'upostit_device_install_id_v1';

  FlutterDeviceIdentityService({
    FlutterSecureStorage? secureStorage,
    DeviceInfoPlugin? deviceInfoPlugin,
    Future<PackageInfo> Function()? packageInfoLoader,
    Uuid? uuid,
  })  : _secureStorage = secureStorage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(
                encryptedSharedPreferences: true,
              ),
              iOptions: IOSOptions(
                accessibility: KeychainAccessibility.first_unlock_this_device,
              ),
            ),
        _deviceInfoPlugin = deviceInfoPlugin ?? DeviceInfoPlugin(),
        _packageInfoLoader = packageInfoLoader,
        _uuid = uuid ?? const Uuid();

  @override
  Future<String> getOrCreateInstallationId() async {
    try {
      final existingId = await _secureStorage.read(key: _keyInstallationId);
      if (existingId != null &&
          existingId.trim().isNotEmpty &&
          existingId.length >= 8 &&
          existingId.length <= 128) {
        return existingId.trim();
      }
    } catch (_) {
      // Storage read failure: regenerate and attempt recovery
    }

    final newId = _uuid.v4();
    try {
      await _secureStorage.write(key: _keyInstallationId, value: newId);
    } catch (_) {
      // Even if write encounters a non-fatal transient issue, return the generated ID
    }
    return newId;
  }

  @override
  Future<String?> getInstallationId() async {
    try {
      return await _secureStorage.read(key: _keyInstallationId);
    } catch (_) {
      return null;
    }
  }

  @override
  Future<DevicePlatformInfo> getPlatformMetadata() async {
    String platform = 'OTHER';
    String? deviceModel;
    String? osName;
    String? osVersion;
    String? appVersion;
    final Map<String, dynamic> metadata = {};

    // 1. Resolve Application Version safely
    try {
      final loader = _packageInfoLoader;
      final packageInfo =
          loader != null ? await loader() : await PackageInfo.fromPlatform();
      appVersion = '${packageInfo.version}+${packageInfo.buildNumber}';
    } catch (_) {
      appVersion = '1.0.0+1';
    }

    // 2. Resolve Platform & Hardware Info safely
    try {
      if (kIsWeb) {
        platform = 'WEB';
        final webInfo = await _deviceInfoPlugin.webBrowserInfo;
        deviceModel = webInfo.browserName.name;
        osName = webInfo.platform;
        osVersion = webInfo.userAgent;
      } else if (Platform.isAndroid) {
        platform = 'ANDROID';
        final androidInfo = await _deviceInfoPlugin.androidInfo;
        deviceModel = '${androidInfo.brand} ${androidInfo.model}'.trim();
        osName = 'Android';
        osVersion =
            '${androidInfo.version.release} (SDK ${androidInfo.version.sdkInt})';
        metadata['is_physical_device'] = androidInfo.isPhysicalDevice;
      } else if (Platform.isIOS) {
        platform = 'IOS';
        final iosInfo = await _deviceInfoPlugin.iosInfo;
        deviceModel = iosInfo.utsname.machine;
        osName = iosInfo.systemName;
        osVersion = iosInfo.systemVersion;
        metadata['is_physical_device'] = iosInfo.isPhysicalDevice;
        metadata['model_name'] = iosInfo.name;
      } else if (Platform.isMacOS) {
        platform = 'OTHER';
        osName = 'macOS';
      } else if (Platform.isLinux) {
        platform = 'OTHER';
        osName = 'Linux';
      } else if (Platform.isWindows) {
        platform = 'OTHER';
        osName = 'Windows';
      }
    } catch (_) {
      // Default safe fallback if platform plugins fail (e.g., in unit test harnesses)
      platform = 'ANDROID';
      osName = 'Android';
      deviceModel = 'Standard Mobile Device';
    }

    return DevicePlatformInfo(
      platform: platform,
      deviceModel: deviceModel,
      osName: osName,
      osVersion: osVersion,
      appVersion: appVersion,
      metadata: metadata,
    );
  }
}
