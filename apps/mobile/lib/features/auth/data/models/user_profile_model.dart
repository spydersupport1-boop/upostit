import '../../domain/entities/user_profile.dart';

/// Data model for UserEntity matching FastAPI UserResponse.
class UserModel extends UserEntity {
  const UserModel({
    required super.id,
    required super.tenantId,
    required super.fullName,
    required super.email,
    required super.role,
    required super.status,
    super.emailVerifiedAt,
    super.lastLoginAt,
  });

  factory UserModel.fromJson(Map<String, dynamic> json) {
    return UserModel(
      id: json['id'] as String,
      tenantId: json['tenant_id'] as String,
      fullName: json['full_name'] as String,
      email: json['email'] as String,
      role: json['role'] as String,
      status: json['status'] as String,
      emailVerifiedAt: json['email_verified_at'] != null
          ? DateTime.tryParse(json['email_verified_at'] as String)
          : null,
      lastLoginAt: json['last_login_at'] != null
          ? DateTime.tryParse(json['last_login_at'] as String)
          : null,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'tenant_id': tenantId,
      'full_name': fullName,
      'email': email,
      'role': role,
      'status': status,
      'email_verified_at': emailVerifiedAt?.toIso8601String(),
      'last_login_at': lastLoginAt?.toIso8601String(),
    };
  }
}

/// Data model for TenantEntity matching FastAPI TenantResponse.
class TenantModel extends TenantEntity {
  const TenantModel({
    required super.id,
    required super.slug,
    required super.name,
    required super.companyEmail,
    required super.countryCode,
    required super.timezone,
    super.legalName,
    super.status,
  });

  factory TenantModel.fromJson(Map<String, dynamic> json) {
    return TenantModel(
      id: json['id'] as String,
      slug: json['slug'] as String,
      name: json['name'] as String,
      companyEmail: json['company_email'] as String,
      countryCode: json['country_code'] as String,
      timezone: json['timezone'] as String? ?? 'UTC',
      legalName: json['legal_name'] as String?,
      status: json['status'] as String?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'slug': slug,
      'name': name,
      'company_email': companyEmail,
      'country_code': countryCode,
      'timezone': timezone,
      'legal_name': legalName,
      'status': status,
    };
  }
}

/// Combined DTO matching FastAPI UserProfileResponse for /api/v1/auth/me.
class UserProfileModel extends UserProfile {
  const UserProfileModel({
    required super.user,
    required super.tenant,
  });

  factory UserProfileModel.fromJson(Map<String, dynamic> json) {
    return UserProfileModel(
      user: UserModel.fromJson(json['user'] as Map<String, dynamic>),
      tenant: TenantModel.fromJson(json['tenant'] as Map<String, dynamic>),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'user': (user as UserModel).toJson(),
      'tenant': (tenant as TenantModel).toJson(),
    };
  }
}
