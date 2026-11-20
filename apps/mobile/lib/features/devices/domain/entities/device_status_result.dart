import 'package:equatable/equatable.dart';
import 'device_binding_status.dart';
import 'device_info.dart';

/// Clean Architecture domain entity representing the current binding status of the employee's device.
class DeviceStatusResult extends Equatable {
  final bool isBound;
  final DeviceBindingStatus status;
  final DeviceInfo? device;

  const DeviceStatusResult({
    required this.isBound,
    required this.status,
    this.device,
  });

  @override
  List<Object?> get props => [isBound, status, device];
}
