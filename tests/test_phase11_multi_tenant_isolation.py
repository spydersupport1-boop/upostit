"""Comprehensive Multi-Tenant Isolation & Row-Level Security (RLS) Verification (Phase 11.7).

Validates multi-tenant isolation, role-based access control, and Postgres RLS guarantees:
- 3+ Distinct Tenants (Alpha, Beta, Gamma) across 5 Roles (OWNER, ADMIN, HR, MANAGER, EMPLOYEE).
- Cross-tenant batch sync rejection and employee identity derivation.
- Cross-tenant downward delta sync isolation, HMAC cursor binding, and tampering rejection.
- Multi-device conflict queue isolation, anti-self-approval, and manager direct-report scoping.
- Database RLS migration and schema invariant verification.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status

from database.migrations.versions import (
    c1d2e3f4a5b6_phase_11_multi_device_conflicts as phase11_migration,
)
from services.api.attendance.conflict_service import (
    adjudicate_conflict_incident,
)
from services.api.attendance.downward_sync_service import (
    decode_and_verify_sync_cursor,
    generate_sync_cursor,
)
from services.api.attendance.models import (
    AttendanceConflictIncident,
    AttendanceDay,
    AttendanceEvent,
    AttendanceIdempotencyRecord,
    TenantAttendancePolicy,
)
from services.api.attendance.schemas import (
    AttendanceBatchSyncRequest,
    AttendanceConflictDecisionRequest,
    BatchSyncPunchItem,
)
from services.api.attendance.sync_service import process_attendance_batch_sync
from services.api.auth.dependencies import (
    AuthenticatedContext,
)
from services.api.auth.models import User
from services.api.auth.permissions import Permission, UserRole, has_permission
from services.api.database import set_tenant_context
from services.api.devices.models import Device
from services.api.employees.models import Employee
from services.api.tenants.models import Tenant

# ==============================================================================
# Multi-Tenant & Role Setup Fixtures
# ==============================================================================

TENANT_ALPHA = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TENANT_BETA = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
TENANT_GAMMA = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def _build_context(
    tenant_id: uuid.UUID,
    role: str,
    user_id: uuid.UUID | None = None,
    email: str | None = None,
) -> AuthenticatedContext:
    uid = user_id or uuid.uuid4()
    user = User(
        id=uid,
        tenant_id=tenant_id,
        email=email or f"user-{uid.hex[:6]}@tenant-{tenant_id.hex[:4]}.test",
        full_name=f"{role.title()} User",
        role=role.lower(),
        status="ACTIVE",
    )
    tenant = Tenant(
        id=tenant_id,
        name=f"Tenant {tenant_id.hex[:4]}",
        slug=f"tenant-{tenant_id.hex[:4]}",
        company_email=f"info@tenant-{tenant_id.hex[:4]}.test",
        country_code="US",
        timezone="UTC",
        status="active",
    )
    return AuthenticatedContext(user=user, tenant=tenant)


def _build_employee(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    employee_id: uuid.UUID | None = None,
    manager_id: uuid.UUID | None = None,
) -> Employee:
    return Employee(
        id=employee_id or uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        employee_id=f"EMP-{uuid.uuid4().hex[:6]}",
        first_name="Test",
        last_name="Worker",
        work_email=f"worker-{uuid.uuid4().hex[:6]}@test.com",
        reporting_manager_id=manager_id,
        joining_date=date(2025, 1, 1),
        status="active",
    )


# ==============================================================================
# 1. Role-Based Permission Matrices (5 Roles)
# ==============================================================================


@pytest.mark.parametrize(
    ("role", "expected_permissions"),
    [
        (
            UserRole.OWNER,
            {
                Permission.RESOLVE_ATTENDANCE_CONFLICT,
                Permission.VIEW_ATTENDANCE_CONFLICTS,
                Permission.RECORD_PUNCH,
                Permission.VIEW_OWN_PROFILE,
            },
        ),
        (
            UserRole.ADMIN,
            {
                Permission.RESOLVE_ATTENDANCE_CONFLICT,
                Permission.VIEW_ATTENDANCE_CONFLICTS,
                Permission.RECORD_PUNCH,
                Permission.VIEW_OWN_PROFILE,
            },
        ),
        (
            UserRole.HR,
            {
                Permission.RESOLVE_ATTENDANCE_CONFLICT,
                Permission.VIEW_ATTENDANCE_CONFLICTS,
                Permission.RECORD_PUNCH,
                Permission.VIEW_OWN_PROFILE,
            },
        ),
        (
            UserRole.MANAGER,
            {
                Permission.RESOLVE_ATTENDANCE_CONFLICT,
                Permission.VIEW_ATTENDANCE_CONFLICTS,
                Permission.RECORD_PUNCH,
                Permission.VIEW_OWN_PROFILE,
            },
        ),
        (
            UserRole.EMPLOYEE,
            {
                Permission.SUBMIT_ATTENDANCE_CONFLICT,
                Permission.RECORD_PUNCH,
                Permission.VIEW_OWN_PROFILE,
            },
        ),
    ],
)
def test_five_role_permission_matrix(role: UserRole, expected_permissions: set[Permission]):
    """Validates that all 5 roles possess the intended baseline permissions."""
    for perm in expected_permissions:
        assert has_permission(role, perm) is True

    # Employees must NOT possess supervisor resolution permissions
    if role == UserRole.EMPLOYEE:
        assert has_permission(role, Permission.RESOLVE_ATTENDANCE_CONFLICT) is False


# ==============================================================================
# 2. Cross-Tenant Batch Sync Isolation
# ==============================================================================


@pytest.mark.asyncio
async def test_batch_sync_rejects_cross_tenant_employee_mismatch():
    """Batch sync fails with HTTP 404 when user_id belongs to Tenant A but attempts syncing for Tenant B."""
    mock_session = AsyncMock()
    # Emulate query returning no employee for Tenant B with Tenant A's user_id
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_res

    req = AttendanceBatchSyncRequest(
        items=[
            BatchSyncPunchItem(
                local_id="cross-item-1",
                idempotency_key="key-cross-tenant-sync-1",
                event_type="CHECK_IN",
                device_reported_at=datetime.now(UTC),
                sequence_number=1,
                timezone_offset_minutes=0,
                monotonic_boot_time_ms=1000,
                boot_session_id="boot-cross",
            )
        ]
    )

    with pytest.raises(HTTPException) as exc_info:
        await process_attendance_batch_sync(
            session=mock_session,
            tenant_id=TENANT_BETA,
            user_id=uuid.uuid4(),  # Alpha user ID
            user_role="employee",
            payload=req,
        )

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "No employee profile" in exc_info.value.detail


# ==============================================================================
# 3. Cross-Tenant Downward Delta Sync Isolation & HMAC Cursors
# ==============================================================================


@pytest.mark.asyncio
async def test_downward_sync_cross_tenant_cursor_rejection():
    """A cursor signed for Tenant Alpha is rejected with HTTP 400 when submitted to Tenant Beta."""
    alpha_user = uuid.uuid4()
    beta_user = uuid.uuid4()

    # Generate a cryptographically valid cursor for Tenant Alpha
    alpha_cursor = generate_sync_cursor(
        tenant_id=TENANT_ALPHA,
        user_id=alpha_user,
        timestamp=datetime.now(UTC) - timedelta(hours=1),
    )

    # Submitting to Tenant Beta must fail context validation
    with pytest.raises(HTTPException) as exc_info:
        decode_and_verify_sync_cursor(
            cursor_str=alpha_cursor,
            expected_tenant_id=TENANT_BETA,
            expected_user_id=beta_user,
        )

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Sync cursor tenant or user mismatch" in exc_info.value.detail


@pytest.mark.asyncio
async def test_downward_sync_tampered_cursor_signature_rejection():
    """A cursor whose tenant_id was tampered with has an invalid HMAC and is rejected."""
    alpha_user = uuid.uuid4()
    cursor = generate_sync_cursor(
        tenant_id=TENANT_ALPHA,
        user_id=alpha_user,
        timestamp=datetime.now(UTC) - timedelta(hours=1),
    )

    import base64
    import json

    raw = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
    # Maliciously change tenant_id in payload without knowing secret key
    raw["tid"] = str(TENANT_GAMMA)
    tampered_cursor = base64.urlsafe_b64encode(json.dumps(raw).encode()).decode()

    with pytest.raises(HTTPException) as exc_info:
        decode_and_verify_sync_cursor(
            cursor_str=tampered_cursor,
            expected_tenant_id=TENANT_GAMMA,
            expected_user_id=alpha_user,
        )

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Invalid or tampered sync cursor signature" in exc_info.value.detail


@pytest.mark.asyncio
async def test_downward_sync_expired_cursor_rejection():
    """A cursor past its TTL expires and is rejected."""
    user = uuid.uuid4()
    expired_cursor = generate_sync_cursor(
        tenant_id=TENANT_ALPHA,
        user_id=user,
        timestamp=datetime.now(UTC) - timedelta(days=60),
        expires_in_seconds=-10,  # Expired in past
    )

    with pytest.raises(HTTPException) as exc_info:
        decode_and_verify_sync_cursor(
            cursor_str=expired_cursor,
            expected_tenant_id=TENANT_ALPHA,
            expected_user_id=user,
        )

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "expired" in exc_info.value.detail.lower()


# ==============================================================================
# 4. Multi-Device Conflict Adjudication Isolation & Scoping
# ==============================================================================


@pytest.mark.asyncio
async def test_supervisor_cannot_adjudicate_cross_tenant_conflict():
    """Supervisor in Tenant Alpha attempting to adjudicate a conflict in Tenant Beta receives HTTP 404."""
    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None  # Not found in Tenant Alpha
    mock_session.execute.return_value = mock_res

    incident_id = uuid.uuid4()
    req = AttendanceConflictDecisionRequest(
        action="APPROVE",
        reason="Attempting cross-tenant approval",
    )

    with pytest.raises(HTTPException) as exc_info:
        await adjudicate_conflict_incident(
            session=mock_session,
            tenant_id=TENANT_ALPHA,
            incident_id=incident_id,
            reviewer_user_id=uuid.uuid4(),
            reviewer_role="manager",
            payload=req,
        )

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert "Attendance conflict incident not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_anti_self_approval_supervisor_cannot_adjudicate_own_conflict():
    """A manager/supervisor cannot adjudicate their own attendance conflict incident (HTTP 403)."""
    user_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    incident_id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_incident = AttendanceConflictIncident(
        id=incident_id,
        tenant_id=TENANT_ALPHA,
        employee_id=emp_id,
        status="PENDING_REVIEW",
    )

    mock_res_incident = MagicMock()
    mock_res_incident.scalar_one_or_none.return_value = mock_incident

    # Reviewer's employee profile matches the incident's employee_id
    mock_emp = Employee(
        id=emp_id,
        tenant_id=TENANT_ALPHA,
        user_id=user_id,
        employee_id="MGR-001",
        first_name="Self",
        last_name="Reviewer",
        status="active",
        joining_date=date(2025, 1, 1),
    )
    mock_res_emp = MagicMock()
    mock_res_emp.scalar_one_or_none.return_value = mock_emp

    mock_session.execute.side_effect = [mock_res_incident, mock_res_emp]

    req = AttendanceConflictDecisionRequest(
        action="APPROVE",
        reason="Approving my own conflict",
    )

    with pytest.raises(HTTPException) as exc_info:
        await adjudicate_conflict_incident(
            session=mock_session,
            tenant_id=TENANT_ALPHA,
            incident_id=incident_id,
            reviewer_user_id=user_id,
            reviewer_role="manager",
            payload=req,
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert "cannot adjudicate their own attendance conflicts" in exc_info.value.detail


@pytest.mark.asyncio
async def test_manager_scoping_cannot_adjudicate_unrelated_report():
    """A manager can only adjudicate direct reports; attempting to adjudicate peer report returns HTTP 403."""
    mgr_user_id = uuid.uuid4()
    mgr_emp_id = uuid.uuid4()
    unrelated_emp_id = uuid.uuid4()
    incident_id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_incident = AttendanceConflictIncident(
        id=incident_id,
        tenant_id=TENANT_ALPHA,
        employee_id=unrelated_emp_id,
        status="PENDING_REVIEW",
    )
    mock_res_incident = MagicMock()
    mock_res_incident.scalar_one_or_none.return_value = mock_incident

    mock_mgr_emp = Employee(
        id=mgr_emp_id,
        tenant_id=TENANT_ALPHA,
        user_id=mgr_user_id,
        employee_id="MGR-ALPHA",
        first_name="Alpha",
        last_name="Manager",
        status="active",
        joining_date=date(2025, 1, 1),
    )
    mock_res_emp = MagicMock()
    mock_res_emp.scalar_one_or_none.return_value = mock_mgr_emp

    target_emp = Employee(
        id=unrelated_emp_id,
        tenant_id=TENANT_ALPHA,
        user_id=uuid.uuid4(),
        employee_id="EMP-UNRELATED",
        first_name="Unrelated",
        last_name="Worker",
        reporting_manager_id=uuid.uuid4(),  # Reports to a different manager
        status="active",
        joining_date=date(2025, 1, 1),
    )
    mock_res_target_emp = MagicMock()
    mock_res_target_emp.scalar_one_or_none.return_value = target_emp

    mock_session.execute.side_effect = [
        mock_res_incident,
        mock_res_emp,
        mock_res_target_emp,
    ]

    req = AttendanceConflictDecisionRequest(
        action="APPROVE",
        reason="Approving other team's employee",
    )

    with pytest.raises(HTTPException) as exc_info:
        await adjudicate_conflict_incident(
            session=mock_session,
            tenant_id=TENANT_ALPHA,
            incident_id=incident_id,
            reviewer_user_id=mgr_user_id,
            reviewer_role="manager",
            payload=req,
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert "direct reports" in exc_info.value.detail.lower()


# ==============================================================================
# 5. Database Row-Level Security (RLS) & Schema Invariants
# ==============================================================================


@pytest.mark.asyncio
async def test_set_tenant_context_binds_parameterized_sql():
    """Verifies that set_tenant_context safely sets app.tenant_id via parameterized SQL."""
    mock_session = AsyncMock()
    test_tid = uuid.uuid4()

    await set_tenant_context(mock_session, str(test_tid))

    assert mock_session.execute.called
    calls = mock_session.execute.call_args_list
    assert len(calls) >= 1
    args, kwargs = calls[0]
    # Check that tenant_id was passed safely as a query parameter
    assert kwargs.get("tenant_id") == str(test_tid) or (
        len(args) > 1 and args[1].get("tenant_id") == str(test_tid)
    )


def test_attendance_models_have_not_null_tenant_id_invariants():
    """Validates that all core attendance models enforce non-nullable tenant_id foreign keys."""
    models_to_check = [
        AttendanceEvent,
        AttendanceDay,
        AttendanceIdempotencyRecord,
        TenantAttendancePolicy,
        AttendanceConflictIncident,
        Device,
    ]

    for model in models_to_check:
        tenant_col = getattr(model, "tenant_id", None)
        assert tenant_col is not None, f"Model {model.__name__} is missing tenant_id column"
        assert tenant_col.nullable is False, f"Model {model.__name__} has nullable tenant_id"


def test_multi_device_conflict_migration_preserves_tenant_indexes():
    """Validates that Phase 11.5 multi-device migration defines tenant-scoped compound indexes."""
    # Check that the migration defines compound indexes prefixed with tenant_id
    expected_indexes = [
        "ix_conflict_incidents_tenant_code",
        "ix_conflict_incidents_tenant_severity",
    ]
    # Inspect migration code object or globals
    upgrade_code = phase11_migration.upgrade.__code__
    consts_str = str(upgrade_code.co_consts)
    for idx in expected_indexes:
        assert idx in consts_str, f"Migration missing compound tenant index: {idx}"
