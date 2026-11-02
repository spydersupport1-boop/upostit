"""Comprehensive unit and API integration tests for Phase 4 Milestone 2 Employee Workplace Assignments."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError

from services.api.auth.dependencies import AuthenticatedContext, get_authenticated_context
from services.api.auth.models import User
from services.api.database import get_db
from services.api.employees.models import Employee
from services.api.locations.assignment_service import (
    assign_workplace_to_employee,
    end_employee_workplace_assignment,
    get_my_workplaces,
    list_employee_workplaces,
    list_location_employees,
    update_employee_workplace_assignment,
)
from services.api.locations.models import EmployeeLocation, Location
from services.api.locations.schemas import (
    EmployeeWorkplaceAssignRequest,
    EmployeeWorkplaceUpdateRequest,
)
from services.api.main import app
from services.api.tenants.models import Tenant


def _mock_context(
    role: str, tenant_id: uuid.UUID | None = None, user_id: uuid.UUID | None = None
) -> AuthenticatedContext:
    tid = tenant_id or uuid.uuid4()
    uid = user_id or uuid.uuid4()
    user = User(
        id=uid,
        tenant_id=tid,
        email=f"test_{role}@corp.test",
        password_hash="argon2id$mock",
        role=role,
        status="active",
    )
    tenant = Tenant(
        id=tid,
        name="Test Corp",
        slug=f"test-{tid.hex[:6]}",
        company_email="admin@corp.test",
        country_code="IN",
        status="active",
    )
    return AuthenticatedContext(user=user, tenant=tenant)


def _create_mock_employee(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID | None = None,
    status: str = "active",
    user_id: uuid.UUID | None = None,
) -> Employee:
    emp_uuid = employee_id or uuid.uuid4()
    return Employee(
        id=emp_uuid,
        tenant_id=tenant_id,
        user_id=user_id,
        employee_id="EMP-001",
        first_name="Jane",
        last_name="Doe",
        work_email="jane.doe@corp.test",
        employment_type="full_time",
        joining_date=date(2025, 1, 1),
        status=status,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _create_mock_location(
    tenant_id: uuid.UUID,
    location_id: uuid.UUID | None = None,
    is_active: bool = True,
    name: str = "Headquarters",
    code: str = "HQ-01",
) -> Location:
    loc_uuid = location_id or uuid.uuid4()
    return Location(
        id=loc_uuid,
        tenant_id=tenant_id,
        name=name,
        code=code,
        address_line1="100 Tech Park",
        city="Bengaluru",
        country_code="IN",
        latitude=Decimal("12.9249000"),
        longitude=Decimal("77.6744000"),
        radius_meters=150,
        timezone="Asia/Kolkata",
        wifi_bssids=[],
        ip_ranges=[],
        is_active=is_active,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


# ============================================================================
# Service Layer Unit Tests
# ============================================================================


@pytest.mark.asyncio
async def test_assign_workplace_success():
    """Verify successfully assigning a workplace to an active employee."""
    session = AsyncMock()
    session.add = MagicMock()
    tenant_id = uuid.uuid4()
    emp = _create_mock_employee(tenant_id)
    loc = _create_mock_location(tenant_id)

    # 1. Employee query -> returns emp
    # 2. Location query -> returns loc
    # 3. Duplicate check -> returns None
    # 4. Primary check -> returns empty
    res_emp = MagicMock()
    res_emp.scalar_one_or_none.return_value = emp
    res_loc = MagicMock()
    res_loc.scalar_one_or_none.return_value = loc
    res_dup = MagicMock()
    res_dup.scalar_one_or_none.return_value = None
    res_primaries = MagicMock()
    res_primaries.all.return_value = []

    session.execute.side_effect = [res_emp, res_loc, res_dup, res_primaries]

    req = EmployeeWorkplaceAssignRequest(
        location_id=loc.id,
        is_primary=True,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 6, 30),
    )
    result = await assign_workplace_to_employee(session, tenant_id, emp.id, req)

    assert result.employee_id == emp.id
    assert result.location_id == loc.id
    assert result.is_primary is True
    assert result.effective_from == date(2026, 1, 1)
    assert result.effective_to == date(2026, 6, 30)
    assert session.commit.called


@pytest.mark.asyncio
async def test_assign_workplace_employee_not_found():
    """Verify assigning a workplace raises 404 when employee does not exist in tenant."""
    session = AsyncMock()
    tenant_id = uuid.uuid4()

    res_emp = MagicMock()
    res_emp.scalar_one_or_none.return_value = None
    session.execute.return_value = res_emp

    req = EmployeeWorkplaceAssignRequest(location_id=uuid.uuid4(), is_primary=False)
    with pytest.raises(HTTPException) as exc:
        await assign_workplace_to_employee(session, tenant_id, uuid.uuid4(), req)
    assert exc.value.status_code == 404
    assert "Employee not found" in exc.value.detail


@pytest.mark.asyncio
async def test_assign_workplace_inactive_employee_rejected():
    """Verify assigning a workplace to an inactive employee raises HTTP 400."""
    session = AsyncMock()
    tenant_id = uuid.uuid4()
    emp = _create_mock_employee(tenant_id, status="inactive")

    res_emp = MagicMock()
    res_emp.scalar_one_or_none.return_value = emp
    session.execute.return_value = res_emp

    req = EmployeeWorkplaceAssignRequest(location_id=uuid.uuid4(), is_primary=False)
    with pytest.raises(HTTPException) as exc:
        await assign_workplace_to_employee(session, tenant_id, emp.id, req)
    assert exc.value.status_code == 400
    assert "inactive employee" in exc.value.detail


@pytest.mark.asyncio
async def test_assign_workplace_location_not_found():
    """Verify assigning a non-existent or cross-tenant workplace raises HTTP 404."""
    session = AsyncMock()
    tenant_id = uuid.uuid4()
    emp = _create_mock_employee(tenant_id)

    res_emp = MagicMock()
    res_emp.scalar_one_or_none.return_value = emp
    res_loc = MagicMock()
    res_loc.scalar_one_or_none.return_value = None
    session.execute.side_effect = [res_emp, res_loc]

    req = EmployeeWorkplaceAssignRequest(location_id=uuid.uuid4(), is_primary=False)
    with pytest.raises(HTTPException) as exc:
        await assign_workplace_to_employee(session, tenant_id, emp.id, req)
    assert exc.value.status_code == 404
    assert "Workplace location not found" in exc.value.detail


@pytest.mark.asyncio
async def test_assign_workplace_inactive_location_rejected():
    """Verify assigning an inactive workplace raises HTTP 400."""
    session = AsyncMock()
    tenant_id = uuid.uuid4()
    emp = _create_mock_employee(tenant_id)
    loc = _create_mock_location(tenant_id, is_active=False)

    res_emp = MagicMock()
    res_emp.scalar_one_or_none.return_value = emp
    res_loc = MagicMock()
    res_loc.scalar_one_or_none.return_value = loc
    session.execute.side_effect = [res_emp, res_loc]

    req = EmployeeWorkplaceAssignRequest(location_id=loc.id, is_primary=False)
    with pytest.raises(HTTPException) as exc:
        await assign_workplace_to_employee(session, tenant_id, emp.id, req)
    assert exc.value.status_code == 400
    assert "inactive workplace location" in exc.value.detail


@pytest.mark.asyncio
async def test_assign_workplace_duplicate_assignment_rejected():
    """Verify duplicate assignment on the same start date raises HTTP 409."""
    session = AsyncMock()
    tenant_id = uuid.uuid4()
    emp = _create_mock_employee(tenant_id)
    loc = _create_mock_location(tenant_id)

    res_emp = MagicMock()
    res_emp.scalar_one_or_none.return_value = emp
    res_loc = MagicMock()
    res_loc.scalar_one_or_none.return_value = loc
    res_dup = MagicMock()
    res_dup.scalar_one_or_none.return_value = uuid.uuid4()  # Existing assignment found

    session.execute.side_effect = [res_emp, res_loc, res_dup]

    req = EmployeeWorkplaceAssignRequest(
        location_id=loc.id,
        effective_from=date(2026, 1, 1),
    )
    with pytest.raises(HTTPException) as exc:
        await assign_workplace_to_employee(session, tenant_id, emp.id, req)
    assert exc.value.status_code == 409
    assert "already exists" in exc.value.detail


@pytest.mark.asyncio
async def test_assign_workplace_overlapping_primary_rejected():
    """Verify overlapping primary workplace assignment raises HTTP 409."""
    session = AsyncMock()
    tenant_id = uuid.uuid4()
    emp = _create_mock_employee(tenant_id)
    loc1 = _create_mock_location(tenant_id, name="Location One")
    loc2 = _create_mock_location(tenant_id, name="Location Two")

    existing_assignment = EmployeeLocation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp.id,
        location_id=loc1.id,
        is_primary=True,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 1, 31),
    )

    res_emp = MagicMock()
    res_emp.scalar_one_or_none.return_value = emp
    res_loc = MagicMock()
    res_loc.scalar_one_or_none.return_value = loc2
    res_dup = MagicMock()
    res_dup.scalar_one_or_none.return_value = None
    res_primaries = MagicMock()
    res_primaries.all.return_value = [(existing_assignment, loc1)]

    session.execute.side_effect = [res_emp, res_loc, res_dup, res_primaries]

    # Try assigning primary for overlapping dates: Jan 15 - Feb 15
    req = EmployeeWorkplaceAssignRequest(
        location_id=loc2.id,
        is_primary=True,
        effective_from=date(2026, 1, 15),
        effective_to=date(2026, 2, 15),
    )
    with pytest.raises(HTTPException) as exc:
        await assign_workplace_to_employee(session, tenant_id, emp.id, req)
    assert exc.value.status_code == 409
    assert "Conflicting primary assignment" in exc.value.detail
    assert "Location One" in exc.value.detail


@pytest.mark.asyncio
async def test_assign_workplace_database_exclusion_constraint_handling():
    """Verify exclusion constraint IntegrityError on commit is translated to clean HTTP 409."""
    session = AsyncMock()
    session.add = MagicMock()
    tenant_id = uuid.uuid4()
    emp = _create_mock_employee(tenant_id)
    loc = _create_mock_location(tenant_id)

    res_emp = MagicMock()
    res_emp.scalar_one_or_none.return_value = emp
    res_loc = MagicMock()
    res_loc.scalar_one_or_none.return_value = loc
    res_dup = MagicMock()
    res_dup.scalar_one_or_none.return_value = None
    res_primaries = MagicMock()
    res_primaries.all.return_value = []

    session.execute.side_effect = [res_emp, res_loc, res_dup, res_primaries]
    # Simulate DB-level exclusion constraint violation
    session.commit.side_effect = IntegrityError(
        statement="INSERT INTO employee_locations",
        params={},
        orig=Exception('violates exclusion constraint "excl_emp_primary_workplace_overlap"'),
    )

    req = EmployeeWorkplaceAssignRequest(
        location_id=loc.id,
        is_primary=True,
        effective_from=date(2026, 1, 1),
    )
    with pytest.raises(HTTPException) as exc:
        await assign_workplace_to_employee(session, tenant_id, emp.id, req)
    assert exc.value.status_code == 409
    assert "An employee can have only one primary workplace" in exc.value.detail


@pytest.mark.asyncio
async def test_update_workplace_assignment_success():
    """Verify updating assignment dates and primary status."""
    session = AsyncMock()
    tenant_id = uuid.uuid4()
    emp = _create_mock_employee(tenant_id)
    loc = _create_mock_location(tenant_id)
    assignment = EmployeeLocation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp.id,
        location_id=loc.id,
        is_primary=False,
        effective_from=date(2026, 1, 1),
        effective_to=None,
        created_at=datetime.now(UTC),
    )

    res_emp = MagicMock()
    res_emp.scalar_one_or_none.return_value = emp.id
    res_assign = MagicMock()
    res_assign.one_or_none.return_value = (assignment, loc)
    res_primaries = MagicMock()
    res_primaries.all.return_value = []

    session.execute.side_effect = [res_emp, res_assign, res_primaries]

    req = EmployeeWorkplaceUpdateRequest(
        is_primary=True,
        effective_to=date(2026, 12, 31),
    )
    result = await update_employee_workplace_assignment(
        session, tenant_id, emp.id, assignment.id, req
    )

    assert result.is_primary is True
    assert result.effective_to == date(2026, 12, 31)
    assert assignment.is_primary is True


@pytest.mark.asyncio
async def test_update_workplace_assignment_overlapping_primary_rejected():
    """Verify updating an assignment to primary fails if another primary overlaps."""
    session = AsyncMock()
    tenant_id = uuid.uuid4()
    emp = _create_mock_employee(tenant_id)
    loc1 = _create_mock_location(tenant_id, name="Location One")
    loc2 = _create_mock_location(tenant_id, name="Location Two")

    # Current assignment being updated (Location 2, non-primary)
    assign2 = EmployeeLocation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp.id,
        location_id=loc2.id,
        is_primary=False,
        effective_from=date(2026, 1, 15),
        effective_to=date(2026, 2, 15),
        created_at=datetime.now(UTC),
    )

    # Existing other primary assignment (Location 1)
    assign1 = EmployeeLocation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp.id,
        location_id=loc1.id,
        is_primary=True,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 1, 31),
        created_at=datetime.now(UTC),
    )

    res_emp = MagicMock()
    res_emp.scalar_one_or_none.return_value = emp.id
    res_assign = MagicMock()
    res_assign.one_or_none.return_value = (assign2, loc2)
    res_primaries = MagicMock()
    res_primaries.all.return_value = [(assign1, loc1)]

    session.execute.side_effect = [res_emp, res_assign, res_primaries]

    req = EmployeeWorkplaceUpdateRequest(is_primary=True)
    with pytest.raises(HTTPException) as exc:
        await update_employee_workplace_assignment(session, tenant_id, emp.id, assign2.id, req)
    assert exc.value.status_code == 409
    assert "Conflicting primary assignment" in exc.value.detail


@pytest.mark.asyncio
async def test_end_workplace_assignment_preserves_historical_record():
    """Verify ending an assignment sets effective_to without deleting the row."""
    session = AsyncMock()
    tenant_id = uuid.uuid4()
    emp = _create_mock_employee(tenant_id)
    loc = _create_mock_location(tenant_id)

    assignment = EmployeeLocation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp.id,
        location_id=loc.id,
        is_primary=True,
        effective_from=date(2025, 1, 1),
        effective_to=None,
        created_at=datetime.now(UTC),
    )

    res_emp = MagicMock()
    res_emp.scalar_one_or_none.return_value = emp.id
    res_assign = MagicMock()
    res_assign.one_or_none.return_value = (assignment, loc)

    session.execute.side_effect = [res_emp, res_assign]

    end_date = date.today()
    result = await end_employee_workplace_assignment(
        session, tenant_id, emp.id, assignment.id, end_date=end_date
    )

    assert result.effective_to == end_date
    assert assignment.effective_to == end_date
    assert session.delete.called is False  # NOT hard-deleted
    assert session.commit.called


@pytest.mark.asyncio
async def test_end_workplace_assignment_already_ended_rejected():
    """Verify attempting to end an already-ended assignment raises HTTP 400."""
    session = AsyncMock()
    tenant_id = uuid.uuid4()
    emp = _create_mock_employee(tenant_id)
    loc = _create_mock_location(tenant_id)

    past_end = date.today() - timedelta(days=10)
    assignment = EmployeeLocation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp.id,
        location_id=loc.id,
        is_primary=True,
        effective_from=date(2025, 1, 1),
        effective_to=past_end,
        created_at=datetime.now(UTC),
    )

    res_emp = MagicMock()
    res_emp.scalar_one_or_none.return_value = emp.id
    res_assign = MagicMock()
    res_assign.one_or_none.return_value = (assignment, loc)

    session.execute.side_effect = [res_emp, res_assign]

    with pytest.raises(HTTPException) as exc:
        await end_employee_workplace_assignment(session, tenant_id, emp.id, assignment.id)
    assert exc.value.status_code == 400
    assert "already ended" in exc.value.detail


@pytest.mark.asyncio
async def test_list_location_employees_service():
    """Verify list_location_employees returns formatted employee records."""
    session = AsyncMock()
    tenant_id = uuid.uuid4()
    loc = _create_mock_location(tenant_id)
    emp = _create_mock_employee(tenant_id)
    assignment = EmployeeLocation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp.id,
        location_id=loc.id,
        is_primary=True,
        effective_from=date(2026, 1, 1),
        effective_to=None,
        created_at=datetime.now(UTC),
    )

    res_loc = MagicMock()
    res_loc.scalar_one_or_none.return_value = loc.id
    res_count = MagicMock()
    res_count.scalar_one.return_value = 1
    res_rows = MagicMock()
    res_rows.all.return_value = [(assignment, emp, "Engineering", "Senior Engineer")]

    session.execute.side_effect = [res_loc, res_count, res_rows]

    items, total = await list_location_employees(session, tenant_id, loc.id)
    assert total == 1
    assert len(items) == 1
    assert items[0].employee_id == emp.id
    assert items[0].employee_name == "Jane Doe"
    assert items[0].department_name == "Engineering"
    assert items[0].designation_title == "Senior Engineer"
    assert items[0].is_primary is True
    assert items[0].is_current is True


@pytest.mark.asyncio
async def test_list_employee_workplaces_service():
    """Verify list_employee_workplaces service returns mapped assignments."""
    session = AsyncMock()
    tenant_id = uuid.uuid4()
    emp = _create_mock_employee(tenant_id)
    loc = _create_mock_location(tenant_id)
    assignment = EmployeeLocation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp.id,
        location_id=loc.id,
        is_primary=True,
        effective_from=date(2026, 1, 1),
        effective_to=None,
        created_at=datetime.now(UTC),
    )

    res_emp = MagicMock()
    res_emp.scalar_one_or_none.return_value = emp.id
    res_count = MagicMock()
    res_count.scalar_one.return_value = 1
    res_rows = MagicMock()
    res_rows.all.return_value = [(assignment, loc)]

    session.execute.side_effect = [res_emp, res_count, res_rows]

    items, total = await list_employee_workplaces(session, tenant_id, emp.id)
    assert total == 1
    assert len(items) == 1
    assert items[0].location_name == "Headquarters"
    assert items[0].is_primary is True


@pytest.mark.asyncio
async def test_get_my_workplaces_service():
    """Verify get_my_workplaces service resolves employee profile and returns assignments."""
    session = AsyncMock()
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    emp = _create_mock_employee(tenant_id, user_id=user_id)
    loc = _create_mock_location(tenant_id)
    assignment = EmployeeLocation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp.id,
        location_id=loc.id,
        is_primary=True,
        effective_from=date(2026, 1, 1),
        effective_to=None,
        created_at=datetime.now(UTC),
    )

    res_user = MagicMock()
    res_user.scalar_one_or_none.return_value = emp.id
    res_emp = MagicMock()
    res_emp.scalar_one_or_none.return_value = emp.id
    res_count = MagicMock()
    res_count.scalar_one.return_value = 1
    res_rows = MagicMock()
    res_rows.all.return_value = [(assignment, loc)]

    session.execute.side_effect = [res_user, res_emp, res_count, res_rows]

    items, total = await get_my_workplaces(session, tenant_id, user_id)
    assert total == 1
    assert len(items) == 1
    assert items[0].location_name == "Headquarters"



# ============================================================================
# API Route & RBAC Integration Tests
# ============================================================================


@pytest.mark.asyncio
async def test_api_unauthenticated_requests_rejected():
    """Verify workplace assignment endpoints require authentication."""
    transport = ASGITransport(app=app)
    emp_id = uuid.uuid4()
    loc_id = uuid.uuid4()
    assign_id = uuid.uuid4()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # GET /employees/me/workplaces
        r1 = await client.get("/api/v1/employees/me/workplaces")
        assert r1.status_code == 401

        # POST /employees/{id}/workplaces
        r2 = await client.post(f"/api/v1/employees/{emp_id}/workplaces", json={})
        assert r2.status_code == 401

        # GET /employees/{id}/workplaces
        r3 = await client.get(f"/api/v1/employees/{emp_id}/workplaces")
        assert r3.status_code == 401

        # PUT /employees/{id}/workplaces/{assignment_id}
        r4 = await client.put(f"/api/v1/employees/{emp_id}/workplaces/{assign_id}", json={})
        assert r4.status_code == 401

        # DELETE /employees/{id}/workplaces/{assignment_id}
        r5 = await client.delete(f"/api/v1/employees/{emp_id}/workplaces/{assign_id}")
        assert r5.status_code == 401

        # GET /locations/{location_id}/employees
        r6 = await client.get(f"/api/v1/locations/{loc_id}/employees")
        assert r6.status_code == 401


@pytest.mark.asyncio
async def test_api_employee_role_forbidden_from_other_employees_workplaces():
    """Verify EMPLOYEE role cannot view or manage other employees' workplace assignments."""
    auth_ctx = _mock_context("employee")
    app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx

    transport = ASGITransport(app=app)
    target_emp_id = uuid.uuid4()
    assign_id = uuid.uuid4()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Cannot view other's workplaces
        r1 = await client.get(f"/api/v1/employees/{target_emp_id}/workplaces")
        assert r1.status_code == 403

        # Cannot assign workplace
        r2 = await client.post(f"/api/v1/employees/{target_emp_id}/workplaces", json={})
        assert r2.status_code == 403

        # Cannot update assignment
        r3 = await client.put(
            f"/api/v1/employees/{target_emp_id}/workplaces/{assign_id}", json={}
        )
        assert r3.status_code == 403

        # Cannot end assignment
        r4 = await client.delete(f"/api/v1/employees/{target_emp_id}/workplaces/{assign_id}")
        assert r4.status_code == 403

        # Cannot view location employee roster
        r5 = await client.get(f"/api/v1/locations/{uuid.uuid4()}/employees")
        assert r5.status_code == 403

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_manager_role_read_only_assignments():
    """Verify MANAGER role can view assignments and location roster, but cannot mutate them."""
    auth_ctx = _mock_context("manager")
    mock_db = AsyncMock()
    app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
    app.dependency_overrides[get_db] = lambda: mock_db

    transport = ASGITransport(app=app)
    emp_id = uuid.uuid4()
    assign_id = uuid.uuid4()
    loc_id = uuid.uuid4()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Mutating endpoints must return 403 Forbidden for MANAGER
        r_post = await client.post(
            f"/api/v1/employees/{emp_id}/workplaces",
            json={"location_id": str(loc_id), "is_primary": True},
        )
        assert r_post.status_code == 403

        r_put = await client.put(
            f"/api/v1/employees/{emp_id}/workplaces/{assign_id}",
            json={"is_primary": False},
        )
        assert r_put.status_code == 403

        r_del = await client.delete(f"/api/v1/employees/{emp_id}/workplaces/{assign_id}")
        assert r_del.status_code == 403

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_hr_role_can_manage_assignments():
    """Verify HR role has permission to create, update, and end employee workplace assignments."""
    tenant_id = uuid.uuid4()
    auth_ctx = _mock_context("hr", tenant_id=tenant_id)
    emp = _create_mock_employee(tenant_id)
    loc = _create_mock_location(tenant_id)

    mock_db = AsyncMock()
    mock_db.add = MagicMock()

    res_emp = MagicMock()
    res_emp.scalar_one_or_none.return_value = emp
    res_loc = MagicMock()
    res_loc.scalar_one_or_none.return_value = loc
    res_dup = MagicMock()
    res_dup.scalar_one_or_none.return_value = None
    res_primaries = MagicMock()
    res_primaries.all.return_value = []

    mock_db.execute.side_effect = [res_emp, res_loc, res_dup, res_primaries]

    app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
    app.dependency_overrides[get_db] = lambda: mock_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            f"/api/v1/employees/{emp.id}/workplaces",
            json={
                "location_id": str(loc.id),
                "is_primary": True,
                "effective_from": "2026-01-01",
            },
        )
        assert res.status_code == 201
        data = res.json()
        assert data["employee_id"] == str(emp.id)
        assert data["location_id"] == str(loc.id)
        assert data["is_primary"] is True

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_get_my_workplaces_resolves_authenticated_employee():
    """Verify GET /employees/me/workplaces retrieves assignments for the calling user's profile."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    auth_ctx = _mock_context("employee", tenant_id=tenant_id, user_id=user_id)
    emp = _create_mock_employee(tenant_id, user_id=user_id)
    loc = _create_mock_location(tenant_id)
    assignment = EmployeeLocation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp.id,
        location_id=loc.id,
        is_primary=True,
        effective_from=date(2026, 1, 1),
        effective_to=None,
        created_at=datetime.now(UTC),
    )

    mock_db = AsyncMock()

    # 1. get_my_workplaces: select(Employee.id).where(tenant_id, user_id)
    res_user_emp = MagicMock()
    res_user_emp.scalar_one_or_none.return_value = emp.id

    # 2. list_employee_workplaces: select(Employee.id).where(id, tenant_id)
    res_emp = MagicMock()
    res_emp.scalar_one_or_none.return_value = emp.id

    # 3. count_stmt
    res_count = MagicMock()
    res_count.scalar_one.return_value = 1

    # 4. rows_stmt
    res_rows = MagicMock()
    res_rows.all.return_value = [(assignment, loc)]

    mock_db.execute.side_effect = [res_user_emp, res_emp, res_count, res_rows]

    app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
    app.dependency_overrides[get_db] = lambda: mock_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/employees/me/workplaces")
        assert res.status_code == 200
        payload = res.json()
        assert payload["total"] == 1
        assert len(payload["items"]) == 1
        assert payload["items"][0]["location_name"] == "Headquarters"
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_assign_workplace_non_primary_overlap_accepted():
    """Verify non-primary workplace assignments are permitted to overlap."""
    session = AsyncMock()
    session.add = MagicMock()
    tenant_id = uuid.uuid4()
    emp = _create_mock_employee(tenant_id)
    loc = _create_mock_location(tenant_id)

    res_emp = MagicMock()
    res_emp.scalar_one_or_none.return_value = emp
    res_loc = MagicMock()
    res_loc.scalar_one_or_none.return_value = loc
    res_dup = MagicMock()
    res_dup.scalar_one_or_none.return_value = None

    session.execute.side_effect = [res_emp, res_loc, res_dup]

    req = EmployeeWorkplaceAssignRequest(
        location_id=loc.id,
        is_primary=False,
        effective_from=date(2026, 1, 15),
        effective_to=date(2026, 2, 15),
    )
    result = await assign_workplace_to_employee(session, tenant_id, emp.id, req)
    assert result.is_primary is False
    assert result.location_id == loc.id


@pytest.mark.asyncio
async def test_assign_workplace_invalid_date_range_service():
    """Verify assign_workplace_to_employee rejects effective_to < effective_from."""
    session = AsyncMock()
    tenant_id = uuid.uuid4()
    emp = _create_mock_employee(tenant_id)
    loc = _create_mock_location(tenant_id)

    res_emp = MagicMock()
    res_emp.scalar_one_or_none.return_value = emp
    res_loc = MagicMock()
    res_loc.scalar_one_or_none.return_value = loc

    session.execute.side_effect = [res_emp, res_loc]

    # Create model bypassing pydantic validator to test service boundary
    req = EmployeeWorkplaceAssignRequest.model_construct(
        location_id=loc.id,
        is_primary=False,
        effective_from=date(2026, 2, 1),
        effective_to=date(2026, 1, 1),
    )
    with pytest.raises(HTTPException) as exc:
        await assign_workplace_to_employee(session, tenant_id, emp.id, req)
    assert exc.value.status_code == 400
    assert "earlier than start date" in exc.value.detail


@pytest.mark.asyncio
async def test_end_workplace_assignment_invalid_end_date():
    """Verify end_employee_workplace_assignment rejects end_date < effective_from."""
    session = AsyncMock()
    tenant_id = uuid.uuid4()
    emp = _create_mock_employee(tenant_id)
    loc = _create_mock_location(tenant_id)

    assignment = EmployeeLocation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp.id,
        location_id=loc.id,
        is_primary=True,
        effective_from=date(2026, 5, 1),
        effective_to=None,
        created_at=datetime.now(UTC),
    )

    res_emp = MagicMock()
    res_emp.scalar_one_or_none.return_value = emp.id
    res_assign = MagicMock()
    res_assign.one_or_none.return_value = (assignment, loc)

    session.execute.side_effect = [res_emp, res_assign]

    with pytest.raises(HTTPException) as exc:
        await end_employee_workplace_assignment(
            session, tenant_id, emp.id, assignment.id, end_date=date(2026, 4, 1)
        )
    assert exc.value.status_code == 400
    assert "cannot be earlier than assignment start date" in exc.value.detail


@pytest.mark.asyncio
async def test_api_admin_can_update_workplace_assignment():
    """Verify Admin role can update workplace assignment via PUT."""
    tenant_id = uuid.uuid4()
    auth_ctx = _mock_context("admin", tenant_id=tenant_id)
    emp = _create_mock_employee(tenant_id)
    loc = _create_mock_location(tenant_id)
    assignment = EmployeeLocation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp.id,
        location_id=loc.id,
        is_primary=False,
        effective_from=date(2026, 1, 1),
        effective_to=None,
        created_at=datetime.now(UTC),
    )

    mock_db = AsyncMock()
    res_emp = MagicMock()
    res_emp.scalar_one_or_none.return_value = emp.id
    res_assign = MagicMock()
    res_assign.one_or_none.return_value = (assignment, loc)
    res_primaries = MagicMock()
    res_primaries.all.return_value = []

    mock_db.execute.side_effect = [res_emp, res_assign, res_primaries]

    app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
    app.dependency_overrides[get_db] = lambda: mock_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.put(
            f"/api/v1/employees/{emp.id}/workplaces/{assignment.id}",
            json={"is_primary": True},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["is_primary"] is True

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_admin_can_end_workplace_assignment():
    """Verify Admin role can end workplace assignment via DELETE."""
    tenant_id = uuid.uuid4()
    auth_ctx = _mock_context("admin", tenant_id=tenant_id)
    emp = _create_mock_employee(tenant_id)
    loc = _create_mock_location(tenant_id)
    assignment = EmployeeLocation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp.id,
        location_id=loc.id,
        is_primary=True,
        effective_from=date(2025, 1, 1),
        effective_to=None,
        created_at=datetime.now(UTC),
    )

    mock_db = AsyncMock()
    res_emp = MagicMock()
    res_emp.scalar_one_or_none.return_value = emp.id
    res_assign = MagicMock()
    res_assign.one_or_none.return_value = (assignment, loc)

    mock_db.execute.side_effect = [res_emp, res_assign]

    app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
    app.dependency_overrides[get_db] = lambda: mock_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.delete(
            f"/api/v1/employees/{emp.id}/workplaces/{assignment.id}?end_date=2026-06-30"
        )
        assert res.status_code == 200
        data = res.json()
        assert data["effective_to"] == "2026-06-30"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_manager_can_list_location_employees():
    """Verify Manager role can list employees assigned to a workplace location."""
    tenant_id = uuid.uuid4()
    auth_ctx = _mock_context("manager", tenant_id=tenant_id)
    loc = _create_mock_location(tenant_id)
    emp = _create_mock_employee(tenant_id)
    assignment = EmployeeLocation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp.id,
        location_id=loc.id,
        is_primary=True,
        effective_from=date(2026, 1, 1),
        effective_to=None,
        created_at=datetime.now(UTC),
    )

    mock_db = AsyncMock()
    res_loc = MagicMock()
    res_loc.scalar_one_or_none.return_value = loc.id
    res_count = MagicMock()
    res_count.scalar_one.return_value = 1
    res_rows = MagicMock()
    res_rows.all.return_value = [(assignment, emp, "Operations", "Supervisor")]

    mock_db.execute.side_effect = [res_loc, res_count, res_rows]

    app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
    app.dependency_overrides[get_db] = lambda: mock_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(f"/api/v1/locations/{loc.id}/employees")
        assert res.status_code == 200
        payload = res.json()
        assert payload["total"] == 1
        assert len(payload["items"]) == 1
        assert payload["items"][0]["employee_name"] == "Jane Doe"
        assert payload["items"][0]["department_name"] == "Operations"
        assert payload["items"][0]["designation_title"] == "Supervisor"

    app.dependency_overrides.clear()

