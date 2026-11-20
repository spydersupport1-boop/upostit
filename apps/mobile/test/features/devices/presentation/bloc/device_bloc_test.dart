import 'package:bloc_test/bloc_test.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/errors/failure.dart';
import 'package:mobile/core/errors/result.dart';
import 'package:mobile/features/devices/domain/entities/device_binding_status.dart';
import 'package:mobile/features/devices/domain/entities/device_info.dart';
import 'package:mobile/features/devices/domain/entities/device_status_result.dart';
import 'package:mobile/features/devices/domain/repositories/device_repository.dart';
import 'package:mobile/features/devices/presentation/bloc/device_bloc.dart';
import 'package:mobile/features/devices/presentation/bloc/device_event.dart';
import 'package:mobile/features/devices/presentation/bloc/device_state.dart';
import 'package:mocktail/mocktail.dart';

class MockDeviceRepository extends Mock implements DeviceRepository {}

void main() {
  late MockDeviceRepository mockRepository;

  final activeDeviceInfo = DeviceInfo(
    id: 'device-1',
    tenantId: 'tenant-1',
    employeeId: 'emp-1',
    platform: 'ANDROID',
    deviceModel: 'Pixel 8',
    osName: 'Android',
    osVersion: '14',
    appVersion: '1.0.0+1',
    status: DeviceBindingStatus.active,
    registeredAt: DateTime.utc(2026, 11, 1),
  );

  final pendingDeviceInfo = DeviceInfo(
    id: 'device-2',
    tenantId: 'tenant-1',
    employeeId: 'emp-1',
    platform: 'IOS',
    deviceModel: 'iPhone 15',
    osName: 'iOS',
    osVersion: '17.2',
    appVersion: '1.0.0+1',
    status: DeviceBindingStatus.pendingApproval,
    registeredAt: DateTime.utc(2026, 11, 2),
  );

  final revokedDeviceInfo = DeviceInfo(
    id: 'device-3',
    tenantId: 'tenant-1',
    employeeId: 'emp-1',
    platform: 'ANDROID',
    deviceModel: 'Galaxy S23',
    osName: 'Android',
    osVersion: '14',
    appVersion: '1.0.0+1',
    status: DeviceBindingStatus.revoked,
    registeredAt: DateTime.utc(2026, 10, 1),
    revokedAt: DateTime.utc(2026, 11, 10),
    revocationReason: 'Device reported lost by employee',
  );

  setUp(() {
    mockRepository = MockDeviceRepository();
  });

  group('DeviceBloc - CheckDeviceStatusRequested', () {
    test('initial state is DeviceInitial', () {
      final bloc = DeviceBloc(repository: mockRepository);
      expect(bloc.state, equals(const DeviceInitial()));
    });

    blocTest<DeviceBloc, DeviceState>(
      'emits [DeviceLoading, DeviceLoaded] when status check returns ACTIVE device',
      build: () {
        when(() => mockRepository.getDeviceStatus()).thenAnswer(
          (_) async => Result.success(DeviceStatusResult(
            isBound: true,
            status: DeviceBindingStatus.active,
            device: activeDeviceInfo,
          )),
        );
        return DeviceBloc(repository: mockRepository);
      },
      act: (bloc) => bloc.add(const CheckDeviceStatusRequested()),
      expect: () => [
        const DeviceLoading(),
        DeviceLoaded(
          isBound: true,
          status: DeviceBindingStatus.active,
          device: activeDeviceInfo,
        ),
      ],
      verify: (_) {
        verify(() => mockRepository.getDeviceStatus()).called(1);
      },
    );

    blocTest<DeviceBloc, DeviceState>(
      'emits [DeviceLoading, DeviceLoaded] when status check returns UNREGISTERED',
      build: () {
        when(() => mockRepository.getDeviceStatus()).thenAnswer(
          (_) async => const Result.success(DeviceStatusResult(
            isBound: false,
            status: DeviceBindingStatus.unregistered,
            device: null,
          )),
        );
        return DeviceBloc(repository: mockRepository);
      },
      act: (bloc) => bloc.add(const CheckDeviceStatusRequested()),
      expect: () => [
        const DeviceLoading(),
        const DeviceLoaded(
          isBound: false,
          status: DeviceBindingStatus.unregistered,
          device: null,
        ),
      ],
    );

    blocTest<DeviceBloc, DeviceState>(
      'emits [DeviceLoading, DeviceLoaded] when status check returns PENDING_APPROVAL',
      build: () {
        when(() => mockRepository.getDeviceStatus()).thenAnswer(
          (_) async => Result.success(DeviceStatusResult(
            isBound: true,
            status: DeviceBindingStatus.pendingApproval,
            device: pendingDeviceInfo,
          )),
        );
        return DeviceBloc(repository: mockRepository);
      },
      act: (bloc) => bloc.add(const CheckDeviceStatusRequested()),
      expect: () => [
        const DeviceLoading(),
        DeviceLoaded(
          isBound: true,
          status: DeviceBindingStatus.pendingApproval,
          device: pendingDeviceInfo,
        ),
      ],
    );

    blocTest<DeviceBloc, DeviceState>(
      'emits [DeviceLoading, DeviceLoaded] when status check returns REVOKED',
      build: () {
        when(() => mockRepository.getDeviceStatus()).thenAnswer(
          (_) async => Result.success(DeviceStatusResult(
            isBound: true,
            status: DeviceBindingStatus.revoked,
            device: revokedDeviceInfo,
          )),
        );
        return DeviceBloc(repository: mockRepository);
      },
      act: (bloc) => bloc.add(const CheckDeviceStatusRequested()),
      expect: () => [
        const DeviceLoading(),
        DeviceLoaded(
          isBound: true,
          status: DeviceBindingStatus.revoked,
          device: revokedDeviceInfo,
        ),
      ],
    );

    blocTest<DeviceBloc, DeviceState>(
      'emits [DeviceLoading, DeviceFailure] when status check fails with NetworkFailure',
      build: () {
        when(() => mockRepository.getDeviceStatus()).thenAnswer(
          (_) async => const Result.failure(
              NetworkFailure('Unable to connect to server')),
        );
        return DeviceBloc(repository: mockRepository);
      },
      act: (bloc) => bloc.add(const CheckDeviceStatusRequested()),
      expect: () => [
        const DeviceLoading(),
        const DeviceFailure(
          'Unable to connect to server',
          isRetriable: true,
          statusCode: null,
        ),
      ],
    );
  });

  group('DeviceBloc - RegisterCurrentDeviceRequested', () {
    blocTest<DeviceBloc, DeviceState>(
      'transitions from unregistered DeviceLoaded to isRegistering true, then emits updated DeviceLoaded',
      build: () {
        when(() => mockRepository.registerCurrentDevice()).thenAnswer(
          (_) async => Result.success(activeDeviceInfo),
        );
        return DeviceBloc(repository: mockRepository);
      },
      seed: () => const DeviceLoaded(
        isBound: false,
        status: DeviceBindingStatus.unregistered,
        device: null,
      ),
      act: (bloc) => bloc.add(const RegisterCurrentDeviceRequested()),
      expect: () => [
        const DeviceLoaded(
          isBound: false,
          status: DeviceBindingStatus.unregistered,
          device: null,
          isRegistering: true,
        ),
        DeviceLoaded(
          isBound: true,
          status: DeviceBindingStatus.active,
          device: activeDeviceInfo,
          isRegistering: false,
          actionMessage: 'Device registered successfully (Active).',
        ),
      ],
    );

    blocTest<DeviceBloc, DeviceState>(
      'emits DeviceFailure when registration is rejected with 403',
      build: () {
        when(() => mockRepository.registerCurrentDevice()).thenAnswer(
          (_) async => const Result.failure(
            ServerFailure('Device limit reached for tenant', statusCode: 403),
          ),
        );
        return DeviceBloc(repository: mockRepository);
      },
      seed: () => const DeviceLoaded(
        isBound: false,
        status: DeviceBindingStatus.unregistered,
      ),
      act: (bloc) => bloc.add(const RegisterCurrentDeviceRequested()),
      expect: () => [
        const DeviceLoaded(
          isBound: false,
          status: DeviceBindingStatus.unregistered,
          isRegistering: true,
        ),
        const DeviceFailure(
          'Device limit reached for tenant',
          isRetriable: false,
          statusCode: 403,
        ),
      ],
    );
  });
}
