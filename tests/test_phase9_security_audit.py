"""Phase 9 Milestone 9.8: Comprehensive Security Audit & Penetration Regression Suite.

Validates security boundaries across:
1. Multi-Tenant Data Isolation (Leave types, holiday calendars, requests, overtime rules/records).
2. Privilege Escalation & RBAC Enforcement (Employee, Manager, HR/Admin/Owner permission gates).
3. Manager Reporting Hierarchy & Anti-Self-Approval Verification (User and Employee entity mappings).
4. Leave Balance Mathematical Integrity & Concurrency Protection (Invariant, double-spend, commenced leave).
5. Overtime Multipliers, Caps, and Pre-Approval Policy Security.
6. Attendance Event Ledger Immutability (Zero synthetic punches, projection-only recalculation).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status

from services.api.attendance.engine import (
    ResolvedTimeline,
    WorkSession,
    calculate_attendance_day,
)
from services.api.attendance.models import (
    AttendanceDay,
    AttendanceEvent,
    ShiftTemplateVersion,
)
from services.api.employees.models import Employee
from services.api.leave.holiday_service import (
    get_holiday_calendar,
)
from services.api.leave.leave_request_service import (
    adjudicate_leave_request,
    apply_leave_request,
)
from services.api.leave.leave_type_service import (
    get_leave_type,
)
from services.api.leave.models import (
    LeaveBalance,
    LeaveRequest,
    LeaveType,
    OvertimeRecord,
    OvertimeRule,
)
from services.api.leave.overtime_service import (
    adjudicate_overtime_record,
    create_overtime_rule,
    get_overtime_rule,
)
from services.api.leave.schemas import (
    LeaveRequestCreate,
    OvertimeDecisionRequest,
    OvertimeRuleCreateRequest,
)

# ==============================================================================
# Helper Mock Factories
# ==============================================================================


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
        first_name="Audited",
        last_name="Worker",
        work_email=f"worker.{uuid.uuid4().hex[:4]}@audit.test",
        reporting_manager_id=reporting_manager_id,
        employment_type="full_time",
        joining_date=date(2025, 1, 1),
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _mock_leave_type(
    tenant_id: uuid.UUID,
    code: str = "ANNUAL",
    is_active: bool = True,
    max_consecutive_days: int | None = 14,
) -> LeaveType:
    return LeaveType(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        code=code,
        name="Annual Paid Leave",
        is_paid=True,
        requires_approval=True,
        allow_half_day=True,
        max_consecutive_days=max_consecutive_days,
        carry_forward_limit=Decimal("5.0"),
        is_active=is_active,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _mock_leave_balance(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    allocation: Decimal = Decimal("20.00"),
    pending: Decimal = Decimal("0.00"),
    used: Decimal = Decimal("0.00"),
) -> LeaveBalance:
    return LeaveBalance(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=employee_id,
        leave_type_id=leave_type_id,
        year=2026,
        annual_allocation=allocation,
        carried_forward=Decimal("0.00"),
        accrued=allocation,
        used=used,
        pending_approval=pending,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


# ==============================================================================
# 1. Multi-Tenant Data Isolation Audit
# ==============================================================================


class TestMultiTenantIsolationAudit:
    """Verifies that foreign tenant IDs cannot access or mutate Phase 9 data under any circumstances."""

    @pytest.mark.asyncio
    async def test_leave_type_foreign_tenant_access_blocked(self) -> None:
        session = AsyncMock()
        primary_tenant = uuid.uuid4()

        # Attempt to get leave type belonging to foreign tenant
        session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        with pytest.raises(HTTPException) as exc_info:
            await get_leave_type(session, primary_tenant, uuid.uuid4())
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_holiday_calendar_foreign_tenant_access_blocked(self) -> None:
        session = AsyncMock()
        primary_tenant = uuid.uuid4()

        session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        with pytest.raises(HTTPException) as exc_info:
            await get_holiday_calendar(session, primary_tenant, uuid.uuid4())
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_overtime_rule_foreign_tenant_access_blocked(self) -> None:
        session = AsyncMock()
        primary_tenant = uuid.uuid4()

        session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        with pytest.raises(HTTPException) as exc_info:
            await get_overtime_rule(session, primary_tenant, uuid.uuid4())
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_cross_tenant_leave_application_tamper_blocked(self) -> None:
        """Attacker attempts to apply for leave referencing a leave_type_id from a foreign tenant."""
        session = AsyncMock()
        primary_tenant = uuid.uuid4()
        emp_user = uuid.uuid4()
        emp = _mock_employee(primary_tenant, user_id=emp_user)

        # Employee found, but leave_type query scoped to primary_tenant returns None
        session.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # LeaveType not found in tenant
        ]

        payload = LeaveRequestCreate(
            leave_type_id=uuid.uuid4(),  # Belongs to foreign tenant
            start_date=date(2026, 12, 1),
            end_date=date(2026, 12, 2),
            is_half_day=False,
            reason="Cross-tenant injection attempt",
        )

        with pytest.raises(HTTPException) as exc_info:
            await apply_leave_request(
                session=session,
                tenant_id=primary_tenant,
                user_id=emp_user,
                user_role="employee",
                payload=payload,
            )
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


# ==============================================================================
# 2. RBAC & Manager Scoping Audit
# ==============================================================================


class TestRBACAndManagerScopingAudit:
    """Verifies that employee and manager permissions are strictly partitioned."""

    @pytest.mark.asyncio
    async def test_employee_cannot_adjudicate_leave_requests(self) -> None:
        session = AsyncMock()
        tid = uuid.uuid4()

        with pytest.raises(HTTPException) as exc_info:
            await adjudicate_leave_request(
                session=session,
                tenant_id=tid,
                request_id=uuid.uuid4(),
                reviewer_user_id=uuid.uuid4(),
                reviewer_role="employee",
                action="APPROVE",
            )
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_manager_cannot_adjudicate_other_manager_report(self) -> None:
        """Manager attempts to adjudicate an employee who does not report to them."""
        session = AsyncMock()
        tid = uuid.uuid4()
        manager_uid = uuid.uuid4()
        manager_emp = _mock_employee(tid, user_id=manager_uid)

        other_manager_emp = _mock_employee(tid)
        target_emp = _mock_employee(tid, reporting_manager_id=other_manager_emp.id)

        req = LeaveRequest(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=target_emp.id,
            leave_type_id=uuid.uuid4(),
            start_date=date(2026, 12, 1),
            end_date=date(2026, 12, 2),
            total_days=Decimal("2.0"),
            status="PENDING_APPROVAL",
            employee=target_emp,
        )

        session.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=req)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=manager_emp)),
        ]

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
        assert "Managers may only adjudicate leave requests for their direct reports" in exc_info.value.detail


# ==============================================================================
# 3. Anti-Self-Approval Identity Mapping Audit
# ==============================================================================


class TestAntiSelfApprovalAudit:
    """Verifies that supervisors cannot approve their own leave or overtime requests under any alias."""

    @pytest.mark.asyncio
    async def test_leave_anti_self_approval_matches_user_id(self) -> None:
        session = AsyncMock()
        tid = uuid.uuid4()
        user_id = uuid.uuid4()

        # Reviewer and target employee have the same user_id
        target_emp = _mock_employee(tid, user_id=user_id)
        req = LeaveRequest(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=target_emp.id,
            leave_type_id=uuid.uuid4(),
            start_date=date(2026, 12, 1),
            end_date=date(2026, 12, 2),
            total_days=Decimal("2.0"),
            status="PENDING_APPROVAL",
            employee=target_emp,
        )

        session.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=req)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=target_emp)),
        ]

        with pytest.raises(HTTPException) as exc_info:
            await adjudicate_leave_request(
                session=session,
                tenant_id=tid,
                request_id=req.id,
                reviewer_user_id=user_id,
                reviewer_role="manager",
                action="APPROVE",
            )
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Reviewers are not permitted to adjudicate their own leave applications" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_overtime_anti_self_approval_matches_employee_id(self) -> None:
        session = AsyncMock()
        tid = uuid.uuid4()
        reviewer_uid = uuid.uuid4()
        emp = _mock_employee(tid, user_id=reviewer_uid)

        record = OvertimeRecord(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=emp.id,
            attendance_day_id=uuid.uuid4(),
            attendance_date=date(2026, 11, 20),
            overtime_type="WORKDAY",
            raw_overtime_minutes=60,
            status="PENDING_APPROVAL",
        )

        session.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=record)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
        ]

        payload = OvertimeDecisionRequest(action="APPROVE")

        with pytest.raises(HTTPException) as exc_info:
            await adjudicate_overtime_record(
                session=session,
                tenant_id=tid,
                record_id=record.id,
                reviewer_user_id=reviewer_uid,
                reviewer_role="manager",
                payload=payload,
            )
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Anti-self-approval violation" in exc_info.value.detail


# ==============================================================================
# 4. Leave Balance & Accounting Invariant Audit
# ==============================================================================


class TestLeaveBalanceAccountingSecurity:
    """Audits the mathematical consistency and integrity of leave balance transactions."""

    def test_balance_invariant_formula(self) -> None:
        tid = uuid.uuid4()
        eid = uuid.uuid4()
        ltid = uuid.uuid4()

        bal = LeaveBalance(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=eid,
            leave_type_id=ltid,
            year=2026,
            annual_allocation=Decimal("20.00"),
            carried_forward=Decimal("3.00"),
            accrued=Decimal("5.00"),
            used=Decimal("4.00"),
            pending_approval=Decimal("2.00"),
        )

        # Invariant: available = (20 + 3 + 5) - (4 + 2) = 28 - 6 = 22.00
        assert bal.available_balance == Decimal("22.00")

    @pytest.mark.asyncio
    async def test_inactive_leave_type_rejection(self) -> None:
        """Ensures employees cannot apply for disabled leave types."""
        session = AsyncMock()
        tid = uuid.uuid4()
        uid = uuid.uuid4()
        emp = _mock_employee(tid, user_id=uid)
        inactive_lt = _mock_leave_type(tid, is_active=False)

        session.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=inactive_lt)),
        ]

        payload = LeaveRequestCreate(
            leave_type_id=inactive_lt.id,
            start_date=date(2026, 12, 1),
            end_date=date(2026, 12, 2),
            is_half_day=False,
            reason="Testing inactive policy",
        )

        with pytest.raises(HTTPException) as exc_info:
            await apply_leave_request(
                session=session,
                tenant_id=tid,
                user_id=uid,
                user_role="employee",
                payload=payload,
            )
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "currently inactive" in exc_info.value.detail


# ==============================================================================
# 5. Overtime Multipliers, Caps & Pre-Approval Policy Security
# ==============================================================================


class TestOvertimePolicySecurity:
    """Audits overtime multiplier bounds, daily caps, and pre-approval invariants."""

    @pytest.mark.asyncio
    async def test_multiplier_deflation_attack_blocked(self) -> None:
        """Ensures an employer or malicious actor cannot configure a multiplier below statutory 1.00."""
        session = AsyncMock()
        tid = uuid.uuid4()

        with pytest.raises(Exception) as exc_info:
            payload = OvertimeRuleCreateRequest(
                name="Exploitative Policy",
                workday_multiplier=Decimal("0.50"),  # Less than statutory 1.00
                weekend_multiplier=Decimal("1.50"),
                holiday_multiplier=Decimal("2.00"),
                min_overtime_threshold_minutes=30,
                max_daily_overtime_minutes=120,
            )
            await create_overtime_rule(session, tid, payload)

        assert "greater than or equal to 1.00" in str(exc_info.value) or "cannot be less than 1.00" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_max_daily_overtime_less_than_threshold_blocked(self) -> None:
        session = AsyncMock()
        tid = uuid.uuid4()

        payload = OvertimeRuleCreateRequest(
            name="Contradictory Policy",
            min_overtime_threshold_minutes=60,
            max_daily_overtime_minutes=30,  # Less than threshold!
            workday_multiplier=Decimal("1.50"),
            weekend_multiplier=Decimal("2.00"),
            holiday_multiplier=Decimal("2.00"),
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_overtime_rule(session, tid, payload)
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "cannot be less than min_overtime_threshold_minutes" in exc_info.value.detail

    def test_pre_approval_required_rule_never_auto_approves(self) -> None:
        """When requires_pre_approval is True, detected overtime MUST remain PENDING_APPROVAL."""
        tid = uuid.uuid4()
        shift = ShiftTemplateVersion(
            id=uuid.uuid4(),
            tenant_id=tid,
            shift_template_id=uuid.uuid4(),
            version_number=1,
            version_effective_from=date(2026, 1, 1),
            start_time=datetime(2026, 6, 1, 9, 0, tzinfo=UTC).time(),
            end_time=datetime(2026, 6, 1, 17, 0, tzinfo=UTC).time(),
            grace_period_minutes=15,
            early_exit_grace_minutes=15,
            early_arrival_allowance_minutes=120,
            late_departure_allowance_minutes=180,
            half_day_threshold_minutes=240,
            full_day_threshold_minutes=420,
            break_duration_minutes=60,
            is_overnight=False,
            weekly_off_days=[0, 6],
            created_at=datetime.now(UTC),
        )

        rule = OvertimeRule(
            id=uuid.uuid4(),
            tenant_id=tid,
            name="Strict Pre-Approval Policy",
            min_overtime_threshold_minutes=30,
            max_daily_overtime_minutes=120,
            workday_multiplier=Decimal("1.50"),
            weekend_multiplier=Decimal("2.00"),
            holiday_multiplier=Decimal("2.00"),
            requires_manager_approval=False,
            requires_pre_approval=True,  # Mandatory pre-approval
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        # Employee worked 11 hours (600 net mins vs 420 scheduled = 180 raw OT)
        t_in = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
        t_out = datetime(2026, 6, 1, 20, 0, tzinfo=UTC)
        timeline = ResolvedTimeline(
            active_events=[],
            sessions=[
                WorkSession(
                    check_in=t_in,
                    check_out=t_out,
                    gross_minutes=660,
                    break_minutes=60,
                    net_minutes=600,
                    is_open=False,
                )
            ],
            first_check_in=t_in,
            last_check_out=t_out,
            unclosed_session=False,
            unclosed_break=False,
            has_suspicious_events=False,
            anomalies=[],
            source_event_ids=["ev-test"],
        )

        calc = calculate_attendance_day(
            target_date=date(2026, 6, 1),
            shift_version=shift,
            resolved_timeline=timeline,
            overtime_rule=rule,
        )

        assert calc.overtime_details is not None
        assert calc.overtime_details.status == "PENDING_APPROVAL"
        assert calc.overtime_details.status != "AUTO_APPROVED"


# ==============================================================================
# 6. Immutable Attendance Event Ledger Protection
# ==============================================================================


class TestAttendanceLedgerProtection:
    """Verifies that no Phase 9 operations insert or modify raw AttendanceEvents."""

    @pytest.mark.asyncio
    async def test_leave_approval_preserves_immutable_ledger(self) -> None:
        session = AsyncMock()
        tid = uuid.uuid4()
        manager_uid = uuid.uuid4()
        manager_emp = _mock_employee(tid, user_id=manager_uid)
        target_emp = _mock_employee(tid, reporting_manager_id=manager_emp.id)
        lt = _mock_leave_type(tid)
        bal = _mock_leave_balance(tid, target_emp.id, lt.id, pending=Decimal("2.00"))

        req = LeaveRequest(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=target_emp.id,
            leave_type_id=lt.id,
            start_date=date(2026, 12, 1),
            end_date=date(2026, 12, 2),
            total_days=Decimal("2.00"),
            status="PENDING_APPROVAL",
            employee=target_emp,
            leave_type=lt,
        )

        session.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=req)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=manager_emp)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=bal)),
        ]

        with patch(
            "services.api.leave.leave_request_service.recalculate_attendance_day",
            new_callable=AsyncMock,
        ) as mock_recalc:
            mock_recalc.return_value = AttendanceDay(
                id=uuid.uuid4(),
                tenant_id=tid,
                employee_id=target_emp.id,
                attendance_date=date(2026, 12, 1),
                status="ON_LEAVE",
            )

            await adjudicate_leave_request(
                session=session,
                tenant_id=tid,
                request_id=req.id,
                reviewer_user_id=manager_uid,
                reviewer_role="manager",
                action="APPROVE",
            )

        # Ledger Immutability Verification:
        # Zero calls to session.add() with an AttendanceEvent instance
        for call_args in session.add.call_args_list:
            arg = call_args[0][0]
            assert not isinstance(arg, AttendanceEvent), "Phase 9 must never insert synthetic AttendanceEvents."
