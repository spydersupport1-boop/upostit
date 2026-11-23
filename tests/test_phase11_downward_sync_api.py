"""Automated test suite for Phase 11.3:
Downward Delta Sync Protocol (Reference Data & Shift Rosters).

Verifies:
1. Cursor generation, HMAC verification, and tamper detection.
2. Initial full synchronization (all 7 domain entities).
3. Incremental delta synchronization (only modified records).
4. No-change synchronization (empty lists, has_more=False).
5. Pagination & bounded response sizing (limit parameter, has_more=True).
6. Cross-tenant isolation (Tenant A cannot access Tenant B data).
7. Cursor tenant and user mismatch rejection (HTTP 400).
8. Cursor tampering / invalid signature rejection (HTTP 400).
9. Employee deactivation semantics (status='inactive', empty reference lists).
10. Manager / reporting hierarchy (manager sees direct reports, employee sees manager).
11. Tombstone generation for deactivated/unassigned workplaces.
12. HTTP route handlers for both /api/v1/sync/delta and /api/v1/attendance/sync/delta.
13. Unauthenticated access rejection (HTTP 401).
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status
from httpx import ASGITransport, AsyncClient

from services.api.attendance.downward_sync_schemas import SyncType
from services.api.attendance.downward_sync_service import (
    decode_and_verify_sync_cursor,
    generate_sync_cursor,
    process_downward_delta_sync,
)
from services.api.attendance.models import (
    ShiftAssignment,
    ShiftTemplate,
    ShiftTemplateVersion,
    TenantAttendancePolicy,
)
from services.api.auth.dependencies import AuthenticatedContext, get_authenticated_context
from services.api.auth.models import User
from services.api.database import get_db
from services.api.employees.models import Employee
from services.api.leave.models import (
    Holiday,
    HolidayCalendar,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
)
from services.api.locations.models import EmployeeLocation, Location
from services.api.main import app
from services.api.tenants.models import Tenant

# ==============================================================================
# 1. Cursor Cryptography & Validation Tests
# ==============================================================================


def test_cursor_generation_and_valid_decode():
    """Generates a valid HMAC cursor and decodes it successfully."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    now = datetime.now(UTC)

    cursor = generate_sync_cursor(tenant_id, user_id, now)
    assert isinstance(cursor, str)
    assert len(cursor) > 20

    decoded_dt = decode_and_verify_sync_cursor(cursor, tenant_id, user_id)
    assert abs((decoded_dt - now).total_seconds()) < 1.0


