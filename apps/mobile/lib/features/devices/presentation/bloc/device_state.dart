import 'package:equatable/equatable.dart';
import '../../domain/entities/device_binding_status.dart';
import '../../domain/entities/device_info.dart';

abstract class DeviceState extends Equatable {
  const DeviceState();

  @override
  List<Object?> get props => [];
}

class DeviceInitial extends DeviceState {
  const DeviceInitial();
}

class DeviceLoading extends DeviceState {
  const DeviceLoading();
}

class DeviceLoaded extends DeviceState {
  final bool isBound;
  final DeviceBindingStatus status;
  final DeviceInfo? device;
  final bool isRegistering;
  final String? actionMessage;

  const DeviceLoaded({
    required this.isBound,
    required this.status,
    this.device,
    this.isRegistering = false,
    this.actionMessage,
  });

  DeviceLoaded copyWith({
    bool? isBound,
    DeviceBindingStatus? status,
    DeviceInfo? device,
    bool? isRegistering,
    String? actionMessage,
    bool clearActionMessage = false,
  }) {
    return DeviceLoaded(
      isBound: isBound ?? this.isBound,
      status: status ?? this.status,
      device: device ?? this.device,
      isRegistering: isRegistering ?? this.isRegistering,
      actionMessage:
          clearActionMessage ? null : (actionMessage ?? this.actionMessage),
    );
  }

  @override
  List<Object?> get props => [
        isBound,
        status,
        device,
        isRegistering,
        actionMessage,
      ];
}

class DeviceFailure extends DeviceState {
  final String message;
  final bool isRetriable;
  final int? statusCode;

  const DeviceFailure(
    this.message, {
    this.isRetriable = false,
    this.statusCode,
  });

  @override
  List<Object?> get props => [message, isRetriable, statusCode];
}
