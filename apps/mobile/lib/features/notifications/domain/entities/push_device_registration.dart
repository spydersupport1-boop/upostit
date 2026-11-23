import 'package:equatable/equatable.dart';

/// Represents a registered mobile push device token record on the UPOSTIT backend.
class PushDeviceRegistration extends Equatable {
  final String id;
  final String tenantId;
  final String userId;
  final String? employeeId;
  final String platform;
  final String tokenPreview;
  final String? deviceModel;
  final String? osVersion;
  final String? appVersion;
  final String status;
  final DateTime lastSeenAt;
  final DateTime createdAt;

  const PushDeviceRegistration({
    required this.id,
    required this.tenantId,
    required this.userId,
    this.employeeId,
    required this.platform,
    required this.tokenPreview,
    this.deviceModel,
    this.osVersion,
    this.appVersion,
    required this.status,
    required this.lastSeenAt,
    required this.createdAt,
  });

  bool get isActive => status.toUpperCase() == 'ACTIVE';

  @override
  List<Object?> get props => [
        id,
        tenantId,
        userId,
        employeeId,
        platform,
        tokenPreview,
        deviceModel,
        osVersion,
        appVersion,
        status,
        lastSeenAt,
        createdAt,
      ];
}