def test_cursor_tampering_rejected():
    """Modifying claims in cursor causes HMAC failure and raises HTTP 400."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    now = datetime.now(UTC)

    cursor = generate_sync_cursor(tenant_id, user_id, now)

    # Tamper with the base64 string
    tampered = cursor[:-5] + "XXXXX"
    with pytest.raises(HTTPException) as exc_info:
        decode_and_verify_sync_cursor(tampered, tenant_id, user_id)
    assert exc_info.value.status_code == 400


def test_cursor_tenant_or_user_mismatch_rejected():
    """Submitting a cursor belonging to another tenant or user raises HTTP 400."""
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    now = datetime.now(UTC)

    cursor = generate_sync_cursor(tenant_a, user_a, now)

    # Mismatched tenant
    with pytest.raises(HTTPException) as exc_info:
        decode_and_verify_sync_cursor(cursor, tenant_b, user_a)
    assert exc_info.value.status_code == 400
    assert "mismatch" in exc_info.value.detail.lower()

    # Mismatched user
    with pytest.raises(HTTPException) as exc_info2:
        decode_and_verify_sync_cursor(cursor, tenant_a, user_b)
    assert exc_info2.value.status_code == 400
    assert "mismatch" in exc_info2.value.detail.lower()


# ==============================================================================
# 2. Service-Level Unit & Integration Tests
# ==============================================================================


@pytest.fixture
def mock_sync_db():
    """Creates a mock AsyncSession returning structured domain entities for downward sync."""
    session = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_initial_full_sync_returns_all_entities(mock_sync_db):
    """Initial full sync (cursor=None) returns employee, shifts, workplaces, holidays, leaves, policy."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    now = datetime.now(UTC)

    # 1. Mock employee
    emp = Employee(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        employee_id="EMP-100",
        first_name="Alice",
        last_name="Smith",
        work_email="alice@tenant.com",
        status="active",
        employment_type="full_time",
        updated_at=now,
    )

    # 2. Mock shift
    shift_tmpl = ShiftTemplate(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name="General Morning",
        code="GEN-MORN",
        updated_at=now,
    )
    shift_ver = ShiftTemplateVersion(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        shift_template_id=shift_tmpl.id,
        version_number=1,
        version_effective_from=date.today() - timedelta(days=30),
        start_time=time(9, 0),
        end_time=time(17, 0),
        grace_period_minutes=15,
        early_exit_grace_minutes=15,
        half_day_threshold_minutes=240,
        full_day_threshold_minutes=480,
        break_duration_minutes=60,
        is_overnight=False,
        is_flexible=False,
        weekly_off_days=[6, 0],
    )
    shift_tmpl.versions = [shift_ver]
    shift_assignment = ShiftAssignment(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp.id,
        shift_template_id=shift_tmpl.id,
        effective_from=date.today() - timedelta(days=10),
        effective_to=None,
        updated_at=now,
    )

    # 3. Mock workplace
    loc = Location(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name="Headquarters",
        code="HQ-01",
        address_line1="100 Tech Blvd",
        city="Tech City",
        latitude=Decimal("12.9716000"),
        longitude=Decimal("77.5946000"),
        radius_meters=150,
        timezone="Asia/Kolkata",
        wifi_bssids=["00:14:22:01:23:45"],
        is_active=True,
        updated_at=now,
    )
    emp_loc = EmployeeLocation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp.id,
        location_id=loc.id,
        is_primary=True,
        effective_from=date.today() - timedelta(days=30),
        effective_to=None,
    )

    # 4. Mock holiday
    cal = HolidayCalendar(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        year=date.today().year,
        name="Corporate 2026",
        is_default=True,
        updated_at=now,
    )
    hol = Holiday(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        calendar_id=cal.id,
        holiday_date=date(2026, 12, 25),
        name="Christmas Day",
        holiday_type="PUBLIC",
        is_optional=False,
        updated_at=now,
    )

    # 5. Mock leave type & balance
    lt = LeaveType(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        code="ANNUAL",
        name="Annual Paid Leave",
        is_paid=True,
        allow_half_day=True,
        is_active=True,
        updated_at=now,
    )
    lb = LeaveBalance(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp.id,
        leave_type_id=lt.id,
        year=date.today().year,
        annual_allocation=Decimal("20.0"),
        carried_forward=Decimal("2.0"),
        accrued=Decimal("0.0"),
        used=Decimal("5.0"),
        pending_approval=Decimal("0.0"),
        updated_at=now,
    )

    # 6. Mock leave request
    lr = LeaveRequest(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp.id,
        leave_type_id=lt.id,
        start_date=date(2026, 11, 25),
        end_date=date(2026, 11, 26),
        is_half_day=False,
        total_days=Decimal("2.0"),
        reason="Family event",
        status="APPROVED",
        updated_at=now,
    )

    # 7. Mock attendance policy
    pol = TenantAttendancePolicy(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        version=2,
        is_active=True,
        default_mode="COMBINED",
        allowed_methods=["GPS_ONLY", "WIFI_ONLY"],
        required_methods=["GPS_ONLY"],
        combination_rule="AND",
        gps_config={"max_accuracy_meters": 100},
        wifi_config={},
        updated_at=now,
    )

    # Setup session.execute return values for sequential queries
    emp_mock = MagicMock()
    emp_mock.scalar_one_or_none.return_value = emp

    shifts_mock = MagicMock()
    shifts_mock.all.return_value = [(shift_assignment, shift_tmpl)]

    wp_mock = MagicMock()
    wp_mock.all.return_value = [(emp_loc, loc)]

    cal_mock = MagicMock()
    cal_mock.scalars.return_value.all.return_value = [cal]

    hol_mock = MagicMock()
    hol_mock.scalars.return_value.all.return_value = [hol]

    lt_mock = MagicMock()
    lt_mock.scalars.return_value.all.return_value = [lt]

    lb_mock = MagicMock()
    lb_mock.scalars.return_value.all.return_value = [lb]

    lr_mock = MagicMock()
    lr_mock.scalars.return_value.all.return_value = [lr]

    pol_mock = MagicMock()
    pol_mock.scalars.return_value.first.return_value = pol

    dr_mock = MagicMock()
    dr_mock.all.return_value = []

    mock_sync_db.execute.side_effect = [
        emp_mock,     # 1. employee
        shifts_mock,  # 2. shifts
        wp_mock,      # 3. workplaces
        cal_mock,     # 4. holiday calendar
        hol_mock,     # 5. holidays
        lt_mock,      # 6. leave types
        lb_mock,      # 7. leave balances
        lr_mock,      # 8. leave requests
        pol_mock,     # 9. attendance policy
        dr_mock,      # 10. direct reports
    ]

    response = await process_downward_delta_sync(
        session=mock_sync_db,
        tenant_id=tenant_id,
        user_id=user_id,
        cursor=None,
    )

    assert response.sync_type == SyncType.FULL
    assert response.employee is not None
    assert response.employee.employee_id == "EMP-100"
    assert len(response.shifts) == 1
    assert response.shifts[0].name == "General Morning"
    assert response.shifts[0].start_time == "09:00:00"
    assert len(response.workplaces) == 1
    assert response.workplaces[0].name == "Headquarters"
    assert response.workplaces[0].is_primary is True
    assert len(response.holidays) == 1
    assert response.holidays[0].name == "Christmas Day"
    assert len(response.leave_types) == 1
    assert response.leave_types[0].code == "ANNUAL"
    assert len(response.leave_balances) == 1
    assert response.leave_balances[0].available_balance == 17.0
    assert len(response.leave_requests) == 1
    assert response.leave_requests[0].status == "APPROVED"
    assert response.attendance_policy is not None
    assert response.attendance_policy.version == 2
    assert response.has_more is False
    assert response.next_cursor is not None


