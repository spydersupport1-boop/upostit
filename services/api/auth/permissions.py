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


# Role-to-Permissions Mapping (Deny by default)
ROLE_PERMISSIONS: dict[UserRole, set[Permission]] = {
    UserRole.OWNER: {
        Permission.VIEW_COMPANY_PROFILE,
        Permission.MANAGE_COMPANY_SETTINGS,
        Permission.MANAGE_USERS,
        Permission.ASSIGN_ROLES,
        Permission.VIEW_OWN_PROFILE,
    },
    UserRole.ADMIN: {
        Permission.VIEW_COMPANY_PROFILE,
        Permission.MANAGE_COMPANY_SETTINGS,
        Permission.MANAGE_USERS,
        Permission.ASSIGN_ROLES,
        Permission.VIEW_OWN_PROFILE,
    },
    UserRole.HR: {
        Permission.VIEW_COMPANY_PROFILE,
        Permission.MANAGE_USERS,
        Permission.VIEW_OWN_PROFILE,
    },
    UserRole.MANAGER: {
        Permission.VIEW_COMPANY_PROFILE,
        Permission.VIEW_OWN_PROFILE,
    },
    UserRole.EMPLOYEE: {
        Permission.VIEW_OWN_PROFILE,
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
