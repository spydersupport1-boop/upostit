import 'package:flutter_bloc/flutter_bloc.dart';
import '../../../../core/errors/failure.dart';
import '../../domain/repositories/device_repository.dart';
import 'device_event.dart';
import 'device_state.dart';

class DeviceBloc extends Bloc<DeviceEvent, DeviceState> {
  final DeviceRepository repository;

  DeviceBloc({required this.repository}) : super(const DeviceInitial()) {
    on<CheckDeviceStatusRequested>(_onCheckDeviceStatusRequested);
    on<RegisterCurrentDeviceRequested>(_onRegisterCurrentDeviceRequested);
  }

  Future<void> _onCheckDeviceStatusRequested(
    CheckDeviceStatusRequested event,
    Emitter<DeviceState> emit,
  ) async {
    emit(const DeviceLoading());

    final result = await repository.getDeviceStatus();

    result.fold(
      (failure) {
        emit(DeviceFailure(
          failure.message,
          isRetriable: failure is NetworkFailure,
          statusCode: failure.statusCode,
        ));
      },
      (statusResult) {
        emit(DeviceLoaded(
          isBound: statusResult.isBound,
          status: statusResult.status,
          device: statusResult.device,
        ));
      },
    );
  }

  Future<void> _onRegisterCurrentDeviceRequested(
    RegisterCurrentDeviceRequested event,
    Emitter<DeviceState> emit,
  ) async {
    final currentState = state;
    if (currentState is DeviceLoaded) {
      emit(currentState.copyWith(isRegistering: true));
    } else {
      emit(const DeviceLoading());
    }

    final result = await repository.registerCurrentDevice();

    result.fold(
      (failure) {
        emit(DeviceFailure(
          failure.message,
          isRetriable: failure is NetworkFailure,
          statusCode: failure.statusCode,
        ));
      },
      (registeredDevice) {
        emit(DeviceLoaded(
          isBound: true,
          status: registeredDevice.status,
          device: registeredDevice,
          isRegistering: false,
          actionMessage:
              'Device registered successfully (${registeredDevice.status.toDisplayString()}).',
        ));
      },
    );
  }
}
