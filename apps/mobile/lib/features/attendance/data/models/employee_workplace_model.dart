import '../../domain/entities/assigned_workplace.dart';

/// Data Transfer Object for EmployeeWorkplaceResponse JSON payload.
class EmployeeWorkplaceModel extends AssignedWorkplace {
  const EmployeeWorkplaceModel({
    required super.id,
    required super.locationId,
    required super.locationName,
    required super.locationCode,
    required super.address,
    required super.city,
    required super.countryCode,
    required super.isPrimary,
    required super.isCurrent,
    super.latitude,
    super.longitude,
    super.radiusMeters,
  });

  factory EmployeeWorkplaceModel.fromJson(Map<String, dynamic> json) {
    return EmployeeWorkplaceModel(
      id: json['id'] as String,
      locationId: json['location_id'] as String,
      locationName: (json['location_name'] ?? 'Primary Location') as String,
      locationCode: (json['location_code'] ?? 'LOC') as String,
      address: (json['location_address'] ?? '') as String,
      city: (json['location_city'] ?? '') as String,
      countryCode: (json['location_country_code'] ?? 'US') as String,
      isPrimary: (json['is_primary'] as bool?) ?? false,
      isCurrent: (json['is_current'] as bool?) ?? true,
      latitude: json['latitude'] != null
          ? double.tryParse(json['latitude'].toString())
          : null,
      longitude: json['longitude'] != null
          ? double.tryParse(json['longitude'].toString())
          : null,
      radiusMeters: json['radius_meters'] != null
          ? (num.tryParse(json['radius_meters'].toString()))?.toInt()
          : null,
    );
  }
}
