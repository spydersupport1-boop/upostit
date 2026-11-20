import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:network_info_plus/network_info_plus.dart';
import 'package:mobile/features/attendance/data/services/location_service.dart';
import 'package:mobile/features/attendance/data/services/wifi_service.dart';
import 'package:mobile/features/attendance/domain/entities/wifi_evidence.dart';

class MockNetworkInfo extends Mock implements NetworkInfo {}

class MockLocationService extends Mock implements LocationService {}

void main() {
  late MockNetworkInfo mockNetworkInfo;
  late MockLocationService mockLocationService;

  setUp(() {
    mockNetworkInfo = MockNetworkInfo();
    mockLocationService = MockLocationService();
  });

  group('WifiEvidence Entity & BSSID Normalization', () {
    test(
        'normalizes lowercase hyphenated BSSID to uppercase colon-separated format',
        () {
      expect(
        WifiEvidence.normalizeBssid('aa-bb-cc-dd-ee-ff'),
        equals('AA:BB:CC:DD:EE:FF'),
      );
      expect(
        WifiEvidence.normalizeBssid('00:1a:2b:3c:4d:5e'),
        equals('00:1A:2B:3C:4D:5E'),
      );
    });

    test('filters out Android placeholder dummy MAC addresses', () {
      expect(WifiEvidence.normalizeBssid('02:00:00:00:00:00'), isNull);
      expect(WifiEvidence.normalizeBssid('02-00-00-00-00-00'), isNull);
      expect(WifiEvidence.normalizeBssid('00:00:00:00:00:00'), isNull);
    });

    test('rejects malformed BSSID strings', () {
      expect(WifiEvidence.normalizeBssid('not-a-mac'), isNull);
      expect(WifiEvidence.normalizeBssid('00:11:22:33:44'), isNull);
      expect(WifiEvidence.normalizeBssid(''), isNull);
      expect(WifiEvidence.normalizeBssid(null), isNull);
    });

    test('isStale correctly computes freshness based on threshold', () {
      final fresh = WifiEvidence(
        bssid: 'AA:BB:CC:DD:EE:01',
        signalStatus: WifiSignalStatus.available,
        deviceReportedAt: DateTime.now().toUtc(),
        platform: 'android',
      );
      expect(fresh.isStale(maxAgeSeconds: 30), isFalse);

      final stale = WifiEvidence(
        bssid: 'AA:BB:CC:DD:EE:01',
        signalStatus: WifiSignalStatus.available,
        deviceReportedAt:
            DateTime.now().toUtc().subtract(const Duration(seconds: 45)),
        platform: 'android',
      );
      expect(stale.isStale(maxAgeSeconds: 30), isTrue);
    });

    test('maskedBssid hides internal infrastructure MAC digits', () {
      final evidence = WifiEvidence(
        bssid: '12:34:56:78:9A:BC',
        signalStatus: WifiSignalStatus.available,
        deviceReportedAt: DateTime.now().toUtc(),
        platform: 'android',
      );
      expect(evidence.maskedBssid, equals('12:34:***:9A:BC'));
    });
  });

  group('NetworkInfoWifiService - Android Workflow', () {
    test(
        'returns AVAILABLE evidence with normalized BSSID and clean SSID on Android',
        () async {
      when(() => mockLocationService.isLocationServiceEnabled())
          .thenAnswer((_) async => true);
      when(() => mockLocationService.checkPermissionStatus())
          .thenAnswer((_) async => LocationPermissionStatus.granted);
      when(() => mockNetworkInfo.getWifiBSSID())
          .thenAnswer((_) async => '00-11-22-33-44-55');
      when(() => mockNetworkInfo.getWifiName())
          .thenAnswer((_) async => '"Corp-Office-5G"');

      final service = NetworkInfoWifiService(
        networkInfo: mockNetworkInfo,
        locationService: mockLocationService,
        platformResolver: () => 'android',
      );

      final result = await service.getConnectedWifiEvidence();

      expect(result.signalStatus, equals(WifiSignalStatus.available));
      expect(result.bssid, equals('00:11:22:33:44:55'));
      expect(result.ssid, equals('Corp-Office-5G'));
      expect(result.platform, equals('android'));
      expect(result.isAvailable, isTrue);
    });

    test(
        'returns UNAVAILABLE when Android location services (GPS) are toggled OFF',
        () async {
      when(() => mockLocationService.isLocationServiceEnabled())
          .thenAnswer((_) async => false);

      final service = NetworkInfoWifiService(
        networkInfo: mockNetworkInfo,
        locationService: mockLocationService,
        platformResolver: () => 'android',
      );

      final result = await service.getConnectedWifiEvidence();

      expect(result.signalStatus, equals(WifiSignalStatus.unavailable));
      expect(result.bssid, isNull);
      expect(
          result.errorMessage, contains('Location services must be enabled'));
      verifyNever(() => mockNetworkInfo.getWifiBSSID());
    });

    test('returns PERMISSION_DENIED when Android location permission is denied',
        () async {
      when(() => mockLocationService.isLocationServiceEnabled())
          .thenAnswer((_) async => true);
      when(() => mockLocationService.checkPermissionStatus())
          .thenAnswer((_) async => LocationPermissionStatus.denied);

      final service = NetworkInfoWifiService(
        networkInfo: mockNetworkInfo,
        locationService: mockLocationService,
        platformResolver: () => 'android',
      );

      final result = await service.getConnectedWifiEvidence();

      expect(result.signalStatus, equals(WifiSignalStatus.permissionDenied));
      expect(result.bssid, isNull);
      expect(result.errorMessage, contains('Location permission is required'));
      verifyNever(() => mockNetworkInfo.getWifiBSSID());
    });

    test(
        'returns UNAVAILABLE when Android returns dummy 02:00:00:00:00:00 MAC address',
        () async {
      when(() => mockLocationService.isLocationServiceEnabled())
          .thenAnswer((_) async => true);
      when(() => mockLocationService.checkPermissionStatus())
          .thenAnswer((_) async => LocationPermissionStatus.granted);
      when(() => mockNetworkInfo.getWifiBSSID())
          .thenAnswer((_) async => '02:00:00:00:00:00');
      when(() => mockNetworkInfo.getWifiName())
          .thenAnswer((_) async => 'Some-Network');

      final service = NetworkInfoWifiService(
        networkInfo: mockNetworkInfo,
        locationService: mockLocationService,
        platformResolver: () => 'android',
      );

      final result = await service.getConnectedWifiEvidence();

      expect(result.signalStatus, equals(WifiSignalStatus.unavailable));
      expect(result.bssid, isNull);
      expect(result.isAvailable, isFalse);
    });
  });

  group('NetworkInfoWifiService - iOS Workflow', () {
    test('returns AVAILABLE evidence with BSSID on provisioned iOS device',
        () async {
      when(() => mockLocationService.checkPermissionStatus())
          .thenAnswer((_) async => LocationPermissionStatus.granted);
      when(() => mockNetworkInfo.getWifiBSSID())
          .thenAnswer((_) async => 'AA:BB:CC:DD:EE:FF');
      when(() => mockNetworkInfo.getWifiName())
          .thenAnswer((_) async => '"Guest-Wifi"');

      final service = NetworkInfoWifiService(
        networkInfo: mockNetworkInfo,
        locationService: mockLocationService,
        platformResolver: () => 'ios',
      );

      final result = await service.getConnectedWifiEvidence();

      expect(result.signalStatus, equals(WifiSignalStatus.available));
      expect(result.bssid, equals('AA:BB:CC:DD:EE:FF'));
      expect(result.ssid, equals('Guest-Wifi'));
      expect(result.platform, equals('ios'));
    });

    test(
        'returns UNSUPPORTED on iOS when BSSID is nil (simulator or missing entitlement)',
        () async {
      when(() => mockLocationService.checkPermissionStatus())
          .thenAnswer((_) async => LocationPermissionStatus.granted);
      when(() => mockNetworkInfo.getWifiBSSID()).thenAnswer((_) async => null);
      when(() => mockNetworkInfo.getWifiName()).thenAnswer((_) async => null);

      final service = NetworkInfoWifiService(
        networkInfo: mockNetworkInfo,
        locationService: mockLocationService,
        platformResolver: () => 'ios',
      );

      final result = await service.getConnectedWifiEvidence();

      expect(result.signalStatus, equals(WifiSignalStatus.unsupported));
      expect(result.bssid, isNull);
      expect(result.errorMessage, contains('unavailable on this iOS build'));
    });

    test(
        'returns PERMISSION_DENIED on iOS when location permission is not granted',
        () async {
      when(() => mockLocationService.checkPermissionStatus())
          .thenAnswer((_) async => LocationPermissionStatus.permanentlyDenied);

      final service = NetworkInfoWifiService(
        networkInfo: mockNetworkInfo,
        locationService: mockLocationService,
        platformResolver: () => 'ios',
      );

      final result = await service.getConnectedWifiEvidence();

      expect(result.signalStatus, equals(WifiSignalStatus.permissionDenied));
      expect(result.bssid, isNull);
    });
  });

  group('NetworkInfoWifiService - Platform & Exception Edge Cases', () {
    test('returns UNSUPPORTED on web or desktop platforms', () async {
      final service = NetworkInfoWifiService(
        networkInfo: mockNetworkInfo,
        locationService: mockLocationService,
        platformResolver: () => 'macos',
      );

      final result = await service.getConnectedWifiEvidence();

      expect(result.signalStatus, equals(WifiSignalStatus.unsupported));
      expect(result.platform, equals('macos'));
      expect(result.errorMessage, contains('not supported on macos'));
    });

    test('returns UNAVAILABLE when networkInfo throws platform exception',
        () async {
      when(() => mockLocationService.isLocationServiceEnabled())
          .thenAnswer((_) async => true);
      when(() => mockLocationService.checkPermissionStatus())
          .thenAnswer((_) async => LocationPermissionStatus.granted);
      when(() => mockNetworkInfo.getWifiBSSID())
          .thenThrow(Exception('Native Wi-Fi hardware communication failure'));

      final service = NetworkInfoWifiService(
        networkInfo: mockNetworkInfo,
        locationService: mockLocationService,
        platformResolver: () => 'android',
      );

      final result = await service.getConnectedWifiEvidence();

      expect(result.signalStatus, equals(WifiSignalStatus.unavailable));
      expect(result.bssid, isNull);
      expect(result.errorMessage, contains('Unable to query connected Wi-Fi'));
    });
  });
}
