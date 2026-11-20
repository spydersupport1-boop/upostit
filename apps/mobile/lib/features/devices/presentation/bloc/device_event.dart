import 'package:equatable/equatable.dart';

abstract class DeviceEvent extends Equatable {
  const DeviceEvent();

  @override
  List<Object?> get props => [];
}

/// Triggers checking the current employee's registered device status.
class CheckDeviceStatusRequested extends DeviceEvent {
  const CheckDeviceStatusRequested();
}

/// Triggers registering/binding the current mobile device.
class RegisterCurrentDeviceRequested extends DeviceEvent {
  const RegisterCurrentDeviceRequested();
}
