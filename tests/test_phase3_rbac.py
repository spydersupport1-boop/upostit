"""Tests for Phase 3 Role-Based Access Control (RBAC) permissions matrix."""

from services.api.auth.permissions import Permission, UserRole, has_permission


def test_owner_phase3_permissions():
    """Owner has full control over organization structure and employees."""
    assert has_permission(UserRole.OWNER, Permission.MANAGE_ORGANIZATION) is True
    assert has_permission(UserRole.OWNER, Permission.VIEW_ORGANIZATION) is True
    assert has_permission(UserRole.OWNER, Permission.CREATE_EMPLOYEES) is True
    assert has_permission(UserRole.OWNER, Permission.VIEW_EMPLOYEES) is True
    assert has_permission(UserRole.OWNER, Permission.UPDATE_EMPLOYEES) is True
    assert has_permission(UserRole.OWNER, Permission.DEACTIVATE_EMPLOYEES) is True


def test_admin_phase3_permissions():
    """Admin has full control over organization structure and employees."""
    assert has_permission(UserRole.ADMIN, Permission.MANAGE_ORGANIZATION) is True
    assert has_permission(UserRole.ADMIN, Permission.VIEW_ORGANIZATION) is True
    assert has_permission(UserRole.ADMIN, Permission.CREATE_EMPLOYEES) is True
    assert has_permission(UserRole.ADMIN, Permission.VIEW_EMPLOYEES) is True
    assert has_permission(UserRole.ADMIN, Permission.UPDATE_EMPLOYEES) is True
    assert has_permission(UserRole.ADMIN, Permission.DEACTIVATE_EMPLOYEES) is True


def test_hr_phase3_permissions():
    """HR can manage employee records and view org structure, but cannot alter org structure."""
    assert has_permission(UserRole.HR, Permission.VIEW_ORGANIZATION) is True
    assert has_permission(UserRole.HR, Permission.CREATE_EMPLOYEES) is True
    assert has_permission(UserRole.HR, Permission.VIEW_EMPLOYEES) is True
    assert has_permission(UserRole.HR, Permission.UPDATE_EMPLOYEES) is True
    assert has_permission(UserRole.HR, Permission.DEACTIVATE_EMPLOYEES) is True
    # HR cannot create/modify/delete departments or designations
    assert has_permission(UserRole.HR, Permission.MANAGE_ORGANIZATION) is False


def test_manager_phase3_permissions():
    """Manager can view org structure and employee directory, but cannot create or alter records."""
    assert has_permission(UserRole.MANAGER, Permission.VIEW_ORGANIZATION) is True
    assert has_permission(UserRole.MANAGER, Permission.VIEW_EMPLOYEES) is True
    assert has_permission(UserRole.MANAGER, Permission.MANAGE_ORGANIZATION) is False
    assert has_permission(UserRole.MANAGER, Permission.CREATE_EMPLOYEES) is False
    assert has_permission(UserRole.MANAGER, Permission.UPDATE_EMPLOYEES) is False
    assert has_permission(UserRole.MANAGER, Permission.DEACTIVATE_EMPLOYEES) is False


def test_employee_phase3_permissions():
    """Employee can view org structure and their own profile, but CANNOT view company directory or alter records."""
    assert has_permission(UserRole.EMPLOYEE, Permission.VIEW_OWN_PROFILE) is True
    assert has_permission(UserRole.EMPLOYEE, Permission.VIEW_ORGANIZATION) is True
    assert has_permission(UserRole.EMPLOYEE, Permission.VIEW_EMPLOYEES) is False
    assert has_permission(UserRole.EMPLOYEE, Permission.MANAGE_ORGANIZATION) is False
    assert has_permission(UserRole.EMPLOYEE, Permission.CREATE_EMPLOYEES) is False
    assert has_permission(UserRole.EMPLOYEE, Permission.UPDATE_EMPLOYEES) is False
    assert has_permission(UserRole.EMPLOYEE, Permission.DEACTIVATE_EMPLOYEES) is False
