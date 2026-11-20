import 'package:equatable/equatable.dart';

/// Domain entity representing the authenticated user.
class UserEntity extends Equatable {
  final String id;
  final String tenantId;
  final String fullName;
  final String email;
  final String role;
  final String status;
  final DateTime? emailVerifiedAt;
  final DateTime? lastLoginAt;

  const UserEntity({
    required this.id,
    required this.tenantId,
    required this.fullName,
    required this.email,
    required this.role,
    required this.status,
    this.emailVerifiedAt,
    this.lastLoginAt,
  });

  @override
  List<Object?> get props => [
        id,
        tenantId,
        fullName,
        email,
        role,
        status,
        emailVerifiedAt,
        lastLoginAt
      ];
}

/// Domain entity representing the company / tenant organization.
class TenantEntity extends Equatable {
  final String id;
  final String slug;
  final String name;
  final String companyEmail;
  final String countryCode;
  final String timezone;
  final String? legalName;
  final String? status;

  const TenantEntity({
    required this.id,
    required this.slug,
    required this.name,
    required this.companyEmail,
    required this.countryCode,
    required this.timezone,
    this.legalName,
    this.status,
  });

  @override
  List<Object?> get props =>
      [id, slug, name, companyEmail, countryCode, timezone, legalName, status];
}

/// Combined user and tenant profile entity returned by /api/v1/auth/me.
class UserProfile extends Equatable {
  final UserEntity user;
  final TenantEntity tenant;

  const UserProfile({
    required this.user,
    required this.tenant,
  });

  @override
  List<Object?> get props => [user, tenant];
}
