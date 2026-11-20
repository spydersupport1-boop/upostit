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
    # Phase 6 Attendance Policy Permissions
    MANAGE_ATTENDANCE_POLICY = "manage_attendance_policy"
    VIEW_ATTENDANCE_POLICY = "view_attendance_policy"
    # Phase 7 Device Binding & Fraud Shield Permissions
    MANAGE_DEVICES = "manage_devices"
    VIEW_DEVICES = "view_devices"
    MANAGE_FRAUD_RULES = "manage_fraud_rules"
    VIEW_FRAUD_RULES = "view_fraud_rules"
    VIEW_FRAUD_FLAGS = "view_fraud_flags"
    REVIEW_FRAUD_EVENTS = "review_fraud_events"
    VIEW_FRAUD_REVIEWS = "view_fraud_reviews"
    # Phase 8 Attendance Conflict Permissions
    SUBMIT_ATTENDANCE_CONFLICT = "submit_attendance_conflict"
    VIEW_ATTENDANCE_CONFLICTS = "view_attendance_conflicts"
    RESOLVE_ATTENDANCE_CONFLICT = "resolve_attendance_conflict"
    # Phase 9 Leave & Holiday Permissions
    MANAGE_POLICIES = "manage_policies"
    VIEW_POLICIES = "view_policies"
    MANAGE_LEAVE_TYPES = "manage_leave_types"
    VIEW_LEAVE_TYPES = "view_leave_types"
    MANAGE_HOLIDAYS = "manage_holidays"
    VIEW_HOLIDAYS = "view_holidays"
    APPLY_LEAVE = "apply_leave"
    VIEW_LEAVE_REQUESTS = "view_leave_requests"
    APPROVE_LEAVE = "approve_leave"
    # Phase 9 Overtime Permissions
    MANAGE_OVERTIME_RULES = "manage_overtime_rules"
    VIEW_OVERTIME_RULES = "view_overtime_rules"
    APPROVE_OVERTIME = "approve_overtime"
    VIEW_OVERTIME_RECORDS = "view_overtime_records"


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
        Permission.MANAGE_ATTENDANCE_POLICY,
        Permission.VIEW_ATTENDANCE_POLICY,
        Permission.MANAGE_DEVICES,
        Permission.VIEW_DEVICES,
        Permission.MANAGE_FRAUD_RULES,
        Permission.VIEW_FRAUD_RULES,
        Permission.VIEW_FRAUD_FLAGS,
        Permission.REVIEW_FRAUD_EVENTS,
        Permission.VIEW_FRAUD_REVIEWS,
        Permission.SUBMIT_ATTENDANCE_CONFLICT,
        Permission.VIEW_ATTENDANCE_CONFLICTS,
        Permission.RESOLVE_ATTENDANCE_CONFLICT,
        Permission.MANAGE_POLICIES,
        Permission.VIEW_POLICIES,
        Permission.MANAGE_LEAVE_TYPES,
        Permission.VIEW_LEAVE_TYPES,
        Permission.MANAGE_HOLIDAYS,
        Permission.VIEW_HOLIDAYS,
        Permission.APPLY_LEAVE,
        Permission.VIEW_LEAVE_REQUESTS,
        Permission.APPROVE_LEAVE,
        Permission.MANAGE_OVERTIME_RULES,
        Permission.VIEW_OVERTIME_RULES,
        Permission.APPROVE_OVERTIME,
        Permission.VIEW_OVERTIME_RECORDS,
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
        Permission.MANAGE_ATTENDANCE_POLICY,
        Permission.VIEW_ATTENDANCE_POLICY,
        Permission.MANAGE_DEVICES,
        Permission.VIEW_DEVICES,
        Permission.MANAGE_FRAUD_RULES,
        Permission.VIEW_FRAUD_RULES,
        Permission.VIEW_FRAUD_FLAGS,
        Permission.REVIEW_FRAUD_EVENTS,
        Permission.VIEW_FRAUD_REVIEWS,
        Permission.SUBMIT_ATTENDANCE_CONFLICT,
        Permission.VIEW_ATTENDANCE_CONFLICTS,
        Permission.RESOLVE_ATTENDANCE_CONFLICT,
        Permission.MANAGE_POLICIES,
        Permission.VIEW_POLICIES,
        Permission.MANAGE_LEAVE_TYPES,
        Permission.VIEW_LEAVE_TYPES,
        Permission.MANAGE_HOLIDAYS,
        Permission.VIEW_HOLIDAYS,
        Permission.APPLY_LEAVE,
        Permission.VIEW_LEAVE_REQUESTS,
        Permission.APPROVE_LEAVE,
        Permission.MANAGE_OVERTIME_RULES,
        Permission.VIEW_OVERTIME_RULES,
        Permission.APPROVE_OVERTIME,
        Permission.VIEW_OVERTIME_RECORDS,
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
        Permission.VIEW_ATTENDANCE_POLICY,
        Permission.MANAGE_DEVICES,
        Permission.VIEW_DEVICES,
        Permission.MANAGE_FRAUD_RULES,
        Permission.VIEW_FRAUD_RULES,
        Permission.VIEW_FRAUD_FLAGS,
        Permission.REVIEW_FRAUD_EVENTS,
        Permission.VIEW_FRAUD_REVIEWS,
        Permission.SUBMIT_ATTENDANCE_CONFLICT,
        Permission.VIEW_ATTENDANCE_CONFLICTS,
        Permission.RESOLVE_ATTENDANCE_CONFLICT,
        Permission.MANAGE_POLICIES,
        Permission.VIEW_POLICIES,
        Permission.MANAGE_LEAVE_TYPES,
        Permission.VIEW_LEAVE_TYPES,
        Permission.MANAGE_HOLIDAYS,
        Permission.VIEW_HOLIDAYS,
        Permission.APPLY_LEAVE,
        Permission.VIEW_LEAVE_REQUESTS,
        Permission.APPROVE_LEAVE,
        Permission.MANAGE_OVERTIME_RULES,
        Permission.VIEW_OVERTIME_RULES,
        Permission.APPROVE_OVERTIME,
        Permission.VIEW_OVERTIME_RECORDS,
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
        Permission.VIEW_ATTENDANCE_POLICY,
        Permission.VIEW_FRAUD_FLAGS,
        Permission.VIEW_FRAUD_REVIEWS,
        Permission.SUBMIT_ATTENDANCE_CONFLICT,
        Permission.VIEW_ATTENDANCE_CONFLICTS,
        Permission.RESOLVE_ATTENDANCE_CONFLICT,
        Permission.VIEW_POLICIES,
        Permission.VIEW_LEAVE_TYPES,
        Permission.VIEW_HOLIDAYS,
        Permission.APPLY_LEAVE,
        Permission.VIEW_LEAVE_REQUESTS,
        Permission.APPROVE_LEAVE,
        Permission.VIEW_OVERTIME_RULES,
        Permission.APPROVE_OVERTIME,
        Permission.VIEW_OVERTIME_RECORDS,
    },
    UserRole.EMPLOYEE: {
        Permission.VIEW_OWN_PROFILE,
        Permission.VIEW_ORGANIZATION,
        Permission.VIEW_SHIFTS,
        Permission.RECORD_PUNCH,
        Permission.VIEW_ATTENDANCE,
        Permission.VIEW_ATTENDANCE_POLICY,
        Permission.SUBMIT_ATTENDANCE_CONFLICT,
        Permission.VIEW_ATTENDANCE_CONFLICTS,
        Permission.VIEW_POLICIES,
        Permission.VIEW_LEAVE_TYPES,
        Permission.VIEW_HOLIDAYS,
        Permission.APPLY_LEAVE,
        Permission.VIEW_LEAVE_REQUESTS,
        Permission.VIEW_OVERTIME_RULES,
        Permission.VIEW_OVERTIME_RECORDS,
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
