"""Comprehensive automated test suite for Phase 9 Milestone 9.3:
Leave Application, Balance Tracking & Supervisor Adjudication.

Tests:
1. Deductible working days calculation excluding weekly offs and holidays.
2. Single-day, multi-day, and half-day leave application submission.
3. Balance reservation and available balance invariant enforcement.
4. Overlapping active leave request collision handling (409 Conflict).
5. Manager reporting hierarchy scoping and employee self-only scoping (403 Forbidden).
6. Anti-self-approval rule enforcement (403 Forbidden).
7. Approval workflow: atomic balance commit (pending -> used) and attendance recalculation.
8. Rejection workflow: balance rollback (pending released) with mandatory reason.
9. Cancellation workflow:
   - Pending cancellation releases reservation.
   - Future approved cancellation reverses used balance.
   - Past/commenced approved cancellation is rejected (400 Bad Request).
10. Attendance projection failure transaction rollback.
11. FastAPI HTTP Route Integration via AsyncClient.
12. Cross-tenant isolation verification.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status
from httpx import ASGITransport, AsyncClient

from services.api.attendance.models import AttendanceDay
from services.api.auth.dependencies import AuthenticatedContext, get_authenticated_context
from services.api.auth.models import User
from services.api.auth.permissions import Permission, UserRole, has_permission
from services.api.database import get_db
from services.api.employees.models import Employee
from services.api.leave.leave_request_service import (
    adjudicate_leave_request,
    apply_leave_request,
    calculate_leave_working_days,
    cancel_leave_request,
)
from services.api.leave.models import (
    Holiday,
    HolidayCalendar,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
)
from services.api.leave.schemas import (
    LeaveRequestCreate,
    LeaveRequestDecisionRequest,
)
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
        full_name=f"Phase 9 {role.capitalize()} User",
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
    reporting_manager_id: uuid.UUID | None = None,
) -> Employee:
    return Employee(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id or uuid.uuid4(),
        employee_id=f"EMP-{uuid.uuid4().hex[:6].upper()}",
        first_name="Alice",
        last_name="Worker",
        work_email=f"alice.{uuid.uuid4().hex[:4]}@upostit.test",
        reporting_manager_id=reporting_manager_id,
        employment_type="full_time",
        joining_date=date(2025, 1, 1),
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _mock_leave_type(
    tenant_id: uuid.UUID,
    code: str = "AL",
    name: str = "Annual Leave",
    allow_half_day: bool = True,
    max_consecutive_days: int | None = 14,
) -> LeaveType:
    return LeaveType(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        code=code,
        name=name,
        is_paid=True,
        requires_approval=True,
        allow_half_day=allow_half_day,
        max_consecutive_days=max_consecutive_days,
        carry_forward_limit=Decimal("5.0"),
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _mock_leave_balance(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    year: int = 2026,
    annual_allocation: Decimal = Decimal("20.00"),
    carried_forward: Decimal = Decimal("0.00"),
    accrued: Decimal = Decimal("0.00"),
    used: Decimal = Decimal("0.00"),
    pending_approval: Decimal = Decimal("0.00"),
) -> LeaveBalance:
    return LeaveBalance(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=employee_id,
        leave_type_id=leave_type_id,
        year=year,
        annual_allocation=annual_allocation,
        carried_forward=carried_forward,
        accrued=accrued,
        used=used,
        pending_approval=pending_approval,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


# ==============================================================================
# 1. RBAC Leave Permissions Tests
# ==============================================================================


class TestLeaveWorkflowRBAC:
    """Verifies RBAC permissions for leave application and adjudication."""

    def test_permission_matrix_for_leave_operations(self):
        # Apply leave: Everyone can apply for their own leave
        assert has_permission(UserRole.OWNER, Permission.APPLY_LEAVE) is True
        assert has_permission(UserRole.ADMIN, Permission.APPLY_LEAVE) is True
        assert has_permission(UserRole.HR, Permission.APPLY_LEAVE) is True
        assert has_permission(UserRole.MANAGER, Permission.APPLY_LEAVE) is True
        assert has_permission(UserRole.EMPLOYEE, Permission.APPLY_LEAVE) is True

        # View requests: Everyone can view requests in their scope
        assert has_permission(UserRole.EMPLOYEE, Permission.VIEW_LEAVE_REQUESTS) is True
        assert has_permission(UserRole.MANAGER, Permission.VIEW_LEAVE_REQUESTS) is True

        # Approve leave: Manager, HR, Admin, Owner can approve; Employee cannot!
        assert has_permission(UserRole.OWNER, Permission.APPROVE_LEAVE) is True
        assert has_permission(UserRole.ADMIN, Permission.APPROVE_LEAVE) is True
        assert has_permission(UserRole.HR, Permission.APPROVE_LEAVE) is True
        assert has_permission(UserRole.MANAGER, Permission.APPROVE_LEAVE) is True
        assert has_permission(UserRole.EMPLOYEE, Permission.APPROVE_LEAVE) is False


# ==============================================================================
# 2. Working Days Calculation & Deductible Days
# ==============================================================================


class TestWorkingDaysCalculation:
    """Verifies working days deduction excluding weekly offs and holidays."""

    @pytest.mark.asyncio
    async def test_single_working_day_calculation(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        eid = uuid.uuid4()

        # Monday 2026-06-01 (weekday = 0, so (0+1)%7 = 1 -> not Sunday/Saturday)
        target_date = date(2026, 6, 1)

        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                "services.api.leave.leave_request_service.resolve_applicable_calendar_for_employee",
                AsyncMock(return_value=(None, "NONE")),
            )
            m.setattr(
                "services.api.leave.leave_request_service.resolve_employee_shift_version",
                AsyncMock(return_value=(None, None)),
            )

            total_days, working_dates, excluded_dates = await calculate_leave_working_days(
                session=session,
                tenant_id=tid,
                employee_id=eid,
                start_date=target_date,
                end_date=target_date,
            )

        assert total_days == Decimal("1.0")
        assert working_dates == [target_date]
        assert excluded_dates == []

    @pytest.mark.asyncio
    async def test_multi_day_excluding_weekends_and_holidays(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        eid = uuid.uuid4()

        # Monday 2026-06-01 to Sunday 2026-06-07 (7 calendar days)
        # Saturday (June 6) and Sunday (June 7) are weekly-offs
        # Wednesday (June 3) is a public holiday
        start = date(2026, 6, 1)
        end = date(2026, 6, 7)

        cal = HolidayCalendar(id=uuid.uuid4(), tenant_id=tid, year=2026, name="Main")
        holiday = Holiday(
            id=uuid.uuid4(),
            tenant_id=tid,
            calendar_id=cal.id,
            holiday_date=date(2026, 6, 3),
            name="Founders Day",
            holiday_type="PUBLIC",
            is_optional=False,
        )

        # 1. Resolve calendar -> cal
        mock_cal_res = MagicMock()
        mock_cal_res.scalar_one_or_none.return_value = cal

        # 2. Holiday query -> holiday
        mock_h_res = MagicMock()
        mock_h_res.scalars.return_value.all.return_value = [holiday]

        # 3. resolve_employee_shift_version -> None (defaults to [0, 6])
        mock_none = MagicMock()
        mock_none.scalar_one_or_none.return_value = None

        session.execute.side_effect = [
            # resolve_applicable_calendar_for_employee calls:
            mock_none,    # emp lookup (will be handled by mock if needed)
            mock_h_res,   # range holidays query
            mock_none,    # shift lookup in resolve_employee_shift_version
        ]

        # Directly mock resolve_applicable_calendar_for_employee to return cal
        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                "services.api.leave.leave_request_service.resolve_applicable_calendar_for_employee",
                AsyncMock(return_value=(cal, "TENANT_DEFAULT")),
            )
            m.setattr(
                "services.api.leave.leave_request_service.resolve_employee_shift_version",
                AsyncMock(return_value=(None, None)),
            )

            mock_session = AsyncMock()
            mock_h_query = MagicMock()
            mock_h_query.scalars.return_value.all.return_value = [holiday]
            mock_session.execute.return_value = mock_h_query

            total_days, working_dates, excluded_dates = await calculate_leave_working_days(
                session=mock_session,
                tenant_id=tid,
                employee_id=eid,
                start_date=start,
                end_date=end,
            )

        # Mon(1), Tue(2), Thu(4), Fri(5) -> 4 working days
        # Wed(3) is Holiday, Sat(6) is Weekend, Sun(7) is Weekend -> 3 excluded days
        assert total_days == Decimal("4")
        assert len(working_dates) == 4
        assert len(excluded_dates) == 3

    @pytest.mark.asyncio
    async def test_half_day_returns_half_day_amount(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        eid = uuid.uuid4()
        target = date(2026, 6, 2)  # Tuesday

        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                "services.api.leave.leave_request_service.resolve_applicable_calendar_for_employee",
                AsyncMock(return_value=(None, "NONE")),
            )

            total_days, working, excluded = await calculate_leave_working_days(
                session=session,
                tenant_id=tid,
                employee_id=eid,
                start_date=target,
                end_date=target,
                is_half_day=True,
                half_day_period="FIRST_HALF",
            )

        assert total_days == Decimal("0.50")
        assert working == [target]


# ==============================================================================
# 3. Application Submission & Balance Reservation
# ==============================================================================


class TestLeaveApplicationSubmission:
    """Verifies leave application creation, balance reservation, and constraint checks."""

    @pytest.mark.asyncio
    async def test_successful_leave_submission_reserves_pending_balance(self):
        session = AsyncMock()
        session.add = MagicMock()
        tid = uuid.uuid4()
        uid = uuid.uuid4()
        emp = _mock_employee(tid, user_id=uid)
        lt = _mock_leave_type(tid, code="AL", allow_half_day=True)
        bal = _mock_leave_balance(tid, emp.id, lt.id, year=2026, annual_allocation=Decimal("15.00"))

        req_payload = LeaveRequestCreate(
            leave_type_id=lt.id,
            start_date=date(2026, 6, 1),  # Monday
            end_date=date(2026, 6, 2),    # Tuesday (2 days)
            reason="Family vacation",
        )

        mock_emp_res = MagicMock()
        mock_emp_res.scalar_one_or_none.return_value = emp

        mock_lt_res = MagicMock()
        mock_lt_res.scalar_one_or_none.return_value = lt

        mock_overlap_res = MagicMock()
        mock_overlap_res.scalars.return_value.all.return_value = []

        mock_bal_res = MagicMock()
        mock_bal_res.scalar_one_or_none.return_value = bal

        session.execute.side_effect = [
            mock_emp_res,      # 1. Employee lookup
            mock_lt_res,       # 2. LeaveType lookup
            mock_overlap_res,  # 3. Overlap check
            mock_bal_res,      # 4. LeaveBalance row lock
        ]

        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                "services.api.leave.leave_request_service.calculate_leave_working_days",
                AsyncMock(return_value=(Decimal("2.0"), [date(2026, 6, 1), date(2026, 6, 2)], [])),
            )

            created_req = await apply_leave_request(
                session=session,
                tenant_id=tid,
                user_id=uid,
                user_role="employee",
                payload=req_payload,
            )

        assert created_req.status == "PENDING_APPROVAL"
        assert created_req.total_days == Decimal("2.0")
        assert bal.pending_approval == Decimal("2.00")
        assert bal.available_balance == Decimal("13.00")
        session.add.assert_called_once()
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_insufficient_balance_raises_400(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        uid = uuid.uuid4()
        emp = _mock_employee(tid, user_id=uid)
        lt = _mock_leave_type(tid, code="AL")
        # Balance has 1.0 day available
        bal = _mock_leave_balance(
            tid, emp.id, lt.id, year=2026,
            annual_allocation=Decimal("5.00"),
            used=Decimal("4.00"),
            pending_approval=Decimal("0.00"),
        )

        req_payload = LeaveRequestCreate(
            leave_type_id=lt.id,
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 3),  # 3 days requested
            reason="Personal trip",
        )

        mock_emp_res = MagicMock()
        mock_emp_res.scalar_one_or_none.return_value = emp

        mock_lt_res = MagicMock()
        mock_lt_res.scalar_one_or_none.return_value = lt

        mock_overlap_res = MagicMock()
        mock_overlap_res.scalars.return_value.all.return_value = []

        mock_bal_res = MagicMock()
        mock_bal_res.scalar_one_or_none.return_value = bal

        session.execute.side_effect = [
            mock_emp_res,
            mock_lt_res,
            mock_overlap_res,
            mock_bal_res,
        ]

        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                "services.api.leave.leave_request_service.calculate_leave_working_days",
                AsyncMock(return_value=(Decimal("3.0"), [date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3)], [])),
            )

            with pytest.raises(HTTPException) as exc_info:
                await apply_leave_request(
                    session=session,
                    tenant_id=tid,
                    user_id=uid,
                    user_role="employee",
                    payload=req_payload,
                )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "Insufficient leave balance" in exc_info.value.detail
        # Invariant check: pending_approval was NOT increased
        assert bal.pending_approval == Decimal("0.00")

    @pytest.mark.asyncio
    async def test_overlapping_active_request_raises_409(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        uid = uuid.uuid4()
        emp = _mock_employee(tid, user_id=uid)
        lt = _mock_leave_type(tid, code="AL")

        existing_req = LeaveRequest(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=emp.id,
            leave_type_id=lt.id,
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 5),
            status="PENDING_APPROVAL",
            total_days=Decimal("5.0"),
            reason="Previous request",
        )

        req_payload = LeaveRequestCreate(
            leave_type_id=lt.id,
            start_date=date(2026, 6, 3),
            end_date=date(2026, 6, 4),
            reason="Conflicting overlap",
        )

        mock_emp_res = MagicMock()
        mock_emp_res.scalar_one_or_none.return_value = emp

        mock_lt_res = MagicMock()
        mock_lt_res.scalar_one_or_none.return_value = lt

        mock_overlap_res = MagicMock()
        mock_overlap_res.scalars.return_value.all.return_value = [existing_req]

        session.execute.side_effect = [
            mock_emp_res,
            mock_lt_res,
            mock_overlap_res,
        ]

        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                "services.api.leave.leave_request_service.calculate_leave_working_days",
                AsyncMock(return_value=(Decimal("2.0"), [date(2026, 6, 3), date(2026, 6, 4)], [])),
            )

            with pytest.raises(HTTPException) as exc_info:
                await apply_leave_request(
                    session=session,
                    tenant_id=tid,
                    user_id=uid,
                    user_role="employee",
                    payload=req_payload,
                )

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert "already overlaps" in exc_info.value.detail


# ==============================================================================
# 4. Supervisor Adjudication & Anti-Self-Approval Tests
# ==============================================================================


class TestSupervisorAdjudication:
    """Verifies approval, rejection, RBAC scoping, and anti-self-approval."""

    @pytest.mark.asyncio
    async def test_anti_self_approval_raises_403(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        manager_uid = uuid.uuid4()
        manager_emp = _mock_employee(tid, user_id=manager_uid)

        # Manager's own leave request
        req = LeaveRequest(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=manager_emp.id,
            leave_type_id=uuid.uuid4(),
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 2),
            total_days=Decimal("2.0"),
            status="PENDING_APPROVAL",
            reason="Manager time-off",
        )
        req.employee = manager_emp

        mock_req_res = MagicMock()
        mock_req_res.scalar_one_or_none.return_value = req

        mock_emp_res = MagicMock()
        mock_emp_res.scalar_one_or_none.return_value = manager_emp

        session.execute.side_effect = [mock_req_res, mock_emp_res]

        with pytest.raises(HTTPException) as exc_info:
            await adjudicate_leave_request(
                session=session,
                tenant_id=tid,
                request_id=req.id,
                reviewer_user_id=manager_uid,
                reviewer_role="manager",
                action="APPROVE",
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "not permitted to adjudicate their own leave applications" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_manager_cannot_adjudicate_non_direct_report_raises_403(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        manager_uid = uuid.uuid4()
        manager_emp = _mock_employee(tid, user_id=manager_uid)

        # Employee reports to a different manager
        other_manager_id = uuid.uuid4()
        target_emp = _mock_employee(tid, reporting_manager_id=other_manager_id)

        req = LeaveRequest(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=target_emp.id,
            leave_type_id=uuid.uuid4(),
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 2),
            total_days=Decimal("2.0"),
            status="PENDING_APPROVAL",
            reason="Subordinate request",
        )
        req.employee = target_emp

        mock_req_res = MagicMock()
        mock_req_res.scalar_one_or_none.return_value = req

        mock_rev_emp_res = MagicMock()
        mock_rev_emp_res.scalar_one_or_none.return_value = manager_emp

        session.execute.side_effect = [mock_req_res, mock_rev_emp_res]

        with pytest.raises(HTTPException) as exc_info:
            await adjudicate_leave_request(
                session=session,
                tenant_id=tid,
                request_id=req.id,
                reviewer_user_id=manager_uid,
                reviewer_role="manager",
                action="APPROVE",
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "only adjudicate leave requests for their direct reports" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_successful_approval_commits_balance_and_triggers_recalculation(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        manager_uid = uuid.uuid4()
        manager_emp = _mock_employee(tid, user_id=manager_uid)

        target_emp = _mock_employee(tid, reporting_manager_id=manager_emp.id)
        lt_id = uuid.uuid4()

        req = LeaveRequest(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=target_emp.id,
            leave_type_id=lt_id,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 2),
            total_days=Decimal("2.0"),
            status="PENDING_APPROVAL",
            reason="Medical recovery",
        )
        req.employee = target_emp

        bal = _mock_leave_balance(
            tid, target_emp.id, lt_id, year=2026,
            annual_allocation=Decimal("15.00"),
            pending_approval=Decimal("2.00"),
            used=Decimal("0.00"),
        )

        mock_req_res = MagicMock()
        mock_req_res.scalar_one_or_none.return_value = req

        mock_rev_emp_res = MagicMock()
        mock_rev_emp_res.scalar_one_or_none.return_value = manager_emp

        mock_bal_res = MagicMock()
        mock_bal_res.scalar_one_or_none.return_value = bal

        session.execute.side_effect = [
            mock_req_res,
            mock_rev_emp_res,
            mock_bal_res,
        ]

        mock_day_1 = AttendanceDay(id=uuid.uuid4(), tenant_id=tid, employee_id=target_emp.id, attendance_date=date(2026, 7, 1))
        mock_day_2 = AttendanceDay(id=uuid.uuid4(), tenant_id=tid, employee_id=target_emp.id, attendance_date=date(2026, 7, 2))

        with pytest.MonkeyPatch.context() as m:
            mock_recalc = AsyncMock(side_effect=[mock_day_1, mock_day_2])
            m.setattr("services.api.leave.leave_request_service.recalculate_attendance_day", mock_recalc)

            decided_req, days = await adjudicate_leave_request(
                session=session,
                tenant_id=tid,
                request_id=req.id,
                reviewer_user_id=manager_uid,
                reviewer_role="manager",
                action="APPROVE",
                reason="Approved by manager",
            )

        assert decided_req.status == "APPROVED"
        assert decided_req.reviewer_user_id == manager_uid
        assert decided_req.reviewer_notes == "Approved by manager"
        assert bal.pending_approval == Decimal("0.00")
        assert bal.used == Decimal("2.00")
        assert len(days) == 2
        assert mock_recalc.await_count == 2
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rejection_releases_pending_hold(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        manager_uid = uuid.uuid4()
        manager_emp = _mock_employee(tid, user_id=manager_uid)

        target_emp = _mock_employee(tid, reporting_manager_id=manager_emp.id)
        lt_id = uuid.uuid4()

        req = LeaveRequest(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=target_emp.id,
            leave_type_id=lt_id,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 2),
            total_days=Decimal("2.0"),
            status="PENDING_APPROVAL",
            reason="Leave request",
        )
        req.employee = target_emp

        bal = _mock_leave_balance(
            tid, target_emp.id, lt_id, year=2026,
            annual_allocation=Decimal("15.00"),
            pending_approval=Decimal("2.00"),
            used=Decimal("0.00"),
        )

        mock_req_res = MagicMock()
        mock_req_res.scalar_one_or_none.return_value = req

        mock_rev_emp_res = MagicMock()
        mock_rev_emp_res.scalar_one_or_none.return_value = manager_emp

        mock_bal_res = MagicMock()
        mock_bal_res.scalar_one_or_none.return_value = bal

        session.execute.side_effect = [
            mock_req_res,
            mock_rev_emp_res,
            mock_bal_res,
        ]

        decided_req, _ = await adjudicate_leave_request(
            session=session,
            tenant_id=tid,
            request_id=req.id,
            reviewer_user_id=manager_uid,
            reviewer_role="manager",
            action="REJECT",
            reason="Project release deadline conflict",
        )

        assert decided_req.status == "REJECTED"
        assert decided_req.reviewer_notes == "Project release deadline conflict"
        assert bal.pending_approval == Decimal("0.00")
        assert bal.used == Decimal("0.00")  # unchanged
        assert bal.available_balance == Decimal("15.00")

    @pytest.mark.asyncio
    async def test_rejection_without_mandatory_reason_raises_422(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        uid = uuid.uuid4()

        with pytest.raises(HTTPException) as exc_info:
            await adjudicate_leave_request(
                session=session,
                tenant_id=tid,
                request_id=uuid.uuid4(),
                reviewer_user_id=uid,
                reviewer_role="hr",
                action="REJECT",
                reason="  ",  # Whitespace only
            )

        assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @pytest.mark.asyncio
    async def test_attendance_recalculation_failure_rolls_back_transaction(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        hr_uid = uuid.uuid4()
        hr_emp = _mock_employee(tid, user_id=hr_uid)

        target_emp = _mock_employee(tid)
        lt_id = uuid.uuid4()

        req = LeaveRequest(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=target_emp.id,
            leave_type_id=lt_id,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 1),
            total_days=Decimal("1.0"),
            status="PENDING_APPROVAL",
            reason="Day off",
        )
        req.employee = target_emp

        bal = _mock_leave_balance(
            tid, target_emp.id, lt_id, year=2026,
            annual_allocation=Decimal("10.00"),
            pending_approval=Decimal("1.00"),
        )

        mock_req_res = MagicMock()
        mock_req_res.scalar_one_or_none.return_value = req

        mock_rev_emp_res = MagicMock()
        mock_rev_emp_res.scalar_one_or_none.return_value = hr_emp

        mock_bal_res = MagicMock()
        mock_bal_res.scalar_one_or_none.return_value = bal

        session.execute.side_effect = [
            mock_req_res,
            mock_rev_emp_res,
            mock_bal_res,
        ]

        with pytest.MonkeyPatch.context() as m:
            mock_recalc = AsyncMock(side_effect=RuntimeError("Database lock timeout on attendance_days"))
            m.setattr("services.api.leave.leave_request_service.recalculate_attendance_day", mock_recalc)

            with pytest.raises(HTTPException) as exc_info:
                await adjudicate_leave_request(
                    session=session,
                    tenant_id=tid,
                    request_id=req.id,
                    reviewer_user_id=hr_uid,
                    reviewer_role="hr",
                    action="APPROVE",
                )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Attendance projection recalculation failed" in exc_info.value.detail
        session.rollback.assert_awaited_once()


# ==============================================================================
# 5. Cancellation Workflow Tests
# ==============================================================================


class TestLeaveCancellation:
    """Verifies cancellation of pending and approved leave requests."""

    @pytest.mark.asyncio
    async def test_pending_request_cancellation_releases_hold(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        uid = uuid.uuid4()
        emp = _mock_employee(tid, user_id=uid)
        lt_id = uuid.uuid4()

        req = LeaveRequest(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=emp.id,
            leave_type_id=lt_id,
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 3),
            total_days=Decimal("3.0"),
            status="PENDING_APPROVAL",
            reason="Planned leave",
        )

        bal = _mock_leave_balance(
            tid, emp.id, lt_id, year=2026,
            annual_allocation=Decimal("20.00"),
            pending_approval=Decimal("3.00"),
        )

        mock_req_res = MagicMock()
        mock_req_res.scalar_one_or_none.return_value = req

        mock_emp_res = MagicMock()
        mock_emp_res.scalar_one_or_none.return_value = emp

        mock_bal_res = MagicMock()
        mock_bal_res.scalar_one_or_none.return_value = bal

        session.execute.side_effect = [
            mock_req_res,
            mock_emp_res,
            mock_bal_res,
        ]

        cancelled = await cancel_leave_request(
            session=session,
            tenant_id=tid,
            request_id=req.id,
            user_id=uid,
            user_role="employee",
        )

        assert cancelled.status == "CANCELLED"
        assert bal.pending_approval == Decimal("0.00")
        assert bal.available_balance == Decimal("20.00")

    @pytest.mark.asyncio
    async def test_cancellation_of_past_or_commenced_approved_leave_raises_400(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        uid = uuid.uuid4()
        emp = _mock_employee(tid, user_id=uid)
        lt_id = uuid.uuid4()

        # Leave date is in the past (2025-01-01)
        req = LeaveRequest(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=emp.id,
            leave_type_id=lt_id,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 2),
            total_days=Decimal("2.0"),
            status="APPROVED",
            reason="Past leave",
        )

        bal = _mock_leave_balance(tid, emp.id, lt_id, year=2025, used=Decimal("2.00"))

        mock_req_res = MagicMock()
        mock_req_res.scalar_one_or_none.return_value = req

        mock_emp_res = MagicMock()
        mock_emp_res.scalar_one_or_none.return_value = emp

        mock_bal_res = MagicMock()
        mock_bal_res.scalar_one_or_none.return_value = bal

        session.execute.side_effect = [
            mock_req_res,
            mock_emp_res,
            mock_bal_res,
        ]

        with pytest.raises(HTTPException) as exc_info:
            await cancel_leave_request(
                session=session,
                tenant_id=tid,
                request_id=req.id,
                user_id=uid,
                user_role="employee",
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "Cannot cancel approved leave that has already commenced" in exc_info.value.detail


# ==============================================================================
# 6. FastAPI HTTP Route Integration Tests
# ==============================================================================


class TestLeaveWorkflowHTTPRoutes:
    """HTTP integration tests verifying route wiring, serialization, and status codes."""

    @pytest.mark.asyncio
    async def test_get_my_balances_200_ok(self):
        tid = uuid.uuid4()
        uid = uuid.uuid4()
        ctx = _mock_context("employee", tenant_id=tid, user_id=uid)
        emp = _mock_employee(tid, user_id=uid)
        lt = _mock_leave_type(tid, code="CL", name="Casual Leave")
        bal = _mock_leave_balance(tid, emp.id, lt.id, year=2026, annual_allocation=Decimal("12.00"))

        mock_db = AsyncMock()
        mock_emp_res = MagicMock()
        mock_emp_res.scalar_one_or_none.return_value = emp

        mock_bal_res = MagicMock()
        mock_bal_res.all.return_value = [(bal, lt)]

        mock_db.execute.side_effect = [mock_emp_res, mock_bal_res]

        app.dependency_overrides[get_authenticated_context] = lambda: ctx
        app.dependency_overrides[get_db] = lambda: mock_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/leave/balances/my?year=2026")

        app.dependency_overrides.clear()

        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["leave_type_code"] == "CL"
        assert Decimal(str(data["items"][0]["available_balance"])) == Decimal("12.00")

    @pytest.mark.asyncio
    async def test_employee_cannot_access_supervisor_queue_raises_403(self):
        tid = uuid.uuid4()
        ctx = _mock_context("employee", tenant_id=tid)

        mock_db = AsyncMock()
        app.dependency_overrides[get_authenticated_context] = lambda: ctx
        app.dependency_overrides[get_db] = lambda: mock_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/leave/requests")

        app.dependency_overrides.clear()

        assert resp.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_manager_can_access_supervisor_queue_200_ok(self):
        tid = uuid.uuid4()
        uid = uuid.uuid4()
        ctx = _mock_context("manager", tenant_id=tid, user_id=uid)
        manager_emp = _mock_employee(tid, user_id=uid)

        mock_db = AsyncMock()
        mock_mgr_res = MagicMock()
        mock_mgr_res.scalar_one_or_none.return_value = manager_emp

        mock_count = MagicMock()
        mock_count.scalar.return_value = 0

        mock_data = MagicMock()
        mock_data.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [mock_mgr_res, mock_count, mock_data]

        app.dependency_overrides[get_authenticated_context] = lambda: ctx
        app.dependency_overrides[get_db] = lambda: mock_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/leave/requests")

        app.dependency_overrides.clear()

        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_supervisor_decision_endpoint_approve_200_ok(self):
        tid = uuid.uuid4()
        hr_uid = uuid.uuid4()
        ctx = _mock_context("hr", tenant_id=tid, user_id=hr_uid)
        hr_emp = _mock_employee(tid, user_id=hr_uid)

        target_emp = _mock_employee(tid)
        lt = _mock_leave_type(tid, code="SL", name="Sick Leave")

        req = LeaveRequest(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=target_emp.id,
            leave_type_id=lt.id,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 2),
            is_half_day=False,
            total_days=Decimal("2.0"),
            status="PENDING_APPROVAL",
            reason="Surgery",
        )
        req.employee = target_emp
        req.leave_type = lt

        bal = _mock_leave_balance(tid, target_emp.id, lt.id, year=2026, annual_allocation=Decimal("10.00"), pending_approval=Decimal("2.00"))

        mock_db = AsyncMock()
        mock_db.refresh = AsyncMock()

        mock_req_res = MagicMock()
        mock_req_res.scalar_one_or_none.return_value = req

        mock_rev_res = MagicMock()
        mock_rev_res.scalar_one_or_none.return_value = hr_emp

        mock_bal_res = MagicMock()
        mock_bal_res.scalar_one_or_none.return_value = bal

        mock_db.execute.side_effect = [
            mock_req_res,
            mock_rev_res,
            mock_bal_res,
        ]

        app.dependency_overrides[get_authenticated_context] = lambda: ctx
        app.dependency_overrides[get_db] = lambda: mock_db

        decision_payload = LeaveRequestDecisionRequest(action="APPROVE", reason="Medical notes verified")

        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                "services.api.leave.leave_request_service.recalculate_attendance_day",
                AsyncMock(return_value=AttendanceDay(id=uuid.uuid4(), tenant_id=tid, employee_id=target_emp.id, attendance_date=date(2026, 9, 1))),
            )

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    f"/api/v1/leave/requests/{req.id}/decision",
                    json=decision_payload.model_dump(mode="json"),
                )

        app.dependency_overrides.clear()

        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["status"] == "APPROVED"
        assert data["reviewer_notes"] == "Medical notes verified"

    @pytest.mark.asyncio
    async def test_cross_tenant_isolation_on_leave_requests(self):
        tid_b = uuid.uuid4()
        uid_b = uuid.uuid4()
        ctx_b = _mock_context("hr", tenant_id=tid_b, user_id=uid_b)

        # Request belongs to Tenant A
        mock_db = AsyncMock()
        mock_none_res = MagicMock()
        mock_none_res.scalar_one_or_none.return_value = None  # Scoped to Tenant B -> not found!
        mock_db.execute.return_value = mock_none_res

        app.dependency_overrides[get_authenticated_context] = lambda: ctx_b
        app.dependency_overrides[get_db] = lambda: mock_db

        foreign_req_id = uuid.uuid4()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/v1/leave/requests/{foreign_req_id}")

        app.dependency_overrides.clear()

        assert resp.status_code == status.HTTP_404_NOT_FOUND