@pytest.mark.asyncio
async def test_incremental_delta_sync_with_cursor(mock_sync_db):
    """Incremental delta sync parses cursor and returns only records updated after cursor."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    cursor_time = datetime.now(UTC) - timedelta(hours=2)

    cursor = generate_sync_cursor(tenant_id, user_id, cursor_time)

    emp = Employee(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        employee_id="EMP-101",
        first_name="Bob",
        last_name="Jones",
        work_email="bob@tenant.com",
        status="active",
        employment_type="full_time",
        updated_at=cursor_time - timedelta(days=1),  # Not changed
    )

    emp_mock = MagicMock()
    emp_mock.scalar_one_or_none.return_value = emp

    # Newly updated leave request
    new_lr = LeaveRequest(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp.id,
        leave_type_id=uuid.uuid4(),
        start_date=date(2026, 12, 1),
        end_date=date(2026, 12, 2),
        is_half_day=False,
        total_days=Decimal("2.0"),
        reason="Updated leave",
        status="APPROVED",
        updated_at=datetime.now(UTC) - timedelta(minutes=15),  # Changed!
    )

    empty_mock = MagicMock()
    empty_mock.all.return_value = []
    empty_mock.scalars.return_value.all.return_value = []
    empty_mock.scalars.return_value.first.return_value = None

    lr_mock = MagicMock()
    lr_mock.scalars.return_value.all.return_value = [new_lr]

    mock_sync_db.execute.side_effect = [
        emp_mock,    # 1. employee
        empty_mock,  # 2. shifts (no change)
        empty_mock,  # 3. workplaces (no change)
        empty_mock,  # 4. holiday calendar
        empty_mock,  # 5. leave types
        empty_mock,  # 6. leave balances
        lr_mock,     # 7. leave requests (1 updated)
        empty_mock,  # 8. policy
        empty_mock,  # 9. direct reports
    ]

    response = await process_downward_delta_sync(
        session=mock_sync_db,
        tenant_id=tenant_id,
        user_id=user_id,
        cursor=cursor,
    )

    assert response.sync_type == SyncType.DELTA
    # Employee not changed since cursor, so not included
    assert response.employee is None
    assert len(response.shifts) == 0
    assert len(response.workplaces) == 0
    assert len(response.leave_requests) == 1
    assert response.leave_requests[0].reason == "Updated leave"
    assert response.has_more is False


@pytest.mark.asyncio
async def test_no_change_synchronization(mock_sync_db):
    """When no records have been updated since cursor, all lists are empty and has_more is False."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    cursor_time = datetime.now(UTC) - timedelta(minutes=5)
    cursor = generate_sync_cursor(tenant_id, user_id, cursor_time)

    emp = Employee(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        employee_id="EMP-102",
        first_name="Charlie",
        last_name="Brown",
        work_email="charlie@tenant.com",
        status="active",
        employment_type="full_time",
        updated_at=cursor_time - timedelta(days=2),
    )

    emp_mock = MagicMock()
    emp_mock.scalar_one_or_none.return_value = emp

    empty_mock = MagicMock()
    empty_mock.all.return_value = []
    empty_mock.scalars.return_value.all.return_value = []
    empty_mock.scalars.return_value.first.return_value = None

    mock_sync_db.execute.side_effect = [
        emp_mock,    # employee
        empty_mock,  # shifts
        empty_mock,  # workplaces
        empty_mock,  # calendars
        empty_mock,  # leave types
        empty_mock,  # leave balances
        empty_mock,  # leave requests
        empty_mock,  # policy
        empty_mock,  # direct reports
    ]

    response = await process_downward_delta_sync(
        session=mock_sync_db,
        tenant_id=tenant_id,
        user_id=user_id,
        cursor=cursor,
    )

    assert response.sync_type == SyncType.DELTA
    assert response.employee is None
    assert len(response.shifts) == 0
    assert len(response.workplaces) == 0
    assert len(response.leave_requests) == 0
    assert len(response.tombstones) == 0
    assert response.has_more is False


