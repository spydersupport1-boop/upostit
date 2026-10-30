"""Unit tests for Phase 2 Role-Based Access Control (RBAC) permissions."""

from services.api.auth.permissions import (
    Permission,
    UserRole,
    has_permission,
)


def test_rbac_roles_exist():
    """Verify all 5 required roles are defined."""
    assert UserRole.OWNER == "owner"
    assert UserRole.ADMIN == "admin"
    assert UserRole.HR == "hr"
    assert UserRole.MANAGER == "manager"
    assert UserRole.EMPLOYEE == "employee"


def test_owner_permissions():
    """Verify owner has all permissions in the baseline matrix."""
    assert has_permission(UserRole.OWNER, Permission.VIEW_COMPANY_PROFILE) is True
    assert has_permission(UserRole.OWNER, Permission.MANAGE_COMPANY_SETTINGS) is True
    assert has_permission(UserRole.OWNER, Permission.MANAGE_USERS) is True
    assert has_permission(UserRole.OWNER, Permission.ASSIGN_ROLES) is True
    assert has_permission(UserRole.OWNER, Permission.VIEW_OWN_PROFILE) is True


def test_admin_permissions():
    """Verify admin has administrative capabilities."""
    assert has_permission(UserRole.ADMIN, Permission.VIEW_COMPANY_PROFILE) is True
    assert has_permission(UserRole.ADMIN, Permission.MANAGE_COMPANY_SETTINGS) is True
    assert has_permission(UserRole.ADMIN, Permission.MANAGE_USERS) is True
    assert has_permission(UserRole.ADMIN, Permission.ASSIGN_ROLES) is True
    assert has_permission(UserRole.ADMIN, Permission.VIEW_OWN_PROFILE) is True


def test_hr_permissions():
    """Verify HR cannot manage company settings or assign owner/admin roles."""
    assert has_permission(UserRole.HR, Permission.VIEW_COMPANY_PROFILE) is True
    assert has_permission(UserRole.HR, Permission.MANAGE_USERS) is True
    assert has_permission(UserRole.HR, Permission.VIEW_OWN_PROFILE) is True
    assert has_permission(UserRole.HR, Permission.MANAGE_COMPANY_SETTINGS) is False
    assert has_permission(UserRole.HR, Permission.ASSIGN_ROLES) is False


def test_manager_permissions():
    """Verify manager has limited company access and cannot manage users or settings."""
    assert has_permission(UserRole.MANAGER, Permission.VIEW_COMPANY_PROFILE) is True
    assert has_permission(UserRole.MANAGER, Permission.VIEW_OWN_PROFILE) is True
    assert has_permission(UserRole.MANAGER, Permission.MANAGE_USERS) is False
    assert has_permission(UserRole.MANAGER, Permission.MANAGE_COMPANY_SETTINGS) is False
    assert has_permission(UserRole.MANAGER, Permission.ASSIGN_ROLES) is False


def test_employee_permissions():
    """Verify employee can only view their own profile."""
    assert has_permission(UserRole.EMPLOYEE, Permission.VIEW_OWN_PROFILE) is True
    assert has_permission(UserRole.EMPLOYEE, Permission.VIEW_COMPANY_PROFILE) is False
    assert has_permission(UserRole.EMPLOYEE, Permission.MANAGE_USERS) is False
    assert has_permission(UserRole.EMPLOYEE, Permission.MANAGE_COMPANY_SETTINGS) is False
    assert has_permission(UserRole.EMPLOYEE, Permission.ASSIGN_ROLES) is False


def test_deny_by_default_and_invalid_role():
    """Verify unknown roles or permissions are denied by default."""
    assert has_permission("unknown_role", Permission.VIEW_OWN_PROFILE) is False
    assert has_permission(UserRole.EMPLOYEE, "invalid_permission") is False
