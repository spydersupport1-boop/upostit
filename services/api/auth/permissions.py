"""Centralized Role-Based Access Control (RBAC) definitions and permissions registry."""

from enum import StrEnum


class UserRole(StrEnum):
    """Platform user roles."""

    OWNER = "owner"
    ADMIN = "admin"
    HR = "hr"
    MANAGER = "manager"
    EMPLOYEE = "employee"


class Permission(StrEnum):
    """Granular platform capabilities."""

    VIEW_COMPANY_PROFILE = "view_company_profile"
    MANAGE_COMPANY_SETTINGS = "manage_company_settings"
    MANAGE_USERS = "manage_users"
    ASSIGN_ROLES = "assign_roles"
    VIEW_OWN_PROFILE = "view_own_profile"
    # Organization Structure Permissions
    MANAGE_ORGANIZATION = "manage_organization"
    VIEW_ORGANIZATION = "view_organization"
    # Employee Management Permissions
    CREATE_EMPLOYEES = "create_employees"
    VIEW_EMPLOYEES = "view_employees"
    UPDATE_EMPLOYEES = "update_employees"
    DEACTIVATE_EMPLOYEES = "deactivate_employees"
    # Phase 4 Workplace & Onboarding Permissions
    MANAGE_LOCATIONS = "manage_locations"
    VIEW_LOCATIONS = "view_locations"
    IMPORT_EMPLOYEES = "import_employees"
    INVITE_EMPLOYEES = "invite_employees"
    # Phase 5 Attendance & Shifts Permissions
    MANAGE_SHIFTS = "manage_shifts"
    VIEW_SHIFTS = "view_shifts"
    RECORD_PUNCH = "record_punch"
    VIEW_ATTENDANCE = "view_attendance"
    MANAGE_ATTENDANCE = "manage_attendance"
    CORRECT_ATTENDANCE = "correct_attendance"


# Role-to-Permissions Mapping (Deny by default)
ROLE_PERMISSIONS: dict[UserRole, set[Permission]] = {
    UserRole.OWNER: {
        Permission.VIEW_COMPANY_PROFILE,
        Permission.MANAGE_COMPANY_SETTINGS,
        Permission.MANAGE_USERS,
        Permission.ASSIGN_ROLES,
        Permission.VIEW_OWN_PROFILE,
        Permission.MANAGE_ORGANIZATION,
        Permission.VIEW_ORGANIZATION,
        Permission.CREATE_EMPLOYEES,
        Permission.VIEW_EMPLOYEES,
        Permission.UPDATE_EMPLOYEES,
        Permission.DEACTIVATE_EMPLOYEES,
        Permission.MANAGE_LOCATIONS,
        Permission.VIEW_LOCATIONS,
        Permission.IMPORT_EMPLOYEES,
        Permission.INVITE_EMPLOYEES,
        Permission.MANAGE_SHIFTS,
        Permission.VIEW_SHIFTS,
        Permission.RECORD_PUNCH,
        Permission.VIEW_ATTENDANCE,
        Permission.MANAGE_ATTENDANCE,
        Permission.CORRECT_ATTENDANCE,
    },
    UserRole.ADMIN: {
        Permission.VIEW_COMPANY_PROFILE,
        Permission.MANAGE_COMPANY_SETTINGS,
        Permission.MANAGE_USERS,
        Permission.ASSIGN_ROLES,
        Permission.VIEW_OWN_PROFILE,
        Permission.MANAGE_ORGANIZATION,
        Permission.VIEW_ORGANIZATION,
        Permission.CREATE_EMPLOYEES,
        Permission.VIEW_EMPLOYEES,
        Permission.UPDATE_EMPLOYEES,
        Permission.DEACTIVATE_EMPLOYEES,
        Permission.MANAGE_LOCATIONS,
        Permission.VIEW_LOCATIONS,
        Permission.IMPORT_EMPLOYEES,
        Permission.INVITE_EMPLOYEES,
        Permission.MANAGE_SHIFTS,
        Permission.VIEW_SHIFTS,
        Permission.RECORD_PUNCH,
        Permission.VIEW_ATTENDANCE,
        Permission.MANAGE_ATTENDANCE,
        Permission.CORRECT_ATTENDANCE,
    },
    UserRole.HR: {
        Permission.VIEW_COMPANY_PROFILE,
        Permission.MANAGE_USERS,
        Permission.VIEW_OWN_PROFILE,
        Permission.VIEW_ORGANIZATION,
        Permission.CREATE_EMPLOYEES,
        Permission.VIEW_EMPLOYEES,
        Permission.UPDATE_EMPLOYEES,
        Permission.DEACTIVATE_EMPLOYEES,
        Permission.VIEW_LOCATIONS,
        Permission.IMPORT_EMPLOYEES,
        Permission.INVITE_EMPLOYEES,
        Permission.MANAGE_SHIFTS,
        Permission.VIEW_SHIFTS,
        Permission.RECORD_PUNCH,
        Permission.VIEW_ATTENDANCE,
        Permission.MANAGE_ATTENDANCE,
        Permission.CORRECT_ATTENDANCE,
    },
    UserRole.MANAGER: {
        Permission.VIEW_COMPANY_PROFILE,
        Permission.VIEW_OWN_PROFILE,
        Permission.VIEW_ORGANIZATION,
        Permission.VIEW_EMPLOYEES,
        Permission.VIEW_LOCATIONS,
        Permission.VIEW_SHIFTS,
        Permission.RECORD_PUNCH,
        Permission.VIEW_ATTENDANCE,
        Permission.CORRECT_ATTENDANCE,
    },
    UserRole.EMPLOYEE: {
        Permission.VIEW_OWN_PROFILE,
        Permission.VIEW_ORGANIZATION,
        Permission.VIEW_SHIFTS,
        Permission.RECORD_PUNCH,
        Permission.VIEW_ATTENDANCE,
    },
}


def has_permission(role: UserRole | str, permission: Permission | str) -> bool:
    """Checks whether a given user role possesses the requested permission."""
    try:
        user_role = UserRole(role) if isinstance(role, str) else role
        perm = Permission(permission) if isinstance(permission, str) else permission
    except ValueError:
        return False
    return perm in ROLE_PERMISSIONS.get(user_role, set())