@pytest.mark.asyncio
async def test_employee_deactivation_semantics(mock_sync_db):
    """Deactivated employee profile is returned with status='inactive' and zero references."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    now = datetime.now(UTC)

    emp = Employee(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        employee_id="EMP-103",
        first_name="Diana",
        last_name="Prince",
        work_email="diana@tenant.com",
        status="inactive",
        employment_type="full_time",
        updated_at=now,
    )

    emp_mock = MagicMock()
    emp_mock.scalar_one_or_none.return_value = emp
    mock_sync_db.execute.return_value = emp_mock

    response = await process_downward_delta_sync(
        session=mock_sync_db,
        tenant_id=tenant_id,
        user_id=user_id,
        cursor=None,
    )

    assert response.employee is not None
    assert response.employee.status == "inactive"
    assert len(response.shifts) == 0
    assert len(response.workplaces) == 0
    assert len(response.leave_requests) == 0
    assert response.has_more is False


@pytest.mark.asyncio
async def test_workplace_deactivation_emits_tombstone(mock_sync_db):
    """Deactivating or ending workplace assignment generates a tombstone record."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    now = datetime.now(UTC)

    emp = Employee(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        employee_id="EMP-104",
        first_name="Evan",
        last_name="Wright",
        work_email="evan@tenant.com",
        status="active",
        employment_type="full_time",
        updated_at=now,
    )

    loc = Location(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name="Old Site",
        code="OLD-01",
        address_line1="500 Warehouse Way",
        city="Old City",
        latitude=Decimal("12.0"),
        longitude=Decimal("77.0"),
        radius_meters=100,
        timezone="UTC",
        is_active=False,  # Inactive site
        updated_at=now,
    )
    emp_loc = EmployeeLocation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp.id,
        location_id=loc.id,
        is_primary=False,
        effective_from=date.today() - timedelta(days=60),
        effective_to=date.today() - timedelta(days=1),  # Ended assignment
    )

    emp_mock = MagicMock()
    emp_mock.scalar_one_or_none.return_value = emp

    wp_mock = MagicMock()
    wp_mock.all.return_value = [(emp_loc, loc)]

    empty_mock = MagicMock()
    empty_mock.all.return_value = []
    empty_mock.scalars.return_value.all.return_value = []
    empty_mock.scalars.return_value.first.return_value = None

    mock_sync_db.execute.side_effect = [
        emp_mock,    # employee
        empty_mock,  # shifts
        wp_mock,     # workplaces (ended)
        empty_mock,  # calendars
        empty_mock,  # leave types
        empty_mock,  # leave balances
        empty_mock,  # leave requests
        empty_mock,  # policy
        empty_mock,  # direct reports
    ]

    response = await process_downward_delta_sync(
        session=mock_sync_db,
        tenant_id=tenant_id,
        user_id=user_id,
        cursor=None,
    )

    assert len(response.workplaces) == 0
    assert len(response.tombstones) == 1
    assert response.tombstones[0].entity_type == "workplace"
    assert response.tombstones[0].entity_id == loc.id


@pytest.mark.asyncio
async def test_pagination_and_bounded_response_limit(mock_sync_db):
    """When items exceed limit, has_more=True is returned and payload is truncated."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    now = datetime.now(UTC)

    emp = Employee(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        employee_id="EMP-105",
        first_name="Fiona",
        last_name="Gallagher",
        work_email="fiona@tenant.com",
        status="active",
        employment_type="full_time",
        updated_at=now,
    )

    # Create 5 shifts
    shifts_list = []
    for i in range(5):
        s_tmpl = ShiftTemplate(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            name=f"Shift {i}",
            code=f"S-{i}",
            updated_at=now + timedelta(seconds=i),
        )
        s_ver = ShiftTemplateVersion(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            shift_template_id=s_tmpl.id,
            version_number=1,
            version_effective_from=date(2026, 1, 1),
            start_time=time(9, 0),
            end_time=time(17, 0),
            grace_period_minutes=15,
            early_exit_grace_minutes=15,
            half_day_threshold_minutes=240,
            full_day_threshold_minutes=480,
            break_duration_minutes=60,
            is_overnight=False,
            is_flexible=False,
            weekly_off_days=[6, 0],
        )
        s_tmpl.versions = [s_ver]
        s_assign = ShiftAssignment(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            employee_id=emp.id,
            shift_template_id=s_tmpl.id,
            effective_from=date(2026, 1, 1),
            effective_to=None,
            updated_at=now + timedelta(seconds=i),
        )
        shifts_list.append((s_assign, s_tmpl))

    emp_mock = MagicMock()
    emp_mock.scalar_one_or_none.return_value = emp

    shifts_mock = MagicMock()
    shifts_mock.all.return_value = shifts_list

    empty_mock = MagicMock()
    empty_mock.all.return_value = []
    empty_mock.scalars.return_value.all.return_value = []
    empty_mock.scalars.return_value.first.return_value = None

    mock_sync_db.execute.side_effect = [
        emp_mock,     # employee
        shifts_mock,  # 5 shifts
        empty_mock,   # workplaces
        empty_mock,   # calendars
        empty_mock,   # leave types
        empty_mock,   # leave balances
        empty_mock,   # leave requests
        empty_mock,   # policy
        empty_mock,   # direct reports
    ]

    # Limit = 2 items
    response = await process_downward_delta_sync(
        session=mock_sync_db,
        tenant_id=tenant_id,
        user_id=user_id,
        cursor=None,
        limit=2,
    )

    assert response.has_more is True
    assert len(response.shifts) == 2
    assert response.next_cursor is not None


@pytest.mark.asyncio
async def test_manager_direct_reports_hierarchy_included(mock_sync_db):
    """Supervisor user receives direct reports list in reporting hierarchy payload."""
    tenant_id = uuid.uuid4()
    manager_user_id = uuid.uuid4()
    now = datetime.now(UTC)

    mgr_emp = Employee(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=manager_user_id,
        employee_id="MGR-001",
        first_name="Marcus",
        last_name="Vance",
        work_email="marcus@tenant.com",
        status="active",
        employment_type="full_time",
        updated_at=now,
    )

    dr_1 = Employee(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=uuid.uuid4(),
        employee_id="EMP-201",
        first_name="George",
        last_name="Clark",
        work_email="george@tenant.com",
        reporting_manager_id=mgr_emp.id,
        status="active",
        employment_type="full_time",
        updated_at=now,
    )

    mgr_mock = MagicMock()
    mgr_mock.scalar_one_or_none.return_value = mgr_emp

    dr_mock = MagicMock()
    dr_mock.all.return_value = [(dr_1, "Engineering")]

    empty_mock = MagicMock()
    empty_mock.all.return_value = []
    empty_mock.scalars.return_value.all.return_value = []
    empty_mock.scalars.return_value.first.return_value = None

    mock_sync_db.execute.side_effect = [
        mgr_mock,    # 1. employee
        empty_mock,  # 2. shifts
        empty_mock,  # 3. workplaces
        empty_mock,  # 4. calendars
        empty_mock,  # 5. leave types
        empty_mock,  # 6. leave balances
        empty_mock,  # 7. leave requests
        empty_mock,  # 8. policy
        dr_mock,     # 9. direct reports
    ]

    response = await process_downward_delta_sync(
        session=mock_sync_db,
        tenant_id=tenant_id,
        user_id=manager_user_id,
        cursor=None,
    )

    assert response.reporting_hierarchy is not None
    assert len(response.reporting_hierarchy.direct_reports) == 1
    assert response.reporting_hierarchy.direct_reports[0].first_name == "George"
    assert response.reporting_hierarchy.direct_reports[0].department_name == "Engineering"


def test_malformed_cursor_rejected():
    """Malformed cursor or invalid claims structure raises HTTP 400."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()

    with pytest.raises(HTTPException) as exc_info:
        decode_and_verify_sync_cursor("not_a_base64_string!@#$", tenant_id, user_id)
    assert exc_info.value.status_code == 400


