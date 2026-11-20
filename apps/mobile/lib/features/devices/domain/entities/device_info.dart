import 'package:equatable/equatable.dart';
import 'device_binding_status.dart';

/// Clean Architecture domain entity representing a registered mobile device.
class DeviceInfo extends Equatable {
  final String id;
  final String tenantId;
  final String employeeId;
  final String platform;
  final String? deviceModel;
  final String? osName;
  final String? osVersion;
  final String? appVersion;
  final DeviceBindingStatus status;
  final DateTime registeredAt;
  final DateTime? lastSeenAt;
  final DateTime? revokedAt;
  final String? revocationReason;

  const DeviceInfo({
    required this.id,
    required this.tenantId,
    required this.employeeId,
    required this.platform,
    this.deviceModel,
    this.osName,
    this.osVersion,
    this.appVersion,
    required this.status,
    required this.registeredAt,
    this.lastSeenAt,
    this.revokedAt,
    this.revocationReason,
  });

  @override
  List<Object?> get props => [
        id,
        tenantId,
        employeeId,
        platform,
        deviceModel,
        osName,
        osVersion,
        appVersion,
        status,
        registeredAt,
        lastSeenAt,
        revokedAt,
        revocationReason,
      ];
}
