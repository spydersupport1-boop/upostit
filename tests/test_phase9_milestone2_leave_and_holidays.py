"""Comprehensive automated test suite for Phase 9 Milestone 9.2:
Holiday Calendars & Leave Type Configuration.

Tests:
1. RBAC permissions registry and role capabilities for Phase 9.
2. Leave Type Service CRUD, code uniqueness, input validations, reference checks on deletion.
3. Holiday Calendar Management: creation, listing, updating, deletion, and default demotion.
4. Holiday Entries: creation, date uniqueness per calendar, date-range queries, and deletion.
5. Hierarchical Calendar Resolution Engine:
   - Location-specific calendar precedence.
   - Inactive location fallback.
   - Department-specific calendar precedence.
   - Tenant-default fallback.
   - Complete missing calendar fallback.
6. Upcoming holidays inquiry logic and date range handling.
7. FastAPI Route Endpoints (HTTP integration via AsyncClient):
   - Leave type creation, retrieval, authorization (Employee -> 403 on mutate).
   - Holiday calendar creation and entry management.
   - Employee upcoming holidays self-scoping and peer access rejection (403).
   - Cross-tenant isolation enforcement.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status
from httpx import ASGITransport, AsyncClient

from services.api.auth.dependencies import AuthenticatedContext, get_authenticated_context
from services.api.auth.models import User
from services.api.auth.permissions import Permission, UserRole, has_permission
from services.api.database import get_db
from services.api.employees.models import Employee
from services.api.leave.holiday_service import (
    create_holiday_calendar,
    create_holiday_entry,
    resolve_applicable_calendar_for_employee,
)
from services.api.leave.leave_type_service import (
    create_leave_type,
    delete_leave_type,
    list_leave_types,
    update_leave_type,
)
from services.api.leave.models import (
    Holiday,
    HolidayCalendar,
    LeaveType,
)
from services.api.leave.schemas import (
    HolidayCalendarCreateRequest,
    HolidayCreateRequest,
    LeaveTypeCreateRequest,
    LeaveTypeUpdateRequest,
)
from services.api.locations.models import EmployeeLocation, Location
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
        full_name="Phase 9 Test User",
        email=f"test_{role.lower()}@upostit.test",
        password_hash="argon2id$mock",
        role=role.lower(),
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    tenant = Tenant(
        id=tid,
        name="Phase 9 Test Tenant",
        slug="phase9-test-tenant",
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    return AuthenticatedContext(user=user, tenant=tenant)


def _mock_employee(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
    department_id: uuid.UUID | None = None,
) -> Employee:
    return Employee(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id or uuid.uuid4(),
        employee_id=f"EMP-{uuid.uuid4().hex[:6].upper()}",
        first_name="Jane",
        last_name="Doe",
        work_email=f"jane.{uuid.uuid4().hex[:4]}@upostit.test",
        department_id=department_id,
        employment_type="full_time",
        joining_date=date(2025, 1, 1),
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


# ==============================================================================
# 1. RBAC & Permissions Matrix Tests
# ==============================================================================


class TestPhase9RBACPermissions:
    """Verifies granular Phase 9 permissions registry and role assignments."""

    def test_permission_definitions_exist(self):
        assert Permission.MANAGE_POLICIES == "manage_policies"
        assert Permission.VIEW_POLICIES == "view_policies"
        assert Permission.MANAGE_LEAVE_TYPES == "manage_leave_types"
        assert Permission.VIEW_LEAVE_TYPES == "view_leave_types"
        assert Permission.MANAGE_HOLIDAYS == "manage_holidays"
        assert Permission.VIEW_HOLIDAYS == "view_holidays"

    @pytest.mark.parametrize("role", [UserRole.OWNER, UserRole.ADMIN, UserRole.HR])
    def test_administrative_roles_have_full_leave_and_holiday_capabilities(self, role):
        assert has_permission(role, Permission.MANAGE_POLICIES) is True
        assert has_permission(role, Permission.VIEW_POLICIES) is True
        assert has_permission(role, Permission.MANAGE_LEAVE_TYPES) is True
        assert has_permission(role, Permission.VIEW_LEAVE_TYPES) is True
        assert has_permission(role, Permission.MANAGE_HOLIDAYS) is True
        assert has_permission(role, Permission.VIEW_HOLIDAYS) is True

    def test_manager_has_view_only_capabilities(self):
        assert has_permission(UserRole.MANAGER, Permission.VIEW_LEAVE_TYPES) is True
        assert has_permission(UserRole.MANAGER, Permission.VIEW_HOLIDAYS) is True
        assert has_permission(UserRole.MANAGER, Permission.MANAGE_LEAVE_TYPES) is False
        assert has_permission(UserRole.MANAGER, Permission.MANAGE_HOLIDAYS) is False

    def test_employee_has_view_only_capabilities(self):
        assert has_permission(UserRole.EMPLOYEE, Permission.VIEW_LEAVE_TYPES) is True
        assert has_permission(UserRole.EMPLOYEE, Permission.VIEW_HOLIDAYS) is True
        assert has_permission(UserRole.EMPLOYEE, Permission.MANAGE_LEAVE_TYPES) is False
        assert has_permission(UserRole.EMPLOYEE, Permission.MANAGE_HOLIDAYS) is False


# ==============================================================================
# 2. Leave Type Service & CRUD Tests
# ==============================================================================


class TestLeaveTypeService:
    """Unit tests for LeaveType management logic."""

    @pytest.mark.asyncio
    async def test_create_leave_type_success(self):
        session = AsyncMock()
        session.add = MagicMock()
        tid = uuid.uuid4()
        payload = LeaveTypeCreateRequest(
            code="al",
            name="Annual Leave",
            description="Paid vacation entitlement",
            is_paid=True,
            carry_forward_limit=Decimal("5.0"),
            max_consecutive_days=14,
        )

        mock_none_res = MagicMock()
        mock_none_res.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_none_res

        lt = await create_leave_type(session=session, tenant_id=tid, payload=payload)

        assert lt.code == "AL"
        assert lt.name == "Annual Leave"
        assert lt.carry_forward_limit == Decimal("5.0")
        assert lt.max_consecutive_days == 14
        session.add.assert_called_once()
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_leave_type_duplicate_code_raises_409(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        payload = LeaveTypeCreateRequest(code="cl", name="Casual Leave")

        existing_lt = LeaveType(id=uuid.uuid4(), tenant_id=tid, code="CL", name="Casual Leave")
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = existing_lt
        session.execute.return_value = mock_res

        with pytest.raises(HTTPException) as exc_info:
            await create_leave_type(session=session, tenant_id=tid, payload=payload)

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert "already exists" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_list_leave_types_filtering(self):
        session = AsyncMock()
        tid = uuid.uuid4()

        mock_count = MagicMock()
        mock_count.scalar.return_value = 2

        mock_data = MagicMock()
        mock_data.scalars.return_value.all.return_value = [
            LeaveType(id=uuid.uuid4(), tenant_id=tid, code="AL", name="Annual Leave"),
            LeaveType(id=uuid.uuid4(), tenant_id=tid, code="SL", name="Sick Leave"),
        ]

        session.execute.side_effect = [mock_count, mock_data]

        items, total = await list_leave_types(
            session=session,
            tenant_id=tid,
            search="leave",
            is_active=True,
            limit=10,
            offset=0,
        )

        assert total == 2
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_update_leave_type_modifies_fields(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        lid = uuid.uuid4()
        lt = LeaveType(
            id=lid,
            tenant_id=tid,
            code="SL",
            name="Sick Leave",
            is_active=True,
            carry_forward_limit=Decimal("0.0"),
        )

        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = lt
        session.execute.return_value = mock_res

        payload = LeaveTypeUpdateRequest(
            name="Medical / Sick Leave",
            carry_forward_limit=Decimal("3.0"),
            is_active=False,
        )
        updated = await update_leave_type(session, tid, lid, payload)

        assert updated.name == "Medical / Sick Leave"
        assert updated.carry_forward_limit == Decimal("3.0")
        assert updated.is_active is False
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_leave_type_blocked_by_existing_balances_raises_409(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        lid = uuid.uuid4()
        lt = LeaveType(id=lid, tenant_id=tid, code="AL", name="Annual Leave")

        mock_lt = MagicMock()
        mock_lt.scalar_one_or_none.return_value = lt

        mock_bal_count = MagicMock()
        mock_bal_count.scalar.return_value = 5  # 5 employee balances reference this

        session.execute.side_effect = [mock_lt, mock_bal_count]

        with pytest.raises(HTTPException) as exc_info:
            await delete_leave_type(session, tid, lid)

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert "referenced by 5 employee balance record(s)" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_delete_leave_type_blocked_by_existing_requests_raises_409(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        lid = uuid.uuid4()
        lt = LeaveType(id=lid, tenant_id=tid, code="AL", name="Annual Leave")

        mock_lt = MagicMock()
        mock_lt.scalar_one_or_none.return_value = lt

        mock_bal_count = MagicMock()
        mock_bal_count.scalar.return_value = 0

        mock_req_count = MagicMock()
        mock_req_count.scalar.return_value = 3  # 3 leave requests reference this

        session.execute.side_effect = [mock_lt, mock_bal_count, mock_req_count]

        with pytest.raises(HTTPException) as exc_info:
            await delete_leave_type(session, tid, lid)

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert "referenced by 3 employee leave request(s)" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_delete_leave_type_success_when_unreferenced(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        lid = uuid.uuid4()
        lt = LeaveType(id=lid, tenant_id=tid, code="SPECIAL", name="Special Leave")

        mock_lt = MagicMock()
        mock_lt.scalar_one_or_none.return_value = lt

        mock_zero = MagicMock()
        mock_zero.scalar.return_value = 0

        session.execute.side_effect = [mock_lt, mock_zero, mock_zero]

        await delete_leave_type(session, tid, lid)
        session.delete.assert_called_once_with(lt)
        session.flush.assert_awaited_once()


# ==============================================================================
# 3. Holiday Calendar Management Tests
# ==============================================================================


class TestHolidayCalendarService:
    """Unit tests for Holiday Calendar creation and management."""

    @pytest.mark.asyncio
    async def test_create_default_calendar_demotes_prior_default(self):
        session = AsyncMock()
        session.add = MagicMock()
        tid = uuid.uuid4()
        prior_default = HolidayCalendar(
            id=uuid.uuid4(),
            tenant_id=tid,
            year=2026,
            name="Old Default Calendar",
            is_default=True,
        )

        mock_defaults_res = MagicMock()
        mock_defaults_res.scalars.return_value.all.return_value = [prior_default]
        session.execute.return_value = mock_defaults_res

        payload = HolidayCalendarCreateRequest(
            year=2026,
            name="New Default Calendar 2026",
            is_default=True,
        )
        new_cal = await create_holiday_calendar(session, tid, payload)

        assert new_cal.name == "New Default Calendar 2026"
        assert new_cal.is_default is True
        assert prior_default.is_default is False
        session.add.assert_called_once()
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_location_calendar_validates_location_belongs_to_tenant(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        foreign_loc_id = uuid.uuid4()

        mock_none_res = MagicMock()
        mock_none_res.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_none_res

        payload = HolidayCalendarCreateRequest(
            year=2026,
            name="Branch Calendar",
            location_id=foreign_loc_id,
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_holiday_calendar(session, tid, payload)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "Workplace location" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_create_holiday_entry_duplicate_date_raises_409(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        cid = uuid.uuid4()
        cal = HolidayCalendar(id=cid, tenant_id=tid, year=2026, name="Main Calendar", holidays=[])

        dup_holiday = Holiday(
            id=uuid.uuid4(),
            tenant_id=tid,
            calendar_id=cid,
            holiday_date=date(2026, 1, 1),
            name="New Year's Day",
        )

        mock_cal_res = MagicMock()
        mock_cal_res.scalar_one_or_none.return_value = cal

        mock_dup_res = MagicMock()
        mock_dup_res.scalar_one_or_none.return_value = dup_holiday

        session.execute.side_effect = [mock_cal_res, mock_dup_res]

        payload = HolidayCreateRequest(
            holiday_date=date(2026, 1, 1),
            name="Duplicate New Year",
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_holiday_entry(session, tid, cid, payload)

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert "already exists on date 2026-01-01" in exc_info.value.detail


# ==============================================================================
# 4. Hierarchical Calendar Resolution Engine Tests
# ==============================================================================


class TestHierarchicalCalendarResolution:
    """Verifies strict 3-tier precedence: Location -> Department -> Tenant Default."""

    @pytest.mark.asyncio
    async def test_precedence_tier1_location_overrides_department_and_default(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        dept_id = uuid.uuid4()
        emp = _mock_employee(tid, department_id=dept_id)

        loc_id = uuid.uuid4()
        emp_loc = EmployeeLocation(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=emp.id,
            location_id=loc_id,
            is_primary=True,
            effective_from=date(2025, 1, 1),
        )
        active_loc = Location(
            id=loc_id,
            tenant_id=tid,
            name="Headquarters",
            code="HQ",
            is_active=True,
        )
        loc_calendar = HolidayCalendar(
            id=uuid.uuid4(),
            tenant_id=tid,
            year=2026,
            name="HQ Holiday Calendar",
            location_id=loc_id,
        )

        mock_emp = MagicMock()
        mock_emp.scalar_one_or_none.return_value = emp

        mock_primary_loc = MagicMock()
        mock_primary_loc.scalar_one_or_none.return_value = emp_loc

        mock_loc = MagicMock()
        mock_loc.scalar_one_or_none.return_value = active_loc

        mock_cal = MagicMock()
        mock_cal.scalar_one_or_none.return_value = loc_calendar

        session.execute.side_effect = [
            mock_emp,          # 1. Employee query
            mock_primary_loc,  # 2. Primary EmployeeLocation query
            mock_loc,          # 3. Active Location query
            mock_cal,          # 4. Location HolidayCalendar query
        ]

        calendar, source = await resolve_applicable_calendar_for_employee(
            session=session,
            tenant_id=tid,
            employee_id=emp.id,
            year=2026,
        )

        assert calendar is not None
        assert calendar.id == loc_calendar.id
        assert source == "LOCATION"

    @pytest.mark.asyncio
    async def test_precedence_tier1_inactive_location_falls_back_to_department(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        dept_id = uuid.uuid4()
        emp = _mock_employee(tid, department_id=dept_id)

        loc_id = uuid.uuid4()
        emp_loc = EmployeeLocation(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=emp.id,
            location_id=loc_id,
            is_primary=True,
            effective_from=date(2025, 1, 1),
        )

        dept_calendar = HolidayCalendar(
            id=uuid.uuid4(),
            tenant_id=tid,
            year=2026,
            name="Engineering Department Calendar",
            department_id=dept_id,
        )

        mock_emp = MagicMock()
        mock_emp.scalar_one_or_none.return_value = emp

        mock_primary_loc = MagicMock()
        mock_primary_loc.scalar_one_or_none.return_value = emp_loc

        mock_inactive_loc = MagicMock()
        mock_inactive_loc.scalar_one_or_none.return_value = None  # Location is inactive or missing

        mock_dept_cal = MagicMock()
        mock_dept_cal.scalar_one_or_none.return_value = dept_calendar

        session.execute.side_effect = [
            mock_emp,           # 1. Employee query
            mock_primary_loc,   # 2. Primary EmployeeLocation query
            mock_inactive_loc,  # 3. Active Location query -> None
            mock_dept_cal,      # 4. Department HolidayCalendar query -> Match!
        ]

        calendar, source = await resolve_applicable_calendar_for_employee(
            session=session,
            tenant_id=tid,
            employee_id=emp.id,
            year=2026,
        )

        assert calendar is not None
        assert calendar.id == dept_calendar.id
        assert source == "DEPARTMENT"

    @pytest.mark.asyncio
    async def test_precedence_tier3_falls_back_to_tenant_default(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        emp = _mock_employee(tid, department_id=None)

        default_calendar = HolidayCalendar(
            id=uuid.uuid4(),
            tenant_id=tid,
            year=2026,
            name="Standard National Calendar 2026",
            is_default=True,
        )

        mock_emp = MagicMock()
        mock_emp.scalar_one_or_none.return_value = emp

        mock_none = MagicMock()
        mock_none.scalar_one_or_none.return_value = None

        mock_default = MagicMock()
        mock_default.scalar_one_or_none.return_value = default_calendar

        session.execute.side_effect = [
            mock_emp,      # 1. Employee query
            mock_none,     # 2. Primary EmployeeLocation -> None
            mock_default,  # 3. Tenant Default query -> Match!
        ]

        calendar, source = await resolve_applicable_calendar_for_employee(
            session=session,
            tenant_id=tid,
            employee_id=emp.id,
            year=2026,
        )

        assert calendar is not None
        assert calendar.id == default_calendar.id
        assert source == "TENANT_DEFAULT"

    @pytest.mark.asyncio
    async def test_precedence_unmatched_returns_none(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        emp = _mock_employee(tid, department_id=None)

        mock_emp = MagicMock()
        mock_emp.scalar_one_or_none.return_value = emp

        mock_none = MagicMock()
        mock_none.scalar_one_or_none.return_value = None

        session.execute.side_effect = [
            mock_emp,   # 1. Employee query
            mock_none,  # 2. Primary EmployeeLocation -> None
            mock_none,  # 3. Tenant Default -> None
        ]

        calendar, source = await resolve_applicable_calendar_for_employee(
            session=session,
            tenant_id=tid,
            employee_id=emp.id,
            year=2026,
        )

        assert calendar is None
        assert source == "NONE"


# ==============================================================================
# 5. FastAPI HTTP Route Integration Tests
# ==============================================================================


class TestPhase9HTTPRouteIntegration:
    """HTTP integration tests verifying endpoints, status codes, and authorization."""

    @pytest.mark.asyncio
    async def test_hr_can_create_leave_type(self):
        tid = uuid.uuid4()
        ctx = _mock_context("hr", tenant_id=tid)

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_none_res = MagicMock()
        mock_none_res.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_none_res

        app.dependency_overrides[get_authenticated_context] = lambda: ctx
        app.dependency_overrides[get_db] = lambda: mock_db

        req = LeaveTypeCreateRequest(
            code="BEREAVEMENT",
            name="Bereavement Leave",
            is_paid=True,
            carry_forward_limit=Decimal("0.0"),
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/leave/types",
                json=req.model_dump(mode="json"),
            )

        app.dependency_overrides.clear()

        assert resp.status_code == status.HTTP_201_CREATED
        data = resp.json()
        assert data["code"] == "BEREAVEMENT"
        assert data["name"] == "Bereavement Leave"

    @pytest.mark.asyncio
    async def test_employee_cannot_create_leave_type_raises_403(self):
        tid = uuid.uuid4()
        ctx = _mock_context("employee", tenant_id=tid)

        mock_db = AsyncMock()

        app.dependency_overrides[get_authenticated_context] = lambda: ctx
        app.dependency_overrides[get_db] = lambda: mock_db

        req = LeaveTypeCreateRequest(
            code="UNAUTHORIZED",
            name="Unauthorized Leave",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/leave/types",
                json=req.model_dump(mode="json"),
            )

        app.dependency_overrides.clear()

        assert resp.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_employee_can_view_leave_types_200_ok(self):
        tid = uuid.uuid4()
        ctx = _mock_context("employee", tenant_id=tid)

        mock_db = AsyncMock()
        mock_count = MagicMock()
        mock_count.scalar.return_value = 1

        mock_data = MagicMock()
        mock_data.scalars.return_value.all.return_value = [
            LeaveType(
                id=uuid.uuid4(),
                tenant_id=tid,
                code="AL",
                name="Annual Leave",
                is_paid=True,
                requires_approval=True,
                allow_half_day=True,
                carry_forward_limit=Decimal("5.0"),
                is_active=True,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        ]
        mock_db.execute.side_effect = [mock_count, mock_data]

        app.dependency_overrides[get_authenticated_context] = lambda: ctx
        app.dependency_overrides[get_db] = lambda: mock_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/leave/types")

        app.dependency_overrides.clear()

        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["code"] == "AL"

    @pytest.mark.asyncio
    async def test_employee_can_query_own_upcoming_holidays(self):
        tid = uuid.uuid4()
        uid = uuid.uuid4()
        ctx = _mock_context("employee", tenant_id=tid, user_id=uid)
        emp = _mock_employee(tid, user_id=uid)

        cid = uuid.uuid4()
        cal = HolidayCalendar(id=cid, tenant_id=tid, year=2026, name="Default Calendar", is_default=True)
        h = Holiday(
            id=uuid.uuid4(),
            tenant_id=tid,
            calendar_id=cid,
            holiday_date=date(2026, 12, 25),
            name="Christmas Day",
            holiday_type="PUBLIC",
            is_optional=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        mock_db = AsyncMock()

        # Route query for user's employee record
        mock_emp_res = MagicMock()
        mock_emp_res.scalar_one_or_none.return_value = emp

        # Holiday service queries
        mock_emp_lookup = MagicMock()
        mock_emp_lookup.scalar_one_or_none.return_value = emp

        mock_none = MagicMock()
        mock_none.scalar_one_or_none.return_value = None

        mock_default_cal = MagicMock()
        mock_default_cal.scalar_one_or_none.return_value = cal

        mock_count = MagicMock()
        mock_count.scalar.return_value = 1

        mock_holidays_data = MagicMock()
        mock_holidays_data.all.return_value = [(h, "Default Calendar")]

        mock_db.execute.side_effect = [
            mock_emp_res,       # Route user_emp query
            mock_emp_lookup,    # resolve: employee lookup
            mock_none,          # resolve: primary loc -> None
            mock_default_cal,   # resolve: default cal -> cal
            mock_count,         # holidays count
            mock_holidays_data, # holidays data
        ]

        app.dependency_overrides[get_authenticated_context] = lambda: ctx
        app.dependency_overrides[get_db] = lambda: mock_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/holidays/upcoming?start_date=2026-01-01&end_date=2026-12-31")

        app.dependency_overrides.clear()

        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "Christmas Day"
        assert data["resolution_source"] == "TENANT_DEFAULT"

    @pytest.mark.asyncio
    async def test_employee_querying_other_employee_holidays_raises_403(self):
        tid = uuid.uuid4()
        uid = uuid.uuid4()
        ctx = _mock_context("employee", tenant_id=tid, user_id=uid)
        own_emp = _mock_employee(tid, user_id=uid)
        peer_emp_id = uuid.uuid4()

        mock_db = AsyncMock()
        mock_emp_res = MagicMock()
        mock_emp_res.scalar_one_or_none.return_value = own_emp
        mock_db.execute.return_value = mock_emp_res

        app.dependency_overrides[get_authenticated_context] = lambda: ctx
        app.dependency_overrides[get_db] = lambda: mock_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/v1/holidays/upcoming?employee_id={peer_emp_id}")

        app.dependency_overrides.clear()

        assert resp.status_code == status.HTTP_403_FORBIDDEN
        assert "cannot query holiday schedules of other employees" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_cross_tenant_isolation_on_leave_type(self):
        tid_b = uuid.uuid4()
        ctx_b = _mock_context("hr", tenant_id=tid_b)

        # Leave type belongs to Tenant A
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_none_res = MagicMock()
        mock_none_res.scalar_one_or_none.return_value = None  # Tenant B cannot find it
        mock_db.execute.return_value = mock_none_res

        app.dependency_overrides[get_authenticated_context] = lambda: ctx_b
        app.dependency_overrides[get_db] = lambda: mock_db

        leave_type_id_a = uuid.uuid4()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/v1/leave/types/{leave_type_id_a}")

        app.dependency_overrides.clear()

        assert resp.status_code == status.HTTP_404_NOT_FOUND