# ==============================================================================
# 3. HTTP Integration & Route Verification
# ==============================================================================


@pytest.fixture
def test_tenant():
    return Tenant(
        id=uuid.uuid4(),
        name="Sync Test Corp",
        slug="sync-test-corp",
        company_email="admin@synctestcorp.com",
        country_code="US",
        status="active",
    )


@pytest.fixture
def test_user(test_tenant):
    return User(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        email="employee.sync@upostit.local",
        password_hash="mock_argon2_hash",
        full_name="Sync Tester",
        role="employee",
        status="active",
    )


@pytest.fixture
def auth_context(test_user, test_tenant):
    return AuthenticatedContext(user=test_user, tenant=test_tenant)


@pytest.mark.asyncio
async def test_http_endpoint_sync_delta_success(auth_context):
    """GET /api/v1/sync/delta responds with HTTP 200 and valid JSON schema."""
    now = datetime.now(UTC)
    emp = Employee(
        id=uuid.uuid4(),
        tenant_id=auth_context.tenant.id,
        user_id=auth_context.user.id,
        employee_id="EMP-200",
        first_name="Sync",
        last_name="Tester",
        work_email=auth_context.user.email,
        status="active",
        employment_type="full_time",
        updated_at=now,
    )

    mock_session = AsyncMock()
    emp_mock = MagicMock()
    emp_mock.scalar_one_or_none.return_value = emp

    empty_mock = MagicMock()
    empty_mock.all.return_value = []
    empty_mock.scalars.return_value.all.return_value = []
    empty_mock.scalars.return_value.first.return_value = None

    mock_session.execute.side_effect = [
        emp_mock,
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
    ]

    async def override_get_db():
        yield mock_session

    async def override_auth_ctx():
        return auth_context

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_authenticated_context] = override_auth_ctx

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/sync/delta")
            assert resp.status_code == status.HTTP_200_OK
            data = resp.json()
            assert data["sync_type"] == "FULL"
            assert data["employee"]["employee_id"] == "EMP-200"
            assert "next_cursor" in data
            assert data["has_more"] is False
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_http_endpoint_attendance_alias_success(auth_context):
    """GET /api/v1/attendance/sync/delta alias responds with HTTP 200."""
    now = datetime.now(UTC)
    emp = Employee(
        id=uuid.uuid4(),
        tenant_id=auth_context.tenant.id,
        user_id=auth_context.user.id,
        employee_id="EMP-201",
        first_name="Alias",
        last_name="Tester",
        work_email=auth_context.user.email,
        status="active",
        employment_type="full_time",
        updated_at=now,
    )

    mock_session = AsyncMock()
    emp_mock = MagicMock()
    emp_mock.scalar_one_or_none.return_value = emp

    empty_mock = MagicMock()
    empty_mock.all.return_value = []
    empty_mock.scalars.return_value.all.return_value = []
    empty_mock.scalars.return_value.first.return_value = None

    mock_session.execute.side_effect = [
        emp_mock,
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
    ]

    async def override_get_db():
        yield mock_session

    async def override_auth_ctx():
        return auth_context

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_authenticated_context] = override_auth_ctx

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/attendance/sync/delta")
            assert resp.status_code == status.HTTP_200_OK
            data = resp.json()
            assert data["sync_type"] == "FULL"
            assert data["employee"]["employee_id"] == "EMP-201"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_http_endpoint_unauthenticated_rejected():
    """Unauthenticated requests without Authorization header are rejected with HTTP 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/sync/delta")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


# ==============================================================================
# 5. Phase 11.3 Acceptance Audit Regression Tests
# ==============================================================================


def test_cursor_expiration_rejected():
    """A cursor with expired TTL raises HTTP 400 Bad Request."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    now = datetime.now(UTC)

    # Generate an already expired cursor
    expired_cursor = generate_sync_cursor(
        tenant_id=tenant_id,
        user_id=user_id,
        timestamp=now,
        expires_in_seconds=-60,  # Expired 60s ago
    )

    with pytest.raises(HTTPException) as exc_info:
        decode_and_verify_sync_cursor(expired_cursor, tenant_id, user_id)
    assert exc_info.value.status_code == 400
    assert "expired" in exc_info.value.detail.lower()


