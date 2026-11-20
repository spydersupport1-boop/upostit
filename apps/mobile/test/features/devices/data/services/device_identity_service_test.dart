import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/features/devices/data/services/device_identity_service.dart';
import 'package:mocktail/mocktail.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:uuid/uuid.dart';

class MockFlutterSecureStorage extends Mock implements FlutterSecureStorage {}

class MockUuid extends Mock implements Uuid {}

void main() {
  late MockFlutterSecureStorage mockStorage;
  late MockUuid mockUuid;
  late FlutterDeviceIdentityService identityService;

  const testKey = 'upostit_device_install_id_v1';
  const generatedId = '9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d';
  const existingId = '11111111-2222-3333-4444-555555555555';

  setUp(() {
    mockStorage = MockFlutterSecureStorage();
    mockUuid = MockUuid();

    identityService = FlutterDeviceIdentityService(
      secureStorage: mockStorage,
      uuid: mockUuid,
      packageInfoLoader: () async => PackageInfo(
        appName: 'Upostit Attendance',
        packageName: 'com.upostit.attendance',
        version: '1.2.3',
        buildNumber: '42',
      ),
    );
  });

  group('DeviceIdentityService - Installation Identifier Lifecycle', () {
    test(
        'getOrCreateInstallationId generates, stores, and returns a new UUID v4 on first launch',
        () async {
      when(() => mockStorage.read(key: testKey)).thenAnswer((_) async => null);
      when(() => mockUuid.v4()).thenReturn(generatedId);
      when(() => mockStorage.write(key: testKey, value: generatedId))
          .thenAnswer((_) async {});

      final id = await identityService.getOrCreateInstallationId();

      expect(id, equals(generatedId));
      verify(() => mockStorage.read(key: testKey)).called(1);
      verify(() => mockUuid.v4()).called(1);
      verify(() => mockStorage.write(key: testKey, value: generatedId))
          .called(1);
    });

    test(
        'getOrCreateInstallationId reuses existing persisted identifier on subsequent runs',
        () async {
      when(() => mockStorage.read(key: testKey))
          .thenAnswer((_) async => existingId);

      final id = await identityService.getOrCreateInstallationId();

      expect(id, equals(existingId));
      verify(() => mockStorage.read(key: testKey)).called(1);
      verifyNever(() => mockUuid.v4());
      verifyNever(() => mockStorage.write(
            key: any(named: 'key'),
            value: any(named: 'value'),
          ));
    });

    test(
        'getOrCreateInstallationId regenerates identifier when stored key is corrupt or too short',
        () async {
      // Corrupted / too short value (< 8 chars)
      when(() => mockStorage.read(key: testKey)).thenAnswer((_) async => 'bad');
      when(() => mockUuid.v4()).thenReturn(generatedId);
      when(() => mockStorage.write(key: testKey, value: generatedId))
          .thenAnswer((_) async {});

      final id = await identityService.getOrCreateInstallationId();

      expect(id, equals(generatedId));
      verify(() => mockUuid.v4()).called(1);
      verify(() => mockStorage.write(key: testKey, value: generatedId))
          .called(1);
    });

    test(
        'getOrCreateInstallationId recovers gracefully when secure storage read throws',
        () async {
      when(() => mockStorage.read(key: testKey))
          .thenThrow(Exception('Keystore decryption failure'));
      when(() => mockUuid.v4()).thenReturn(generatedId);
      when(() => mockStorage.write(key: testKey, value: generatedId))
          .thenAnswer((_) async {});

      final id = await identityService.getOrCreateInstallationId();

      expect(id, equals(generatedId));
      verify(() => mockUuid.v4()).called(1);
    });

    test('getInstallationId returns null when no key is persisted', () async {
      when(() => mockStorage.read(key: testKey)).thenAnswer((_) async => null);

      final id = await identityService.getInstallationId();

      expect(id, isNull);
    });

    test('getInstallationId returns persisted ID without generating', () async {
      when(() => mockStorage.read(key: testKey))
          .thenAnswer((_) async => existingId);

      final id = await identityService.getInstallationId();

      expect(id, equals(existingId));
      verifyNever(() => mockUuid.v4());
    });
  });

  group('DeviceIdentityService - Platform Metadata Collection', () {
    test(
        'getPlatformMetadata resolves app version and fallback platform safely in test environment',
        () async {
      final info = await identityService.getPlatformMetadata();

      expect(info.appVersion, equals('1.2.3+42'));
      expect(info.platform, isNotEmpty);
      expect(info.osName, isNotEmpty);
    });
  });
}
