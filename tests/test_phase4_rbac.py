"""Unit tests for Phase 4 RBAC permissions mapping and role boundaries."""

from services.api.auth.permissions import Permission, UserRole, has_permission


def test_owner_phase4_permissions():
    """Verify OWNER possesses all Phase 4 permissions."""
    assert has_permission(UserRole.OWNER, Permission.MANAGE_LOCATIONS) is True
    assert has_permission(UserRole.OWNER, Permission.VIEW_LOCATIONS) is True
    assert has_permission(UserRole.OWNER, Permission.IMPORT_EMPLOYEES) is True
    assert has_permission(UserRole.OWNER, Permission.INVITE_EMPLOYEES) is True


def test_admin_phase4_permissions():
    """Verify ADMIN possesses all Phase 4 permissions."""
    assert has_permission(UserRole.ADMIN, Permission.MANAGE_LOCATIONS) is True
    assert has_permission(UserRole.ADMIN, Permission.VIEW_LOCATIONS) is True
    assert has_permission(UserRole.ADMIN, Permission.IMPORT_EMPLOYEES) is True
    assert has_permission(UserRole.ADMIN, Permission.INVITE_EMPLOYEES) is True


def test_hr_phase4_permissions():
    """Verify HR has view_locations, import_employees, and invite_employees, but cannot manage_locations."""
    assert has_permission(UserRole.HR, Permission.VIEW_LOCATIONS) is True
    assert has_permission(UserRole.HR, Permission.IMPORT_EMPLOYEES) is True
    assert has_permission(UserRole.HR, Permission.INVITE_EMPLOYEES) is True
    # HR is restricted from configuring geofence coordinates and locations
    assert has_permission(UserRole.HR, Permission.MANAGE_LOCATIONS) is False


def test_manager_phase4_permissions():
    """Verify MANAGER has view_locations only."""
    assert has_permission(UserRole.MANAGER, Permission.VIEW_LOCATIONS) is True
    assert has_permission(UserRole.MANAGER, Permission.MANAGE_LOCATIONS) is False
    assert has_permission(UserRole.MANAGER, Permission.IMPORT_EMPLOYEES) is False
    assert has_permission(UserRole.MANAGER, Permission.INVITE_EMPLOYEES) is False


def test_employee_phase4_permissions():
    """Verify EMPLOYEE has zero organization-wide location permissions (self-access only)."""
    assert has_permission(UserRole.EMPLOYEE, Permission.VIEW_LOCATIONS) is False
    assert has_permission(UserRole.EMPLOYEE, Permission.MANAGE_LOCATIONS) is False
    assert has_permission(UserRole.EMPLOYEE, Permission.IMPORT_EMPLOYEES) is False
    assert has_permission(UserRole.EMPLOYEE, Permission.INVITE_EMPLOYEES) is False