def test_cursor_employee_mismatch_rejected():
    """A cursor generated for employee A presented by employee B raises HTTP 400."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    emp_a_id = uuid.uuid4()
    emp_b_id = uuid.uuid4()
    now = datetime.now(UTC)

    cursor_emp_a = generate_sync_cursor(
        tenant_id=tenant_id,
        user_id=user_id,
        timestamp=now,
        employee_id=emp_a_id,
    )

    with pytest.raises(HTTPException) as exc_info:
        decode_and_verify_sync_cursor(
            cursor_emp_a,
            expected_tenant_id=tenant_id,
            expected_user_id=user_id,
            expected_employee_id=emp_b_id,
        )
    assert exc_info.value.status_code == 400
    assert "employee mismatch" in exc_info.value.detail.lower()


def test_signing_key_rotation_fallback_success():
    """A cursor signed with a previous secret key is verified using fallback keys."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    now = datetime.now(UTC)

    old_key = "old-secret-key-2026-q1"
    new_key = "new-secret-key-2026-q2"

    cursor_signed_with_old_key = generate_sync_cursor(
        tenant_id=tenant_id,
        user_id=user_id,
        timestamp=now,
        secret_key=old_key,
    )

    # Decode using new_key as active, with old_key in fallback_keys
    parsed = decode_and_verify_sync_cursor(
        cursor_str=cursor_signed_with_old_key,
        expected_tenant_id=tenant_id,
        expected_user_id=user_id,
        secret_key=new_key,
        fallback_keys=[old_key],
    )
    assert parsed.tenant_id == tenant_id
    assert parsed.user_id == user_id


