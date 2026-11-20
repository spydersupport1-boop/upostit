import 'package:equatable/equatable.dart';

/// Domain entity representing a workplace location assigned to the employee.
class AssignedWorkplace extends Equatable {
  final String id;
  final String locationId;
  final String locationName;
  final String locationCode;
  final String address;
  final String city;
  final String countryCode;
  final bool isPrimary;
  final bool isCurrent;
  final double? latitude;
  final double? longitude;
  final int? radiusMeters;

  const AssignedWorkplace({
    required this.id,
    required this.locationId,
    required this.locationName,
    required this.locationCode,
    required this.address,
    required this.city,
    required this.countryCode,
    required this.isPrimary,
    required this.isCurrent,
    this.latitude,
    this.longitude,
    this.radiusMeters,
  });

  String get shortDisplay => '$locationName, $city';

  @override
  List<Object?> get props => [
        id,
        locationId,
        locationName,
        locationCode,
        address,
        city,
        countryCode,
        isPrimary,
        isCurrent,
        latitude,
        longitude,
        radiusMeters,
      ];
}
