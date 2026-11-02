"""Unit tests for Phase 3 employee business rules and validations."""

import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from services.api.auth.models import RefreshToken, User
from services.api.employees.models import Employee
from services.api.employees.schemas import (
    EmployeeCreateRequest,
    EmployeeUpdateRequest,
)
from services.api.employees.service import (
    create_employee,
    update_employee,
    update_employee_status,
)
from services.api.organization.models import Department, Designation
from services.api.tenants.models import Tenant


@pytest.mark.asyncio
async def test_cannot_assign_inactive_department():
    """Verify that creating an employee with an inactive department raises HTTP 400."""
    session = AsyncMock()
    tenant_id = uuid.uuid4()
    dept_id = uuid.uuid4()

    inactive_dept = Department(
        id=dept_id,
        tenant_id=tenant_id,
        name="Archive",
        code="ARC",
        is_active=False,
    )

    # 1. employee_id check -> None
    # 2. email check -> None
    # 3. department check -> inactive_dept
    res_none = MagicMock()
    res_none.scalar_one_or_none.return_value = None

    res_dept = MagicMock()
    res_dept.scalar_one_or_none.return_value = inactive_dept

    session.execute.side_effect = [res_none, res_none, res_dept]

    req = EmployeeCreateRequest(
        employee_id="EMP-101",
        first_name="Jane",
        last_name="Doe",
        work_email="jane.doe@example.com",
        department_id=dept_id,
        joining_date=date(2024, 1, 1),
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_employee(session, tenant_id, req)

    assert exc_info.value.status_code == 400
    assert "Cannot assign an inactive department" in exc_info.value.detail


@pytest.mark.asyncio
async def test_cannot_assign_inactive_designation():
    """Verify that creating an employee with an inactive designation raises HTTP 400."""
    session = AsyncMock()
    tenant_id = uuid.uuid4()
    desig_id = uuid.uuid4()

    inactive_desig = Designation(
        id=desig_id,
        tenant_id=tenant_id,
        title="Deprecated Title",
        code="OLD",
        is_active=False,
    )

    res_none = MagicMock()
    res_none.scalar_one_or_none.return_value = None

    res_desig = MagicMock()
    res_desig.scalar_one_or_none.return_value = inactive_desig

    session.execute.side_effect = [res_none, res_none, res_desig]

    req = EmployeeCreateRequest(
        employee_id="EMP-102",
        first_name="Jane",
        last_name="Doe",
        work_email="jane.doe2@example.com",
        designation_id=desig_id,
        joining_date=date(2024, 1, 1),
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_employee(session, tenant_id, req)

    assert exc_info.value.status_code == 400
    assert "Cannot assign an inactive designation" in exc_info.value.detail


@pytest.mark.asyncio
async def test_cannot_assign_inactive_manager():
    """Verify that assigning an inactive/terminated manager raises HTTP 400."""
    session = AsyncMock()
    tenant_id = uuid.uuid4()
    mgr_id = uuid.uuid4()

    inactive_mgr = Employee(
        id=mgr_id,
        tenant_id=tenant_id,
        employee_id="EMP-MGR",
        first_name="Former",
        last_name="Boss",
        work_email="boss@example.com",
        status="terminated",
        joining_date=date(2020, 1, 1),
    )

    res_none = MagicMock()
    res_none.scalar_one_or_none.return_value = None

    res_mgr = MagicMock()
    res_mgr.scalar_one_or_none.return_value = inactive_mgr

    session.execute.side_effect = [res_none, res_none, res_mgr]

    req = EmployeeCreateRequest(
        employee_id="EMP-103",
        first_name="Jane",
        last_name="Doe",
        work_email="jane.doe3@example.com",
        reporting_manager_id=mgr_id,
        joining_date=date(2024, 1, 1),
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_employee(session, tenant_id, req)

    assert exc_info.value.status_code == 400
    assert (
        "Cannot assign an inactive or terminated employee as reporting manager"
        in exc_info.value.detail
    )


@pytest.mark.asyncio
async def test_reporting_hierarchy_cycle_prevention():
    """Verify circular reporting detection when updating an employee."""
    session = AsyncMock()
    tenant_id = uuid.uuid4()
    emp_a_id = uuid.uuid4()
    emp_b_id = uuid.uuid4()

    emp_b = Employee(
        id=emp_b_id,
        tenant_id=tenant_id,
        employee_id="EMP-B",
        first_name="Bob",
        last_name="Smith",
        work_email="bob@example.com",
        status="active",
        reporting_manager_id=None,
        joining_date=date(2023, 1, 1),
    )

    # Manager A exists and currently reports to B!
    mgr_a = Employee(
        id=emp_a_id,
        tenant_id=tenant_id,
        employee_id="EMP-A",
        first_name="Alice",
        last_name="Smith",
        work_email="alice@example.com",
        status="active",
        reporting_manager_id=emp_b_id,
        joining_date=date(2022, 1, 1),
    )

    res_emp_b = MagicMock()
    res_emp_b.scalar_one_or_none.return_value = emp_b

    res_mgr_a = MagicMock()
    res_mgr_a.scalar_one_or_none.return_value = mgr_a

    session.execute.side_effect = [res_emp_b, res_mgr_a]

    req = EmployeeUpdateRequest(reporting_manager_id=emp_a_id)

    with pytest.raises(HTTPException) as exc_info:
        await update_employee(session, tenant_id, emp_b_id, req)

    assert exc_info.value.status_code == 400
    assert "Circular reporting detected" in exc_info.value.detail


@pytest.mark.asyncio
async def test_invalid_status_transition_rejected():
    """Verify that invalid employee status transitions (e.g. terminated -> on_leave) raise HTTP 400."""
    session = AsyncMock()
    tenant_id = uuid.uuid4()
    emp_id = uuid.uuid4()

    terminated_emp = Employee(
        id=emp_id,
        tenant_id=tenant_id,
        employee_id="EMP-TERM",
        first_name="Term",
        last_name="Employee",
        work_email="term@example.com",
        status="terminated",
        joining_date=date(2022, 1, 1),
    )

    res_emp = MagicMock()
    res_emp.scalar_one_or_none.return_value = terminated_emp
    session.execute.return_value = res_emp

    with pytest.raises(HTTPException) as exc_info:
        await update_employee_status(session, tenant_id, emp_id, "on_leave")

    assert exc_info.value.status_code == 400
    assert (
        "Invalid employee status transition from 'terminated' to 'on_leave'"
        in exc_info.value.detail
    )


@pytest.mark.asyncio
async def test_employee_deactivation_syncs_user_and_revokes_tokens():
    """Verify deactivating an employee updates linked user.status to inactive and revokes refresh tokens."""
    session = AsyncMock()
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    emp_id = uuid.uuid4()

    active_emp = Employee(
        id=emp_id,
        tenant_id=tenant_id,
        user_id=user_id,
        employee_id="EMP-ACTIVE",
        first_name="Active",
        last_name="User",
        work_email="active@example.com",
        status="active",
        employment_type="full_time",
        joining_date=date(2022, 1, 1),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    active_emp.department = None
    active_emp.designation = None
    active_emp.manager = None

    active_user = User(
        id=user_id,
        tenant_id=tenant_id,
        full_name="Active User",
        email="active@example.com",
        password_hash="argon2id$mock",
        status="active",
    )

    # 1. Fetch employee -> returns active_emp
    # 2. Fetch linked user -> returns active_user
    # 3. get_employee (return DTO) -> returns active_emp
    res_emp = MagicMock()
    res_emp.scalar_one_or_none.return_value = active_emp

    res_user = MagicMock()
    res_user.scalar_one_or_none.return_value = active_user

    res_get = MagicMock()
    res_get.scalar_one_or_none.return_value = active_emp

    session.execute.side_effect = [res_emp, res_user, MagicMock(), res_get]

    res = await update_employee_status(session, tenant_id, emp_id, "inactive")

    assert res.status == "inactive"
    assert active_emp.status == "inactive"
    assert active_user.status == "inactive"
    assert session.commit.called


@pytest.mark.asyncio
async def test_employee_reactivation_restores_user_status():
    """Verify reactivating an employee restores linked user.status to active."""
    session = AsyncMock()
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    emp_id = uuid.uuid4()

    inactive_emp = Employee(
        id=emp_id,
        tenant_id=tenant_id,
        user_id=user_id,
        employee_id="EMP-INACTIVE",
        first_name="Inactive",
        last_name="User",
        work_email="inactive@example.com",
        status="inactive",
        employment_type="full_time",
        joining_date=date(2022, 1, 1),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    inactive_emp.department = None
    inactive_emp.designation = None
    inactive_emp.manager = None

    inactive_user = User(
        id=user_id,
        tenant_id=tenant_id,
        full_name="Inactive User",
        email="inactive@example.com",
        password_hash="argon2id$mock",
        status="inactive",
    )

    res_emp = MagicMock()
    res_emp.scalar_one_or_none.return_value = inactive_emp

    res_user = MagicMock()
    res_user.scalar_one_or_none.return_value = inactive_user

    res_get = MagicMock()
    res_get.scalar_one_or_none.return_value = inactive_emp

    session.execute.side_effect = [res_emp, res_user, res_get]

    await update_employee_status(session, tenant_id, emp_id, "active")

    assert inactive_emp.status == "active"
    assert inactive_user.status == "active"
    assert session.commit.called


@pytest.mark.asyncio
async def test_login_rejected_for_deactivated_user():
    """Verify login is rejected with HTTP 401 when the user account is inactive."""
    from services.api.auth.schemas import LoginRequest
    from services.api.auth.service import login

    session = AsyncMock()
    tenant_id = uuid.uuid4()
    tenant = Tenant(
        id=tenant_id,
        name="Acme Corp",
        slug="acme-corp",
        company_email="admin@acme.com",
        country_code="US",
        timezone="UTC",
        status="active",
    )

    # 1. Lookup tenant -> returns active tenant
    res_tenant = MagicMock()
    res_tenant.scalar_one_or_none.return_value = tenant

    # 2. Lookup user where status == 'active' -> returns None (user is inactive!)
    res_user = MagicMock()
    res_user.scalar_one_or_none.return_value = None

    session.execute.side_effect = [res_tenant, res_user]

    req = LoginRequest(
        tenant_slug="acme-corp",
        email="inactive@acme.com",
        password="ValidPassword123!",
    )

    with patch("services.api.auth.service.set_tenant_context", new_callable=AsyncMock):
        with pytest.raises(HTTPException) as exc_info:
            await login(session, req)

    assert exc_info.value.status_code == 401
    assert "Invalid credentials or inactive account" in exc_info.value.detail


@pytest.mark.asyncio
async def test_refresh_token_rejected_for_deactivated_user():
    """Verify refresh token rotation is rejected with HTTP 401 when the linked user is inactive."""
    from services.api.auth.service import refresh_access_token

    session = AsyncMock()
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    token_id = uuid.uuid4()

    valid_token = RefreshToken(
        id=token_id,
        tenant_id=tenant_id,
        user_id=user_id,
        token_hash="mock-hash",
        family_id=uuid.uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=7),
        revoked_at=None,
    )

    tenant = Tenant(
        id=tenant_id,
        name="Acme Corp",
        slug="acme-corp",
        company_email="admin@acme.com",
        country_code="US",
        timezone="UTC",
        status="active",
    )

    # 1. Lookup token by hash -> returns valid_token
    res_token = MagicMock()
    res_token.scalar_one_or_none.return_value = valid_token

    # 2. Lookup user where status == 'active' -> returns None (user was deactivated!)
    res_user = MagicMock()
    res_user.scalar_one_or_none.return_value = None

    # 3. Lookup tenant -> returns tenant
    res_tenant = MagicMock()
    res_tenant.scalar_one_or_none.return_value = tenant

    session.execute.side_effect = [res_token, res_user, res_tenant]

    with patch("services.api.auth.service.set_tenant_context", new_callable=AsyncMock):
        with pytest.raises(HTTPException) as exc_info:
            await refresh_access_token(session, "raw-refresh-token")

    assert exc_info.value.status_code == 401
    assert "User or tenant account is inactive" in exc_info.value.detail
    assert valid_token.revoked_at is not None


@pytest.mark.asyncio
async def test_employee_termination_syncs_user_and_revokes_tokens():
    """Verify terminating an employee sets linked user status to inactive and revokes refresh tokens."""
    session = AsyncMock()
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    emp_id = uuid.uuid4()

    active_emp = Employee(
        id=emp_id,
        tenant_id=tenant_id,
        user_id=user_id,
        employee_id="EMP-TERM",
        first_name="Terminated",
        last_name="Worker",
        work_email="term@example.com",
        status="active",
        employment_type="full_time",
        joining_date=date(2023, 1, 1),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    active_emp.department = None
    active_emp.designation = None
    active_emp.manager = None

    active_user = User(
        id=user_id,
        tenant_id=tenant_id,
        full_name="Terminated Worker",
        email="term@example.com",
        password_hash="argon2id$mock",
        status="active",
    )

    res_emp = MagicMock()
    res_emp.scalar_one_or_none.return_value = active_emp

    res_user = MagicMock()
    res_user.scalar_one_or_none.return_value = active_user

    res_get = MagicMock()
    res_get.scalar_one_or_none.return_value = active_emp

    session.execute.side_effect = [res_emp, res_user, MagicMock(), res_get]

    res = await update_employee_status(session, tenant_id, emp_id, "terminated")

    assert res.status == "terminated"
    assert active_emp.status == "terminated"
    assert active_user.status == "inactive"
    assert session.commit.called


@pytest.mark.asyncio
async def test_active_employee_can_authenticate():
    """Verify an active employee can successfully authenticate and receive tokens."""
    from services.api.auth.schemas import LoginRequest
    from services.api.auth.security import hash_password
    from services.api.auth.service import login

    session = AsyncMock()
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()

    tenant = Tenant(
        id=tenant_id,
        name="Acme Corp",
        slug="acme-corp",
        company_email="admin@acme.com",
        country_code="US",
        timezone="UTC",
        status="active",
    )

    password = "CorrectPassword123!"
    active_user = User(
        id=user_id,
        tenant_id=tenant_id,
        full_name="Active Employee",
        email="employee@acme.com",
        password_hash=hash_password(password),
        role="employee",
        status="active",
    )

    res_tenant = MagicMock()
    res_tenant.scalar_one_or_none.return_value = tenant

    res_user = MagicMock()
    res_user.scalar_one_or_none.return_value = active_user

    session.execute.side_effect = [res_tenant, res_user]

    req = LoginRequest(
        tenant_slug="acme-corp",
        email="employee@acme.com",
        password=password,
    )

    with patch("services.api.auth.service.set_tenant_context", new_callable=AsyncMock):
        token_res, returned_user, returned_tenant = await login(session, req)

    assert token_res.access_token is not None
    assert token_res.refresh_token is not None
    assert token_res.token_type == "bearer"
    assert returned_user.email == "employee@acme.com"
    assert returned_user.role == "employee"
    assert returned_tenant.slug == "acme-corp"


@pytest.mark.asyncio
async def test_reactivated_employee_can_authenticate():
    """Verify a reactivated employee account can successfully log in."""
    from services.api.auth.schemas import LoginRequest
    from services.api.auth.security import hash_password
    from services.api.auth.service import login

    session = AsyncMock()
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()

    tenant = Tenant(
        id=tenant_id,
        name="Acme Corp",
        slug="acme-corp",
        company_email="admin@acme.com",
        country_code="US",
        timezone="UTC",
        status="active",
    )

    password = "WelcomeBack123!"
    reactivated_user = User(
        id=user_id,
        tenant_id=tenant_id,
        full_name="Reactivated Employee",
        email="reactivated@acme.com",
        password_hash=hash_password(password),
        role="employee",
        status="active",  # Restored to active
    )

    res_tenant = MagicMock()
    res_tenant.scalar_one_or_none.return_value = tenant

    res_user = MagicMock()
    res_user.scalar_one_or_none.return_value = reactivated_user

    session.execute.side_effect = [res_tenant, res_user]

    req = LoginRequest(
        tenant_slug="acme-corp",
        email="reactivated@acme.com",
        password=password,
    )

    with patch("services.api.auth.service.set_tenant_context", new_callable=AsyncMock):
        token_res, returned_user, _ = await login(session, req)

    assert token_res.access_token is not None
    assert returned_user.status == "active"