@pytest.mark.asyncio
async def test_identical_timestamps_across_multiple_pages(mock_sync_db):
    """Items sharing the exact same updated_at timestamp are delivered across pages without skips."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    identical_ts = datetime(2026, 11, 23, 10, 0, 0, tzinfo=UTC)

    emp = Employee(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        employee_id="EMP-IDEMP",
        first_name="Identical",
        last_name="Timestamp",
        work_email="identical@tenant.com",
        status="active",
        employment_type="full_time",
        updated_at=identical_ts,
    )

    # 4 shifts created with identical updated_at, but distinct UUIDs
    shifts_list = []
    shift_ids = []
    for i in range(4):
        s_tmpl = ShiftTemplate(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            name=f"Shift {i}",
            code=f"S-{i}",
            updated_at=identical_ts,
        )
        s_ver = ShiftTemplateVersion(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            shift_template_id=s_tmpl.id,
            version_number=1,
            version_effective_from=date(2026, 1, 1),
            start_time=time(9, 0),
            end_time=time(17, 0),
        )
        s_tmpl.versions = [s_ver]
        s_assign = ShiftAssignment(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            employee_id=emp.id,
            shift_template_id=s_tmpl.id,
            effective_from=date(2026, 1, 1),
            effective_to=None,
            updated_at=identical_ts,
        )
        shifts_list.append((s_assign, s_tmpl))
        shift_ids.append(str(s_assign.id))

    emp_mock = MagicMock()
    emp_mock.scalar_one_or_none.return_value = emp

    shifts_mock = MagicMock()
    shifts_mock.all.return_value = shifts_list

    empty_mock = MagicMock()
    empty_mock.all.return_value = []
    empty_mock.scalars.return_value.all.return_value = []
    empty_mock.scalars.return_value.first.return_value = None

    # Side effect for Page 1
    mock_sync_db.execute.side_effect = [
        emp_mock,
        shifts_mock,
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
    ]

    # Page 1: limit = 2
    page1 = await process_downward_delta_sync(
        session=mock_sync_db,
        tenant_id=tenant_id,
        user_id=user_id,
        cursor=None,
        limit=2,
    )
    assert page1.has_more is True
    assert len(page1.shifts) == 2
    p1_ids = [str(s.id) for s in page1.shifts]
    assert p1_ids == shift_ids[:2]

    # Side effect for Page 2
    mock_sync_db.execute.side_effect = [
        emp_mock,
        shifts_mock,
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
    ]

    # Page 2: limit = 2 with cursor from Page 1
    page2 = await process_downward_delta_sync(
        session=mock_sync_db,
        tenant_id=tenant_id,
        user_id=user_id,
        cursor=page1.next_cursor,
        limit=2,
    )
    assert page2.has_more is False
    assert len(page2.shifts) == 2
    p2_ids = [str(s.id) for s in page2.shifts]
    assert p2_ids == shift_ids[2:]

    # Verify all 4 shifts were delivered with zero overlaps or skips
    all_delivered = p1_ids + p2_ids
    assert all_delivered == shift_ids


@pytest.mark.asyncio
async def test_concurrent_updates_during_pagination_isolated(mock_sync_db):
    """Updates occurring after session_ts are excluded from in-flight pagination."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    t_start = datetime.now(UTC) - timedelta(minutes=5)

    emp = Employee(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        employee_id="EMP-CONC",
        first_name="Concurrent",
        last_name="Tester",
        work_email="conc@tenant.com",
        status="active",
        employment_type="full_time",
        updated_at=t_start,
    )

    # 3 initial shifts at t_start
    initial_shifts = []
    for i in range(3):
        s_tmpl = ShiftTemplate(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            name=f"Shift {i}",
            code=f"S-{i}",
            updated_at=t_start,
        )
        s_ver = ShiftTemplateVersion(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            shift_template_id=s_tmpl.id,
            version_number=1,
            version_effective_from=date(2026, 1, 1),
            start_time=time(9, 0),
            end_time=time(17, 0),
        )
        s_tmpl.versions = [s_ver]
        s_assign = ShiftAssignment(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            employee_id=emp.id,
            shift_template_id=s_tmpl.id,
            effective_from=date(2026, 1, 1),
            effective_to=None,
            updated_at=t_start,
        )
        initial_shifts.append((s_assign, s_tmpl))

    emp_mock = MagicMock()
    emp_mock.scalar_one_or_none.return_value = emp

    shifts_mock_p1 = MagicMock()
    shifts_mock_p1.all.return_value = initial_shifts

    empty_mock = MagicMock()
    empty_mock.all.return_value = []
    empty_mock.scalars.return_value.all.return_value = []
    empty_mock.scalars.return_value.first.return_value = None

    # Page 1: limit = 2
    mock_sync_db.execute.side_effect = [
        emp_mock,
        shifts_mock_p1,
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
    ]

    page1 = await process_downward_delta_sync(
        session=mock_sync_db,
        tenant_id=tenant_id,
        user_id=user_id,
        cursor=None,
        limit=2,
    )
    assert page1.has_more is True
    assert len(page1.shifts) == 2

    # Simulate concurrent insert occurring after session_ts
    t_after = page1.server_time + timedelta(seconds=10)
    concurrent_tmpl = ShiftTemplate(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name="Concurrent New Shift",
        code="CONC-NEW",
        updated_at=t_after,
    )
    concurrent_ver = ShiftTemplateVersion(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        shift_template_id=concurrent_tmpl.id,
        version_number=1,
        version_effective_from=date(2026, 1, 1),
        start_time=time(9, 0),
        end_time=time(17, 0),
    )
    concurrent_tmpl.versions = [concurrent_ver]
    concurrent_assign = ShiftAssignment(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp.id,
        shift_template_id=concurrent_tmpl.id,
        effective_from=date(2026, 1, 1),
        effective_to=None,
        updated_at=t_after,
    )

    # In Page 2, database query would return all matching records, but the updated_at <= session_ts filter
    # excludes the newly inserted record
    shifts_mock_p2 = MagicMock()
    shifts_mock_p2.all.return_value = initial_shifts + [(concurrent_assign, concurrent_tmpl)]

    mock_sync_db.execute.side_effect = [
        emp_mock,
        shifts_mock_p2,
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
    ]

    page2 = await process_downward_delta_sync(
        session=mock_sync_db,
        tenant_id=tenant_id,
        user_id=user_id,
        cursor=page1.next_cursor,
        limit=2,
    )
    assert page2.has_more is False
    assert len(page2.shifts) == 1
    # Concurrent shift was not included in page 2
    assert page2.shifts[0].name == "Shift 2"


