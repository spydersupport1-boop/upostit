import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/errors/failure.dart';
import 'package:mobile/features/devices/data/datasources/device_remote_data_source.dart';
import 'package:mobile/features/devices/data/models/device_model.dart';
import 'package:mobile/features/devices/data/models/device_register_request_model.dart';
import 'package:mobile/features/devices/data/models/device_register_response_model.dart';
import 'package:mobile/features/devices/data/models/device_status_response_model.dart';
import 'package:mobile/features/devices/data/repositories/device_repository_impl.dart';
import 'package:mobile/features/devices/data/services/device_identity_service.dart';
import 'package:mobile/features/devices/domain/entities/device_binding_status.dart';
import 'package:mocktail/mocktail.dart';

class MockDeviceRemoteDataSource extends Mock
    implements DeviceRemoteDataSource {}

class MockDeviceIdentityService extends Mock implements DeviceIdentityService {}

class FakeDeviceRegisterRequestModel extends Fake
    implements DeviceRegisterRequestModel {}

void main() {
  late MockDeviceRemoteDataSource mockRemoteDataSource;
  late MockDeviceIdentityService mockIdentityService;
  late DeviceRepositoryImpl repository;

  final testDeviceModel = DeviceModel(
    id: 'device-uuid-1',
    tenantId: 'tenant-uuid-1',
    employeeId: 'employee-uuid-1',
    platform: 'ANDROID',
    deviceModel: 'Google Pixel 8',
    osName: 'Android',
    osVersion: '14',
    appVersion: '1.0.0+1',
    status: DeviceBindingStatus.active,
    registeredAt: DateTime.utc(2026, 11, 1),
    lastSeenAt: DateTime.utc(2026, 11, 19, 12, 0),
  );

  setUpAll(() {
    registerFallbackValue(FakeDeviceRegisterRequestModel());
  });

  setUp(() {
    mockRemoteDataSource = MockDeviceRemoteDataSource();
    mockIdentityService = MockDeviceIdentityService();

    repository = DeviceRepositoryImpl(
      remoteDataSource: mockRemoteDataSource,
      deviceIdentityService: mockIdentityService,
    );
  });

  group('DeviceRepository - getDeviceStatus', () {
    test('returns DeviceStatusResult on successful remote query (bound)',
        () async {
      final responseModel = DeviceStatusResponseModel(
        isBound: true,
        status: DeviceBindingStatus.active,
        device: testDeviceModel,
      );

      when(() => mockRemoteDataSource.getMyDeviceStatus())
          .thenAnswer((_) async => responseModel);

      final result = await repository.getDeviceStatus();

      expect(result.isSuccess, isTrue);
      final statusResult = result.data!;
      expect(statusResult.isBound, isTrue);
      expect(statusResult.status, equals(DeviceBindingStatus.active));
      expect(statusResult.device?.deviceModel, equals('Google Pixel 8'));
    });

    test('returns DeviceStatusResult on successful remote query (unregistered)',
        () async {
      const responseModel = DeviceStatusResponseModel(
        isBound: false,
        status: DeviceBindingStatus.unregistered,
        device: null,
      );

      when(() => mockRemoteDataSource.getMyDeviceStatus())
          .thenAnswer((_) async => responseModel);

      final result = await repository.getDeviceStatus();

      expect(result.isSuccess, isTrue);
      final statusResult = result.data!;
      expect(statusResult.isBound, isFalse);
      expect(statusResult.status, equals(DeviceBindingStatus.unregistered));
      expect(statusResult.device, isNull);
    });

    test('maps connection timeout to NetworkFailure', () async {
      when(() => mockRemoteDataSource.getMyDeviceStatus()).thenThrow(
        DioException(
          type: DioExceptionType.connectionTimeout,
          requestOptions: RequestOptions(path: '/api/v1/devices/me'),
        ),
      );

      final result = await repository.getDeviceStatus();

      expect(result.isSuccess, isFalse);
      expect(result.failure, isA<NetworkFailure>());
    });

    test('maps 401 unauthorized to ServerFailure with status code', () async {
      when(() => mockRemoteDataSource.getMyDeviceStatus()).thenThrow(
        DioException(
          type: DioExceptionType.badResponse,
          requestOptions: RequestOptions(path: '/api/v1/devices/me'),
          response: Response(
            statusCode: 401,
            data: {'detail': 'Invalid authentication credentials'},
            requestOptions: RequestOptions(path: '/api/v1/devices/me'),
          ),
        ),
      );

      final result = await repository.getDeviceStatus();

      expect(result.isSuccess, isFalse);
      expect(result.failure, isA<ServerFailure>());
      expect(result.failure?.statusCode, equals(401));
      expect(result.failure?.message,
          equals('Invalid authentication credentials'));
    });
  });

  group('DeviceRepository - registerCurrentDevice', () {
    test(
        'collects installation ID and platform metadata, then registers device successfully',
        () async {
      const testDeviceId = 'device-install-id-12345';
      const platformInfo = DevicePlatformInfo(
        platform: 'ANDROID',
        deviceModel: 'Google Pixel 8',
        osName: 'Android',
        osVersion: '14',
        appVersion: '1.0.0+1',
        metadata: {'is_physical_device': true},
      );

      when(() => mockIdentityService.getOrCreateInstallationId())
          .thenAnswer((_) async => testDeviceId);
      when(() => mockIdentityService.getPlatformMetadata())
          .thenAnswer((_) async => platformInfo);

      final registerResponse = DeviceRegisterResponseModel(
        device: testDeviceModel,
        requiresApproval: false,
        message: 'Device registered successfully',
      );

      when(() => mockRemoteDataSource.registerDevice(any()))
          .thenAnswer((_) async => registerResponse);

      final result = await repository.registerCurrentDevice();

      expect(result.isSuccess, isTrue);
      expect(result.data?.id, equals('device-uuid-1'));
      expect(result.data?.status, equals(DeviceBindingStatus.active));

      verify(() => mockRemoteDataSource.registerDevice(any(
            that: isA<DeviceRegisterRequestModel>().having(
              (r) => r.deviceId,
              'deviceId',
              testDeviceId,
            ),
          ))).called(1);
    });

    test('handles 400 device already registered error gracefully', () async {
      when(() => mockIdentityService.getOrCreateInstallationId())
          .thenAnswer((_) async => 'device-install-id-12345');
      when(() => mockIdentityService.getPlatformMetadata()).thenAnswer(
          (_) async => const DevicePlatformInfo(platform: 'ANDROID'));

      when(() => mockRemoteDataSource.registerDevice(any())).thenThrow(
        DioException(
          type: DioExceptionType.badResponse,
          requestOptions: RequestOptions(path: '/api/v1/devices/register'),
          response: Response(
            statusCode: 400,
            data: {
              'detail': 'Device is already bound to another active employee'
            },
            requestOptions: RequestOptions(path: '/api/v1/devices/register'),
          ),
        ),
      );

      final result = await repository.registerCurrentDevice();

      expect(result.isSuccess, isFalse);
      expect(result.failure?.statusCode, equals(400));
      expect(result.failure?.message,
          equals('Device is already bound to another active employee'));
    });
  });
}
