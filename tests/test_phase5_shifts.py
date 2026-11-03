"""Comprehensive unit and API integration tests for Phase 5 Milestone 1:
Shift Templates, Immutable Shift Versions, and Employee Shift Assignments.
"""

import uuid
from datetime import UTC, date, datetime, time
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from services.api.attendance.models import ShiftAssignment, ShiftTemplate, ShiftTemplateVersion
from services.api.attendance.schemas import (
    ShiftAssignmentCreateRequest,
    ShiftAssignmentEndRequest,
    ShiftTemplateCreateRequest,
    ShiftVersionCreateRequest,
)
from services.api.attendance.service import (
    assign_shift_to_employee,
    create_shift_template,
    create_shift_version,
    deactivate_shift_template,
    end_shift_assignment,
    resolve_shift_version_for_date,
)
from services.api.auth.dependencies import AuthenticatedContext, get_authenticated_context
from services.api.auth.models import User
from services.api.database import get_db
from services.api.employees.models import Employee
from services.api.main import app
from services.api.tenants.models import Tenant

# ==============================================================================
# Helper Mock Factories
# ==============================================================================


def _mock_context(
    role: str,
    tenant_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> AuthenticatedContext:
    tid = tenant_id or uuid.uuid4()
    uid = user_id or uuid.uuid4()
    user = User(
        id=uid,
        tenant_id=tid,
        email=f"test_{role}@company.test",
        password_hash="argon2id$mock",
        role=role,
        status="active",
    )
    tenant = Tenant(
        id=tid,
        name="Test Logistics Corp",
        slug=f"test-{tid.hex[:6]}",
        company_email="admin@company.test",
        country_code="IN",
        status="active",
    )
    return AuthenticatedContext(user=user, tenant=tenant)


def _create_mock_employee(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID | None = None,
    status: str = "active",
) -> Employee:
    return Employee(
        id=employee_id or uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id="EMP-1001",
        first_name="Jane",
        last_name="Doe",
        work_email="jane.doe@company.test",
        employment_type="full_time",
        joining_date=date(2026, 1, 1),
        status=status,
    )


def _create_mock_shift_template(
    tenant_id: uuid.UUID,
    shift_id: uuid.UUID | None = None,
    code: str = "DAY-01",
    name: str = "General Day Shift",
    is_active: bool = True,
) -> ShiftTemplate:
    now = datetime.now(UTC)
    return ShiftTemplate(
        id=shift_id or uuid.uuid4(),
        tenant_id=tenant_id,
        name=name,
        code=code,
        description="Standard 9 to 6 office shift",
        is_active=is_active,
        created_at=now,
        updated_at=now,
    )


def _create_mock_shift_version(
    tenant_id: uuid.UUID,
    shift_template_id: uuid.UUID,
    version_number: int = 1,
    effective_from: date | None = None,
    start_time: time = time(9, 0),
    end_time: time = time(18, 0),
    grace_period: int = 15,
    is_overnight: bool = False,
) -> ShiftTemplateVersion:
    now = datetime.now(UTC)
    return ShiftTemplateVersion(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        shift_template_id=shift_template_id,
        version_number=version_number,
        version_effective_from=effective_from or date(2026, 1, 1),
        start_time=start_time,
        end_time=end_time,
        grace_period_minutes=grace_period,
        early_exit_grace_minutes=15,
        early_arrival_allowance_minutes=120,
        late_departure_allowance_minutes=180,
        half_day_threshold_minutes=240,
        full_day_threshold_minutes=480,
        break_duration_minutes=60,
        is_overnight=is_overnight,
        is_flexible=False,
        weekly_off_days=[6, 0],
        created_at=now,
    )


# ==============================================================================
# 1. Pydantic Schema Validation Tests
# ==============================================================================


def test_shift_template_create_schema_valid():
    """Verify valid shift creation payload."""
    req = ShiftTemplateCreateRequest(
        name="General Day Shift",
        code="day-01",
        start_time=time(9, 0),
        end_time=time(18, 0),
        grace_period_minutes=15,
        half_day_threshold_minutes=240,
        full_day_threshold_minutes=480,
        weekly_off_days=[6, 0],
    )
    assert req.name == "General Day Shift"
    assert req.code == "DAY-01"  # Automatically uppercase
    assert req.is_overnight is False


def test_shift_template_create_schema_overnight_valid():
    """Verify overnight shift validation where end_time < start_time."""
    req = ShiftTemplateCreateRequest(
        name="Night Shift",
        code="NIGHT-01",
        start_time=time(22, 0),
        end_time=time(6, 0),
        is_overnight=True,
    )
    assert req.is_overnight is True
    assert req.start_time == time(22, 0)
    assert req.end_time == time(6, 0)


def test_shift_template_create_schema_day_shift_invalid_start_end():
    """Verify standard day shift with start_time >= end_time is rejected."""
    with pytest.raises(ValidationError) as exc:
        ShiftTemplateCreateRequest(
            name="Invalid Shift",
            code="INV-01",
            start_time=time(18, 0),
            end_time=time(9, 0),
            is_overnight=False,
        )
    assert "start_time must be strictly earlier than end_time" in str(exc.value)


def test_shift_template_create_schema_invalid_thresholds():
    """Verify full_day < half_day threshold is rejected."""
    with pytest.raises(ValidationError) as exc:
        ShiftTemplateCreateRequest(
            name="Threshold Test",
            code="THRESH-01",
            start_time=time(9, 0),
            end_time=time(18, 0),
            half_day_threshold_minutes=300,
            full_day_threshold_minutes=200,
        )
    assert "full_day_threshold_minutes must be greater than or equal to" in str(exc.value)


def test_shift_template_create_schema_invalid_weekly_off_days():
    """Verify duplicate and out-of-range weekly off days are rejected."""
    with pytest.raises(ValidationError):
        ShiftTemplateCreateRequest(
            name="Rest Day Test",
            code="REST-01",
            start_time=time(9, 0),
            end_time=time(18, 0),
            weekly_off_days=[0, 7],  # 7 is invalid
        )

    with pytest.raises(ValidationError):
        ShiftTemplateCreateRequest(
            name="Rest Day Test",
            code="REST-02",
            start_time=time(9, 0),
            end_time=time(18, 0),
            weekly_off_days=[0, 0],  # Duplicate
        )


def test_shift_assignment_create_schema_invalid_date_range():
    """Verify effective_to < effective_from is rejected in assignment schema."""
    with pytest.raises(ValidationError) as exc:
        ShiftAssignmentCreateRequest(
            employee_id=uuid.uuid4(),
            shift_template_id=uuid.uuid4(),
            effective_from=date(2026, 6, 1),
            effective_to=date(2026, 5, 1),
        )
    assert "effective_to must be greater than or equal to effective_from" in str(exc.value)


# ==============================================================================
# 2. Shift Template & Version Service Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_create_shift_template_success():
    """Verify creating a shift template creates master template + Version 1 atomically."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()

    mock_session = AsyncMock()
    # Mock code uniqueness query: returns None (no duplicate)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    payload = ShiftTemplateCreateRequest(
        name="General Day Shift",
        code="GEN-DAY",
        start_time=time(9, 0),
        end_time=time(18, 0),
        effective_from=date(2026, 1, 1),
    )

    resp = await create_shift_template(mock_session, tenant_id, user_id, payload)

    assert resp.name == "General Day Shift"
    assert resp.code == "GEN-DAY"
    assert resp.current_version is not None
    assert resp.current_version.version_number == 1
    assert resp.current_version.version_effective_from == date(2026, 1, 1)
    assert resp.current_version.start_time == time(9, 0)
    assert resp.current_version.end_time == time(18, 0)

    # Verify flush and commit were called
    assert mock_session.flush.called
    assert mock_session.commit.called


@pytest.mark.asyncio
async def test_create_shift_template_duplicate_code_rejected():
    """Verify duplicate shift code within the same tenant raises HTTP 409."""
    tenant_id = uuid.uuid4()
    mock_session = AsyncMock()
    existing_shift = _create_mock_shift_template(tenant_id, code="GEN-DAY")

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_shift
    mock_session.execute.return_value = mock_result

    payload = ShiftTemplateCreateRequest(
        name="General Day Shift 2",
        code="GEN-DAY",
        start_time=time(9, 0),
        end_time=time(18, 0),
    )

    with pytest.raises(HTTPException) as exc:
        await create_shift_template(mock_session, tenant_id, None, payload)

    assert exc.value.status_code == 409
    assert "already exists" in exc.value.detail


@pytest.mark.asyncio
async def test_create_shift_version_preserves_history():
    """Verify creating a new shift version increments version number and preserves version 1."""
    tenant_id = uuid.uuid4()
    shift_id = uuid.uuid4()
    mock_session = AsyncMock()

    shift = _create_mock_shift_template(tenant_id, shift_id=shift_id)

    # Mock template query
    res1 = MagicMock()
    res1.scalar_one_or_none.return_value = shift

    # Mock effective date conflict check: returns None
    res2 = MagicMock()
    res2.scalar_one_or_none.return_value = None

    # Mock max version query: returns 1
    res3 = MagicMock()
    res3.scalar_one.return_value = 1

    mock_session.execute.side_effect = [res1, res2, res3]

    payload = ShiftVersionCreateRequest(
        version_effective_from=date(2026, 6, 1),
        start_time=time(8, 30),
        end_time=time(17, 30),
        grace_period_minutes=10,
    )

    version_resp = await create_shift_version(mock_session, tenant_id, shift_id, None, payload)

    assert version_resp.version_number == 2
    assert version_resp.version_effective_from == date(2026, 6, 1)
    assert version_resp.start_time == time(8, 30)
    assert version_resp.end_time == time(17, 30)
    assert version_resp.grace_period_minutes == 10
    assert mock_session.commit.called


@pytest.mark.asyncio
async def test_create_shift_version_duplicate_effective_date_rejected():
    """Verify adding a version with an existing effective date raises HTTP 409."""
    tenant_id = uuid.uuid4()
    shift_id = uuid.uuid4()
    mock_session = AsyncMock()

    shift = _create_mock_shift_template(tenant_id, shift_id=shift_id)
    existing_version = _create_mock_shift_version(
        tenant_id, shift_id, effective_from=date(2026, 1, 1)
    )

    res1 = MagicMock()
    res1.scalar_one_or_none.return_value = shift

    res2 = MagicMock()
    res2.scalar_one_or_none.return_value = existing_version

    mock_session.execute.side_effect = [res1, res2]

    payload = ShiftVersionCreateRequest(
        version_effective_from=date(2026, 1, 1),  # Already exists!
        start_time=time(8, 30),
        end_time=time(17, 30),
    )

    with pytest.raises(HTTPException) as exc:
        await create_shift_version(mock_session, tenant_id, shift_id, None, payload)

    assert exc.value.status_code == 409
    assert "already exists for this shift template" in exc.value.detail


@pytest.mark.asyncio
async def test_resolve_shift_version_for_date():
    """Verify historical date resolution returns the version in force on that specific day."""
    tenant_id = uuid.uuid4()
    shift_id = uuid.uuid4()
    mock_session = AsyncMock()

    v1 = _create_mock_shift_version(
        tenant_id, shift_id, version_number=1, effective_from=date(2026, 1, 1)
    )

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = v1
    mock_session.execute.return_value = mock_res

    # Query for historical date: 2026-03-15 (between v1 and v2)
    resolved = await resolve_shift_version_for_date(
        mock_session, tenant_id, shift_id, date(2026, 3, 15)
    )

    assert resolved is not None
    assert resolved.version_number == 1
    assert resolved.version_effective_from == date(2026, 1, 1)


@pytest.mark.asyncio
async def test_deactivate_shift_template_soft_delete():
    """Verify deleting a shift template sets is_active = False without deleting rows."""
    tenant_id = uuid.uuid4()
    shift_id = uuid.uuid4()
    mock_session = AsyncMock()

    shift = _create_mock_shift_template(tenant_id, shift_id=shift_id, is_active=True)
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = shift
    mock_session.execute.return_value = mock_res

    resp = await deactivate_shift_template(mock_session, tenant_id, shift_id)

    assert resp.is_active is False
    assert shift.is_active is False
    assert mock_session.commit.called


# ==============================================================================
# 3. Shift Assignment Service Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_assign_shift_to_employee_success():
    """Verify assigning a shift template to an employee creates an assignment record."""
    tenant_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    shift_id = uuid.uuid4()
    mock_session = AsyncMock()

    emp = _create_mock_employee(tenant_id, employee_id=emp_id)
    shift = _create_mock_shift_template(tenant_id, shift_id=shift_id)

    res1 = MagicMock()
    res1.scalar_one_or_none.return_value = emp

    res2 = MagicMock()
    res2.scalar_one_or_none.return_value = shift

    res3 = MagicMock()
    res3.scalar_one_or_none.return_value = None  # No overlap

    mock_session.execute.side_effect = [res1, res2, res3]

    payload = ShiftAssignmentCreateRequest(
        employee_id=emp_id,
        shift_template_id=shift_id,
        effective_from=date(2026, 2, 1),
        effective_to=date(2026, 5, 31),
    )

    resp = await assign_shift_to_employee(mock_session, tenant_id, payload)

    assert resp.employee_id == emp_id
    assert resp.shift_template_id == shift_id
    assert resp.effective_from == date(2026, 2, 1)
    assert resp.effective_to == date(2026, 5, 31)
    assert resp.shift_name == shift.name
    assert resp.shift_code == shift.code


@pytest.mark.asyncio
async def test_assign_shift_overlapping_dates_rejected():
    """Verify assigning a shift with overlapping dates is rejected with HTTP 409."""
    tenant_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    shift_id = uuid.uuid4()
    mock_session = AsyncMock()

    emp = _create_mock_employee(tenant_id, employee_id=emp_id)
    shift = _create_mock_shift_template(tenant_id, shift_id=shift_id)
    now = datetime.now(UTC)
    existing_assignment = ShiftAssignment(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp_id,
        shift_template_id=shift_id,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 6, 30),
        created_at=now,
        updated_at=now,
    )

    res1 = MagicMock()
    res1.scalar_one_or_none.return_value = emp

    res2 = MagicMock()
    res2.scalar_one_or_none.return_value = shift

    res3 = MagicMock()
    res3.scalar_one_or_none.return_value = existing_assignment  # Overlap found!

    mock_session.execute.side_effect = [res1, res2, res3]

    payload = ShiftAssignmentCreateRequest(
        employee_id=emp_id,
        shift_template_id=shift_id,
        effective_from=date(2026, 3, 1),  # Overlaps Jan 1 - Jun 30
        effective_to=date(2026, 8, 31),
    )

    with pytest.raises(HTTPException) as exc:
        await assign_shift_to_employee(mock_session, tenant_id, payload)

    assert exc.value.status_code == 409
    assert "overlapping shift assignment" in exc.value.detail


@pytest.mark.asyncio
async def test_assign_shift_deactivated_template_rejected():
    """Verify assigning a deactivated shift template is rejected with HTTP 400."""
    tenant_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    shift_id = uuid.uuid4()
    mock_session = AsyncMock()

    emp = _create_mock_employee(tenant_id, employee_id=emp_id)
    shift = _create_mock_shift_template(tenant_id, shift_id=shift_id, is_active=False)

    res1 = MagicMock()
    res1.scalar_one_or_none.return_value = emp

    res2 = MagicMock()
    res2.scalar_one_or_none.return_value = shift

    mock_session.execute.side_effect = [res1, res2]

    payload = ShiftAssignmentCreateRequest(
        employee_id=emp_id,
        shift_template_id=shift_id,
        effective_from=date(2026, 1, 1),
    )

    with pytest.raises(HTTPException) as exc:
        await assign_shift_to_employee(mock_session, tenant_id, payload)

    assert exc.value.status_code == 400
    assert "Cannot assign employee to a deactivated shift template" in exc.value.detail


@pytest.mark.asyncio
async def test_assign_shift_exclusion_constraint_integrity_error_handled():
    """Verify PostgreSQL exclusion constraint error on race conditions is mapped to HTTP 409."""
    tenant_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    shift_id = uuid.uuid4()
    mock_session = AsyncMock()

    emp = _create_mock_employee(tenant_id, employee_id=emp_id)
    shift = _create_mock_shift_template(tenant_id, shift_id=shift_id)

    res1 = MagicMock()
    res1.scalar_one_or_none.return_value = emp

    res2 = MagicMock()
    res2.scalar_one_or_none.return_value = shift

    res3 = MagicMock()
    res3.scalar_one_or_none.return_value = None  # Application check passes, but DB catches race

    mock_session.execute.side_effect = [res1, res2, res3]
    mock_session.commit.side_effect = IntegrityError(
        statement="INSERT INTO shift_assignments...",
        params={},
        orig=Exception(
            "conflicting key value violates exclusion constraint 'excl_shift_assignments_overlap'"
        ),
    )

    payload = ShiftAssignmentCreateRequest(
        employee_id=emp_id,
        shift_template_id=shift_id,
        effective_from=date(2026, 1, 1),
    )

    with pytest.raises(HTTPException) as exc:
        await assign_shift_to_employee(mock_session, tenant_id, payload)

    assert exc.value.status_code == 409
    assert "exclusion constraint" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_end_shift_assignment_preserves_history():
    """Verify ending an active shift assignment updates effective_to and preserves row."""
    tenant_id = uuid.uuid4()
    assignment_id = uuid.uuid4()
    mock_session = AsyncMock()

    now = datetime.now(UTC)
    sa = ShiftAssignment(
        id=assignment_id,
        tenant_id=tenant_id,
        employee_id=uuid.uuid4(),
        shift_template_id=uuid.uuid4(),
        effective_from=date(2026, 1, 1),
        effective_to=None,  # Ongoing
        created_at=now,
        updated_at=now,
    )

    mock_row = (sa, "Day Shift", "DAY-01")
    mock_res = MagicMock()
    mock_res.first.return_value = mock_row
    mock_session.execute.return_value = mock_res

    payload = ShiftAssignmentEndRequest(end_date=date(2026, 4, 30))
    resp = await end_shift_assignment(mock_session, tenant_id, assignment_id, payload)

    assert resp.effective_to == date(2026, 4, 30)
    assert sa.effective_to == date(2026, 4, 30)
    assert mock_session.commit.called


# ==============================================================================
# 4. HTTP API & RBAC Integration Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_api_shifts_unauthenticated_rejected():
    """Verify calling /api/v1/shifts without JWT returns 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/shifts")
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_employee_forbidden_from_managing_shifts():
    """Verify employee role is denied MANAGE_SHIFTS (403 Forbidden)."""
    tenant_id = uuid.uuid4()
    mock_ctx = _mock_context("employee", tenant_id=tenant_id)
    app.dependency_overrides[get_authenticated_context] = lambda: mock_ctx

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "name": "Employee Shift",
            "code": "EMP-01",
            "start_time": "09:00:00",
            "end_time": "18:00:00",
        }
        resp = await client.post("/api/v1/shifts", json=payload)
        assert resp.status_code == 403

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_manager_read_only_access():
    """Verify manager role has VIEW_SHIFTS but cannot MANAGE_SHIFTS."""
    tenant_id = uuid.uuid4()
    mock_ctx = _mock_context("manager", tenant_id=tenant_id)
    mock_session = AsyncMock()

    # Mock list shifts return
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    app.dependency_overrides[get_authenticated_context] = lambda: mock_ctx
    app.dependency_overrides[get_db] = lambda: mock_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # GET should succeed (200 OK)
        get_resp = await client.get("/api/v1/shifts")
        assert get_resp.status_code == 200

        # POST should be denied (403 Forbidden)
        payload = {
            "name": "Manager Shift",
            "code": "MGR-01",
            "start_time": "09:00:00",
            "end_time": "18:00:00",
        }
        post_resp = await client.post("/api/v1/shifts", json=payload)
        assert post_resp.status_code == 403

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_admin_can_create_shift_and_version():
    """Verify admin role can create shift template and append a new version."""
    tenant_id = uuid.uuid4()
    mock_ctx = _mock_context("admin", tenant_id=tenant_id)
    mock_session = AsyncMock()

    # 1. Mock create template check: returns None
    res1 = MagicMock()
    res1.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = res1

    app.dependency_overrides[get_authenticated_context] = lambda: mock_ctx
    app.dependency_overrides[get_db] = lambda: mock_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "name": "Warehouse Morning",
            "code": "WH-MORN",
            "start_time": "06:00:00",
            "end_time": "14:30:00",
            "grace_period_minutes": 10,
        }
        resp = await client.post("/api/v1/shifts", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["code"] == "WH-MORN"
        assert data["current_version"]["start_time"] == "06:00:00"

    app.dependency_overrides.clear()