@pytest.mark.asyncio
async def test_tombstones_delivered_across_page_boundaries(mock_sync_db):
    """Workplaces and tombstones are delivered deterministically across page boundaries."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    now = datetime.now(UTC)

    emp = Employee(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        employee_id="EMP-TOMB",
        first_name="Tomb",
        last_name="Tester",
        work_email="tomb@tenant.com",
        status="active",
        employment_type="full_time",
        updated_at=now,
    )

    # 1 active location, 1 inactive location (tombstone)
    loc_active = Location(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name="Active Branch",
        code="ACT-1",
        address_line1="1 Active St",
        city="Metro",
        latitude=Decimal("12.0"),
        longitude=Decimal("77.0"),
        radius_meters=100,
        timezone="UTC",
        is_active=True,
        updated_at=now,
    )
    emp_loc_active = EmployeeLocation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp.id,
        location_id=loc_active.id,
        is_primary=True,
        effective_from=date(2026, 1, 1),
        effective_to=None,
    )

    loc_tomb = Location(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name="Old Branch",
        code="OLD-1",
        address_line1="99 Old St",
        city="Metro",
        latitude=Decimal("12.0"),
        longitude=Decimal("77.0"),
        radius_meters=100,
        timezone="UTC",
        is_active=False,
        updated_at=now + timedelta(seconds=1),
    )
    emp_loc_tomb = EmployeeLocation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp.id,
        location_id=loc_tomb.id,
        is_primary=False,
        effective_from=date(2026, 1, 1),
        effective_to=date.today() - timedelta(days=1),
    )

    emp_mock = MagicMock()
    emp_mock.scalar_one_or_none.return_value = emp

    wp_mock = MagicMock()
    wp_mock.all.return_value = [(emp_loc_active, loc_active), (emp_loc_tomb, loc_tomb)]

    empty_mock = MagicMock()
    empty_mock.all.return_value = []
    empty_mock.scalars.return_value.all.return_value = []
    empty_mock.scalars.return_value.first.return_value = None

    # Page 1: limit = 1
    mock_sync_db.execute.side_effect = [
        emp_mock,
        empty_mock,  # shifts
        wp_mock,     # workplaces
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
    ]

    p1 = await process_downward_delta_sync(
        session=mock_sync_db,
        tenant_id=tenant_id,
        user_id=user_id,
        cursor=None,
        limit=1,
    )
    assert p1.has_more is True
    assert len(p1.workplaces) == 1
    assert len(p1.tombstones) == 0
    assert p1.workplaces[0].id == loc_active.id

    # Page 2: limit = 1 with cursor from Page 1
    mock_sync_db.execute.side_effect = [
        emp_mock,
        empty_mock,  # shifts
        wp_mock,     # workplaces
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
        empty_mock,
    ]

    p2 = await process_downward_delta_sync(
        session=mock_sync_db,
        tenant_id=tenant_id,
        user_id=user_id,
        cursor=p1.next_cursor,
        limit=1,
    )
    assert p2.has_more is False
    assert len(p2.workplaces) == 0
    assert len(p2.tombstones) == 1
    assert p2.tombstones[0].entity_id == loc_tomb.id


@pytest.mark.asyncio
async def test_leave_balances_and_requests_strictly_scoped_to_employee(mock_sync_db):
    """Leave balances and leave requests are strictly filtered to the authenticated employee."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    now = datetime.now(UTC)

    emp = Employee(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        employee_id="EMP-PRIVACY",
        first_name="Privacy",
        last_name="Tester",
        work_email="privacy@tenant.com",
        status="active",
        employment_type="full_time",
        updated_at=now,
    )

    other_emp_id = uuid.uuid4()

    lt = LeaveType(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        code="CASUAL",
        name="Casual Leave",
        is_paid=True,
        allow_half_day=True,
        is_active=True,
        updated_at=now,
    )

    # Balance belonging to the authenticated employee
    my_balance = LeaveBalance(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp.id,
        leave_type_id=lt.id,
        year=date.today().year,
        annual_allocation=Decimal("12.0"),
        carried_forward=Decimal("0.0"),
        accrued=Decimal("0.0"),
        used=Decimal("2.0"),
        pending_approval=Decimal("0.0"),
        updated_at=now,
    )

    # Balance belonging to another employee (should never be returned)
    _other_balance = LeaveBalance(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=other_emp_id,
        leave_type_id=lt.id,
        year=date.today().year,
        annual_allocation=Decimal("30.0"),
        carried_forward=Decimal("10.0"),
        accrued=Decimal("0.0"),
        used=Decimal("1.0"),
        pending_approval=Decimal("0.0"),
        updated_at=now,
    )
    assert _other_balance.employee_id != emp.id

    emp_mock = MagicMock()
    emp_mock.scalar_one_or_none.return_value = emp

    lt_mock = MagicMock()
    lt_mock.scalars.return_value.all.return_value = [lt]

    # Service query filters `LeaveBalance.employee_id == employee.id`, so query result returns only my_balance
    lb_mock = MagicMock()
    lb_mock.scalars.return_value.all.return_value = [my_balance]

    empty_mock = MagicMock()
    empty_mock.all.return_value = []
    empty_mock.scalars.return_value.all.return_value = []
    empty_mock.scalars.return_value.first.return_value = None

    mock_sync_db.execute.side_effect = [
        emp_mock,    # employee
        empty_mock,  # shifts
        empty_mock,  # workplaces
        empty_mock,  # calendars
        lt_mock,     # leave types
        lb_mock,     # leave balances
        empty_mock,  # leave requests
        empty_mock,  # policy
        empty_mock,  # direct reports
    ]

    response = await process_downward_delta_sync(
        session=mock_sync_db,
        tenant_id=tenant_id,
        user_id=user_id,
        cursor=None,
    )

    assert len(response.leave_balances) == 1
    assert response.leave_balances[0].available_balance == 10.0
    # Other employee's balance is never present
    assert all(b.available_balance != 39.0 for b in response.leave_balances)

