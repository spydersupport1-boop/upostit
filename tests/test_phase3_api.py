"""Tests for Phase 3 API endpoint authentication and RBAC authorization boundaries."""

import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from services.api.auth.dependencies import AuthenticatedContext, get_authenticated_context
from services.api.auth.models import User
from services.api.database import get_db
from services.api.employees.models import Employee
from services.api.main import app
from services.api.tenants.models import Tenant


def _mock_context(role: str) -> AuthenticatedContext:
    tenant_id = uuid.uuid4()
    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        full_name=f"Test {role.title()}",
        email=f"test_{role}@corp.test",
        password_hash="argon2id$mock",
        role=role,
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    tenant = Tenant(
        id=tenant_id,
        name="Test Corp",
        slug=f"test-{tenant_id.hex[:6]}",
        company_email="admin@corp.test",
        country_code="US",
        timezone="UTC",
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    return AuthenticatedContext(user=user, tenant=tenant)


@pytest.mark.asyncio
async def test_endpoints_require_authentication():
    """Verify all Phase 3 endpoints strictly require authentication (401 Unauthorized)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Departments
        res1 = await client.get("/api/v1/departments")
        assert res1.status_code == 401
        res2 = await client.post("/api/v1/departments", json={"name": "Eng", "code": "ENG"})
        assert res2.status_code == 401

        # Designations
        res3 = await client.get("/api/v1/designations")
        assert res3.status_code == 401
        res4 = await client.post("/api/v1/designations", json={"title": "Dev", "code": "DEV"})
        assert res4.status_code == 401

        # Employees
        res5 = await client.get("/api/v1/employees")
        assert res5.status_code == 401
        res6 = await client.post("/api/v1/employees", json={"employee_id": "EMP-1"})
        assert res6.status_code == 401


@pytest.mark.asyncio
async def test_employee_role_forbidden_from_modifications():
    """Verify users with role 'employee' are blocked with 403 Forbidden from mutating org/employee records."""
    app.dependency_overrides[get_authenticated_context] = lambda: _mock_context("employee")
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {"Authorization": "Bearer mocked-valid-token"}

            # Cannot create department
            res1 = await client.post("/api/v1/departments", headers=headers, json={"name": "Eng", "code": "ENG"})
            assert res1.status_code == 403
            assert "permission denied" in res1.json()["detail"].lower()

            # Cannot create designation
            res2 = await client.post("/api/v1/designations", headers=headers, json={"title": "Dev", "code": "DEV"})
            assert res2.status_code == 403
            assert "permission denied" in res2.json()["detail"].lower()

            # Cannot create employee
            res3 = await client.post("/api/v1/employees", headers=headers, json={
                "employee_id": "EMP-001",
                "first_name": "Test",
                "last_name": "User",
                "work_email": "test@corp.com",
                "joining_date": "2026-01-01",
            })
            assert res3.status_code == 403
            assert "permission denied" in res3.json()["detail"].lower()

            # Cannot update employee
            random_id = uuid.uuid4()
            res4 = await client.put(f"/api/v1/employees/{random_id}", headers=headers, json={"first_name": "Changed"})
            assert res4.status_code == 403
            assert "permission denied" in res4.json()["detail"].lower()

            # Cannot change employee status
            res5 = await client.patch(f"/api/v1/employees/{random_id}/status", headers=headers, json={"status": "terminated"})
            assert res5.status_code == 403
            assert "permission denied" in res5.json()["detail"].lower()

            # CANNOT view employee directory (Task 1: directory access denied)
            res6 = await client.get("/api/v1/employees", headers=headers)
            assert res6.status_code == 403
            assert "permission denied" in res6.json()["detail"].lower()

            # CANNOT view another employee by URL ID (Task 1: ID manipulation blocked)
            res7 = await client.get(f"/api/v1/employees/{random_id}", headers=headers)
            assert res7.status_code == 403
            assert "permission denied" in res7.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_employee_self_access_me_endpoint():
    """Verify GET /api/v1/employees/me returns 401 when unauthenticated, 404 when user has no linked profile, and 200 with profile when linked."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Unauthenticated request -> 401
        res_unauth = await client.get("/api/v1/employees/me")
        assert res_unauth.status_code == 401

    mock_ctx = _mock_context("employee")
    mock_session = AsyncMock()

    async def _mock_get_db():
        yield mock_session

    app.dependency_overrides[get_authenticated_context] = lambda: mock_ctx
    app.dependency_overrides[get_db] = _mock_get_db
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {"Authorization": "Bearer mocked-valid-token"}

            # 2. Authenticated employee without linked employee profile -> 404
            mock_res_none = MagicMock()
            mock_res_none.scalar_one_or_none.return_value = None
            mock_session.execute.return_value = mock_res_none

            res_404 = await client.get("/api/v1/employees/me", headers=headers)
            assert res_404.status_code == 404
            assert "No employee profile found" in res_404.json()["detail"]

            # 3. Authenticated employee with linked employee profile -> 200
            emp_id = uuid.uuid4()
            emp_profile = Employee(
                id=emp_id,
                tenant_id=mock_ctx.tenant.id,
                user_id=mock_ctx.user.id,
                employee_id="EMP-SELF",
                first_name="Self",
                last_name="Worker",
                work_email="worker@corp.test",
                phone_number="555-0100",
                employment_type="full_time",
                joining_date=date(2025, 1, 1),
                status="active",
                work_location="Remote",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            emp_profile.department = None
            emp_profile.designation = None
            emp_profile.manager = None

            mock_res_emp = MagicMock()
            mock_res_emp.scalar_one_or_none.return_value = emp_profile
            mock_session.execute.return_value = mock_res_emp

            res_200 = await client.get("/api/v1/employees/me", headers=headers)
            assert res_200.status_code == 200
            data = res_200.json()
            assert data["id"] == str(emp_id)
            assert data["employee_id"] == "EMP-SELF"
            assert data["work_email"] == "worker@corp.test"
            assert data["first_name"] == "Self"
            assert data["last_name"] == "Worker"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_hr_role_forbidden_from_managing_organization():
    """Verify HR role can manage employees but cannot alter organization structure (403 Forbidden)."""
    app.dependency_overrides[get_authenticated_context] = lambda: _mock_context("hr")
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {"Authorization": "Bearer mocked-valid-token"}

            # HR cannot create department
            res1 = await client.post("/api/v1/departments", headers=headers, json={"name": "Finance", "code": "FIN"})
            assert res1.status_code == 403
            assert "permission denied" in res1.json()["detail"].lower()

            # HR cannot create designation
            res2 = await client.post("/api/v1/designations", headers=headers, json={"title": "Accountant", "code": "ACC"})
            assert res2.status_code == 403
            assert "permission denied" in res2.json()["detail"].lower()

            # HR cannot update department
            res3 = await client.put(f"/api/v1/departments/{uuid.uuid4()}", headers=headers, json={"name": "New Name"})
            assert res3.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_manager_role_forbidden_from_modifications():
    """Verify Manager role can view records but cannot create, update, or deactivate employees (403 Forbidden)."""
    app.dependency_overrides[get_authenticated_context] = lambda: _mock_context("manager")
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {"Authorization": "Bearer mocked-valid-token"}

            # Manager cannot create employee
            res1 = await client.post("/api/v1/employees", headers=headers, json={
                "employee_id": "EMP-999",
                "first_name": "New",
                "last_name": "Hire",
                "work_email": "hire@corp.com",
                "joining_date": "2026-01-01",
            })
            assert res1.status_code == 403
            assert "permission denied" in res1.json()["detail"].lower()

            # Manager cannot change employee status
            res2 = await client.patch(f"/api/v1/employees/{uuid.uuid4()}/status", headers=headers, json={"status": "inactive"})
            assert res2.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_payload_validation_errors():
    """Verify invalid payloads fail Pydantic validation with 422 Unprocessable Content."""
    app.dependency_overrides[get_authenticated_context] = lambda: _mock_context("owner")
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {"Authorization": "Bearer mocked-valid-token"}

            # Missing required fields
            res1 = await client.post("/api/v1/departments", headers=headers, json={})
            assert res1.status_code in (422, 400)

            # Invalid email in employee create
            res2 = await client.post("/api/v1/employees", headers=headers, json={
                "employee_id": "EMP-001",
                "first_name": "First",
                "last_name": "Last",
                "work_email": "not-valid",
                "joining_date": "invalid-date",
            })
            assert res2.status_code in (422, 400)
    finally:
        app.dependency_overrides.clear()
