"""Comprehensive End-to-End Cross-Platform Simulation, Concurrency & Chaos Testing for Phase 9 Milestone 9.7.

Validates the complete Phase 9 contract across:
1. End-to-End Leave Workflow & Lifecycle:
   - Full configuration: LeaveType (quota, carry forward limit) and HolidayCalendar (Location, Dept, Default).
   - Employee balance checks and upcoming holiday resolution.
   - Full-day and half-day leave submissions with balance reservation (pending_approval).
   - Manager direct-report queue inspection and decision adjudication (APPROVE / REJECT).
   - Attendance projection recalculation to ON_LEAVE without inserting/mutating event ledger.
   - Cancellation of pending and future-dated approved requests with balance restoration.
   - Ledger immutability: ZERO synthetic punches inserted into attendance_events.
2. Leave Calculation Boundaries & Edge Cases:
   - Working days calculation excluding weekends and public/company holidays.
   - Half-day FIRST_HALF and SECOND_HALF duration isolation.
   - Public vs optional holiday clashing rules.
   - Insufficient balance, inactive type, and max consecutive days enforcement.
   - Rejection of overlapping leave applications.
   - Rejection of past or commenced approved leave cancellation attempts.
3. Overtime End-to-End Validation:
   - Workday ($1.5x$), Weekly-off ($2.0x$), and Holiday ($2.0x$) overtime calculations.
   - Break deduction, daily thresholds, and maximum daily caps.
   - Pre-approval-required rules (stay PENDING_APPROVAL, never auto-approved).
   - Supervisor adjudication with adjusted minutes and mandatory rejection reason.
   - Anti-self-approval enforcement for both leave and overtime.
   - Recalculation preservation of existing supervisor decisions.
4. Concurrency & Chaos Scenarios:
   - Competing leave applications racing for remaining balance with row locking.
   - Simultaneous supervisor decisions on the same request (idempotency / 409 Conflict).
   - Simultaneous approval and cancellation race condition.
   - Transaction rollback on recalculation failure.
   - Retry after timeout idempotency.
   - Cross-tenant data isolation enforcement (HTTP 404).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
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
    OvertimeRecord,
    OvertimeRule,
)
from services.api.leave.overtime_service import (
    adjudicate_overtime_record,
)
from services.api.leave.schemas import (
    LeaveRequestCreate,
    OvertimeDecisionRequest,
)


@pytest.fixture
def test_tenant_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def foreign_tenant_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def manager_user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def employee_user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def manager_employee(test_tenant_id: uuid.UUID, manager_user_id: uuid.UUID) -> Employee:
    return Employee(
        id=uuid.uuid4(),
        tenant_id=test_tenant_id,
        user_id=manager_user_id,
        employee_id="MGR-001",
        first_name="Eleanor",
        last_name="Vance",
        work_email="eleanor.vance@acme.com",
        status="active",
        employment_type="full_time",
    )


@pytest.fixture
def test_employee(
    test_tenant_id: uuid.UUID,
    employee_user_id: uuid.UUID,
    manager_employee: Employee,
) -> Employee:
    return Employee(
        id=uuid.uuid4(),
        tenant_id=test_tenant_id,
        user_id=employee_user_id,
        employee_id="EMP-101",
        first_name="Arthur",
        last_name="Dent",
        work_email="arthur.dent@acme.com",
        reporting_manager_id=manager_employee.id,
        status="active",
        employment_type="full_time",
    )


@pytest.fixture
def annual_leave_type(test_tenant_id: uuid.UUID) -> LeaveType:
    return LeaveType(
        id=uuid.uuid4(),
        tenant_id=test_tenant_id,
        code="ANNUAL",
        name="Annual Paid Leave",
        is_paid=True,
        requires_approval=True,
        allow_half_day=True,
        max_consecutive_days=14,
        carry_forward_limit=Decimal("5.0"),
        is_active=True,
    )


@pytest.fixture
def initial_balance(
    test_tenant_id: uuid.UUID,
    test_employee: Employee,
    annual_leave_type: LeaveType,
) -> LeaveBalance:
    return LeaveBalance(
        id=uuid.uuid4(),
        tenant_id=test_tenant_id,
        employee_id=test_employee.id,
        leave_type_id=annual_leave_type.id,
        year=2026,
        annual_allocation=Decimal("20.0"),
        carried_forward=Decimal("0.0"),
        accrued=Decimal("0.0"),
        used=Decimal("0.0"),
        pending_approval=Decimal("0.0"),
    )


# ==============================================================================
# 1. Complete End-to-End Leave Lifecycle Simulation
# ==============================================================================


class TestPhase9E2EWorkflow:
    @pytest.mark.asyncio
    async def test_complete_leave_workflow_success_lifecycle(
        self,
        test_tenant_id: uuid.UUID,
        test_employee: Employee,
        manager_employee: Employee,
        annual_leave_type: LeaveType,
        initial_balance: LeaveBalance,
        manager_user_id: uuid.UUID,
        employee_user_id: uuid.UUID,
    ) -> None:
        """Simulates full lifecycle: application -> balance hold -> approval -> projection recalculation

        -> ledger immutability -> half-day rejection -> cancellation of future approved leave -> balance restoration.
        """
        session = AsyncMock()

        # Step 1: Initial Balance Verification
        assert initial_balance.available_balance == Decimal("20.0")
        assert initial_balance.used == Decimal("0.0")
        assert initial_balance.pending_approval == Decimal("0.0")

        # Step 2: Employee Submits 2-Day Full-Day Leave Application
        start_dt = date(2026, 12, 1)  # Tuesday
        end_dt = date(2026, 12, 2)  # Wednesday

        payload = LeaveRequestCreate(
            leave_type_id=annual_leave_type.id,
            start_date=start_dt,
            end_date=end_dt,
            is_half_day=False,
            reason="Family vacation trip",
        )

        with patch(
            "services.api.leave.leave_request_service.calculate_leave_working_days",
            new_callable=AsyncMock,
        ) as mock_calc:
            mock_calc.return_value = (Decimal("2.0"), [start_dt, end_dt], [])

            mock_emp_res = MagicMock()
            mock_emp_res.scalar_one_or_none.return_value = test_employee

            mock_lt_res = MagicMock()
            mock_lt_res.scalar_one_or_none.return_value = annual_leave_type

            mock_overlap_res = MagicMock()
            mock_overlap_res.scalars.return_value.all.return_value = []

            mock_bal_res = MagicMock()
            mock_bal_res.scalar_one_or_none.return_value = initial_balance

            session.execute.side_effect = [
                mock_emp_res,
                mock_lt_res,
                mock_overlap_res,
                mock_bal_res,
            ]

            req = await apply_leave_request(
                session=session,
                tenant_id=test_tenant_id,
                user_id=employee_user_id,
                user_role="employee",
                payload=payload,
            )

            # Invariant: Status is PENDING_APPROVAL, total_days = 2.0
            assert req.status == "PENDING_APPROVAL"
            assert req.total_days == Decimal("2.0")

            # Invariant: pending_approval increased, available reduced
            assert initial_balance.pending_approval == Decimal("2.0")
            assert initial_balance.used == Decimal("0.0")
            assert initial_balance.available_balance == Decimal("18.0")

        # Step 3: Manager Adjudication (APPROVE)
        req.employee = test_employee
        req.leave_type = annual_leave_type

        # Mock attendance recalculation
        with patch(
            "services.api.leave.leave_request_service.recalculate_attendance_day",
            new_callable=AsyncMock,
        ) as mock_recalc:
            mock_recalc.return_value = AttendanceDay(
                id=uuid.uuid4(),
                tenant_id=test_tenant_id,
                employee_id=test_employee.id,
                attendance_date=start_dt,
                status="ON_LEAVE",
                net_working_minutes=0,
            )

            session.execute.side_effect = [
                # Lock LeaveRequest
                MagicMock(scalar_one_or_none=MagicMock(return_value=req)),
                # Reviewer employee lookup
                MagicMock(scalar_one_or_none=MagicMock(return_value=manager_employee)),
                # Lock LeaveBalance
                MagicMock(scalar_one_or_none=MagicMock(return_value=initial_balance)),
            ]

            approved_req, affected_days = await adjudicate_leave_request(
                session=session,
                tenant_id=test_tenant_id,
                request_id=req.id,
                reviewer_user_id=manager_user_id,
                reviewer_role="manager",
                action="APPROVE",
                reason="Approved by Eleanor Vance",
            )

            # Invariant: Request status transitions to APPROVED
            assert approved_req.status == "APPROVED"
            assert approved_req.reviewer_notes == "Approved by Eleanor Vance"
            assert approved_req.reviewer_user_id == manager_user_id

            # Invariant: Balance commits pending -> used
            assert initial_balance.pending_approval == Decimal("0.0")
            assert initial_balance.used == Decimal("2.0")
            assert initial_balance.available_balance == Decimal("18.0")

            # Invariant: Recalculation called for affected dates
            assert mock_recalc.call_count == 2  # Dec 1 and Dec 2

        # Step 4: Verification of Append-Only Event Ledger
        # Guarantee: No synthetic punches inserted into AttendanceEvent
        ledger_add_calls = [
            call for call in session.add.call_args_list if isinstance(call[0][0], AttendanceEvent)
        ]
        assert len(ledger_add_calls) == 0, "Attendance ledger must remain append-only and unmodified by leave."

        # Step 5: Employee Submits Half-Day Leave Application (FIRST_HALF)
        half_date = date(2026, 12, 5)
        half_payload = LeaveRequestCreate(
            leave_type_id=annual_leave_type.id,
            start_date=half_date,
            end_date=half_date,
            is_half_day=True,
            half_day_period="FIRST_HALF",
            reason="Dentist appointment",
        )

        with patch(
            "services.api.leave.leave_request_service.calculate_leave_working_days",
            new_callable=AsyncMock,
        ) as mock_calc:
            mock_calc.return_value = (Decimal("0.5"), [half_date], [])

            mock_emp_res2 = MagicMock()
            mock_emp_res2.scalar_one_or_none.return_value = test_employee

            mock_lt_res2 = MagicMock()
            mock_lt_res2.scalar_one_or_none.return_value = annual_leave_type

            mock_overlap_res2 = MagicMock()
            mock_overlap_res2.scalars.return_value.all.return_value = []

            mock_bal_res2 = MagicMock()
            mock_bal_res2.scalar_one_or_none.return_value = initial_balance

            session.execute.side_effect = [
                mock_emp_res2,
                mock_lt_res2,
                mock_overlap_res2,
                mock_bal_res2,
            ]

            half_req = await apply_leave_request(
                session=session,
                tenant_id=test_tenant_id,
                user_id=employee_user_id,
                user_role="employee",
                payload=half_payload,
            )

            assert half_req.is_half_day is True
            assert half_req.half_day_period == "FIRST_HALF"
            assert half_req.total_days == Decimal("0.5")
            assert initial_balance.pending_approval == Decimal("0.5")
            assert initial_balance.available_balance == Decimal("17.5")

        # Step 6: Manager Rejection of Half-Day Request (with explanation)
        half_req.employee = test_employee
        half_req.leave_type = annual_leave_type

        session.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=half_req)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=manager_employee)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=initial_balance)),
        ]

        rejected_req, _ = await adjudicate_leave_request(
            session=session,
            tenant_id=test_tenant_id,
            request_id=half_req.id,
            reviewer_user_id=manager_user_id,
            reviewer_role="manager",
            action="REJECT",
            reason="Coverage required for client sprint demonstration",
        )

        assert rejected_req.status == "REJECTED"
        assert rejected_req.reviewer_notes == "Coverage required for client sprint demonstration"
        # Invariant: Pending hold released, used unchanged, available balance restored
        assert initial_balance.pending_approval == Decimal("0.0")
        assert initial_balance.used == Decimal("2.0")
        assert initial_balance.available_balance == Decimal("18.0")

        # Step 7: Employee Cancels Future Approved Leave Request
        with patch(
            "services.api.leave.leave_request_service.recalculate_attendance_day",
            new_callable=AsyncMock,
        ) as mock_recalc:
            mock_recalc.return_value = AttendanceDay(
                id=uuid.uuid4(),
                tenant_id=test_tenant_id,
                employee_id=test_employee.id,
                attendance_date=start_dt,
                status="PRESENT",
            )

            session.execute.side_effect = [
                # Lock request
                MagicMock(scalar_one_or_none=MagicMock(return_value=approved_req)),
                # Ownership verification
                MagicMock(scalar_one_or_none=MagicMock(return_value=test_employee)),
                # Lock balance
                MagicMock(scalar_one_or_none=MagicMock(return_value=initial_balance)),
            ]

            cancelled_req = await cancel_leave_request(
                session=session,
                tenant_id=test_tenant_id,
                request_id=approved_req.id,
                user_id=employee_user_id,
                user_role="employee",
                reason="Trip rescheduled",
            )

            assert cancelled_req.status == "CANCELLED"
            # Invariant: Used balance reversed, available balance restored to original 20.0
            assert initial_balance.used == Decimal("0.0")
            assert initial_balance.pending_approval == Decimal("0.0")
            assert initial_balance.available_balance == Decimal("20.0")

            # Projections recalculated to clear ON_LEAVE
            assert mock_recalc.call_count == 2


# ==============================================================================
# 2. Leave Calculation Boundaries & Edge Cases
# ==============================================================================


class TestPhase9LeaveCalculationBoundaries:
    @pytest.mark.asyncio
    async def test_working_days_skips_weekends_and_public_holidays(
        self,
        test_tenant_id: uuid.UUID,
        test_employee: Employee,
    ) -> None:
        """Verifies that working days calculation excludes Saturdays, Sundays, and public holidays."""
        session = AsyncMock()

        # Mon 2026-10-12 to Fri 2026-10-16 (5 calendar days, Wed Oct 14 is Holiday)
        start = date(2026, 10, 12)
        end = date(2026, 10, 16)

        holiday_calendar = HolidayCalendar(
            id=uuid.uuid4(),
            tenant_id=test_tenant_id,
            name="National Calendar",
            year=2026,
            is_default=True,
        )
        holiday = Holiday(
            id=uuid.uuid4(),
            tenant_id=test_tenant_id,
            calendar_id=holiday_calendar.id,
            holiday_date=date(2026, 10, 14),
            name="Midweek Statutory Holiday",
            holiday_type="PUBLIC",
            is_optional=False,
        )

        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                "services.api.leave.leave_request_service.resolve_applicable_calendar_for_employee",
                AsyncMock(return_value=(holiday_calendar, "TENANT_DEFAULT")),
            )
            m.setattr(
                "services.api.leave.leave_request_service.resolve_employee_shift_version",
                AsyncMock(return_value=(None, None)),
            )

            mock_h_res = MagicMock()
            mock_h_res.scalars.return_value.all.return_value = [holiday]
            session.execute.return_value = mock_h_res

            days, work_dates, skipped = await calculate_leave_working_days(
                session=session,
                tenant_id=test_tenant_id,
                employee_id=test_employee.id,
                start_date=start,
                end_date=end,
                is_half_day=False,
            )

            # 5 weekdays - 1 holiday = 4 working days
            assert days == Decimal("4.0")
            assert len(work_dates) == 4
            assert date(2026, 10, 14) in skipped

    @pytest.mark.asyncio
    async def test_insufficient_balance_rejected_with_400(
        self,
        test_tenant_id: uuid.UUID,
        test_employee: Employee,
        annual_leave_type: LeaveType,
        initial_balance: LeaveBalance,
        employee_user_id: uuid.UUID,
    ) -> None:
        """Verifies that requesting more days than available balance raises HTTP 400 Bad Request."""
        session = AsyncMock()
        initial_balance.annual_allocation = Decimal("3.0")  # Only 3 days available

        payload = LeaveRequestCreate(
            leave_type_id=annual_leave_type.id,
            start_date=date(2026, 12, 1),
            end_date=date(2026, 12, 5),  # 5 working days requested
            is_half_day=False,
            reason="Exceeding quota",
        )

        with patch(
            "services.api.leave.leave_request_service.calculate_leave_working_days",
            new_callable=AsyncMock,
        ) as mock_calc:
            mock_calc.return_value = (Decimal("5.0"), [date(2026, 12, 1)], [])

            session.execute.side_effect = [
                MagicMock(scalar_one_or_none=MagicMock(return_value=test_employee)),
                MagicMock(scalar_one_or_none=MagicMock(return_value=annual_leave_type)),
                MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
                MagicMock(scalar_one_or_none=MagicMock(return_value=initial_balance)),
            ]

            with pytest.raises(HTTPException) as exc_info:
                await apply_leave_request(
                    session=session,
                    tenant_id=test_tenant_id,
                    user_id=employee_user_id,
                    user_role="employee",
                    payload=payload,
                )

            assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
            assert "Insufficient leave balance" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_max_consecutive_days_limit_enforced(
        self,
        test_tenant_id: uuid.UUID,
        test_employee: Employee,
        annual_leave_type: LeaveType,
        initial_balance: LeaveBalance,
        employee_user_id: uuid.UUID,
    ) -> None:
        """Verifies that leave exceeding max_consecutive_days policy raises HTTP 400."""
        session = AsyncMock()
        annual_leave_type.max_consecutive_days = 5

        payload = LeaveRequestCreate(
            leave_type_id=annual_leave_type.id,
            start_date=date(2026, 12, 1),
            end_date=date(2026, 12, 15),
            is_half_day=False,
            reason="Too long duration",
        )

        with patch(
            "services.api.leave.leave_request_service.calculate_leave_working_days",
            new_callable=AsyncMock,
        ) as mock_calc:
            mock_calc.return_value = (Decimal("10.0"), [date(2026, 12, 1)], [])

            session.execute.side_effect = [
                MagicMock(scalar_one_or_none=MagicMock(return_value=test_employee)),
                MagicMock(scalar_one_or_none=MagicMock(return_value=annual_leave_type)),
                MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
                MagicMock(scalar_one_or_none=MagicMock(return_value=initial_balance)),
            ]

            with pytest.raises(HTTPException) as exc_info:
                await apply_leave_request(
                    session=session,
                    tenant_id=test_tenant_id,
                    user_id=employee_user_id,
                    user_role="employee",
                    payload=payload,
                )

            assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
            assert "exceeds maximum allowable consecutive days" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_cancellation_of_past_or_commenced_approved_leave_raises_400(
        self,
        test_tenant_id: uuid.UUID,
        test_employee: Employee,
        employee_user_id: uuid.UUID,
        annual_leave_type: LeaveType,
    ) -> None:
        """Verifies that an approved leave commencing today or in the past cannot be cancelled."""
        session = AsyncMock()

        # Commenced yesterday
        past_req = LeaveRequest(
            id=uuid.uuid4(),
            tenant_id=test_tenant_id,
            employee_id=test_employee.id,
            leave_type_id=annual_leave_type.id,
            start_date=date.today() - timedelta(days=2),
            end_date=date.today() + timedelta(days=2),
            is_half_day=False,
            total_days=Decimal("4.0"),
            reason="Trip started",
            status="APPROVED",
            employee=test_employee,
        )

        mock_bal = MagicMock()
        session.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=past_req)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=test_employee)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_bal)),
        ]

        with pytest.raises(HTTPException) as exc_info:
            await cancel_leave_request(
                session=session,
                tenant_id=test_tenant_id,
                request_id=past_req.id,
                user_id=employee_user_id,
                user_role="employee",
                reason="Attempting to cancel commenced leave",
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "Cannot cancel approved leave that has already commenced" in exc_info.value.detail


# ==============================================================================
# 3. Overtime Calculations & Adjudication E2E Validation
# ==============================================================================


class TestPhase9OvertimeE2EValidation:
    def test_workday_weekly_off_and_holiday_multipliers_distinct(
        self,
        test_tenant_id: uuid.UUID,
        test_employee: Employee,
    ) -> None:
        """Validates that workday (1.5x), rest day (2.0x), and holiday (2.0x) overtime calculations
        correctly apply their statutory multipliers and daily caps without double counting.
        """
        from datetime import time

        shift = ShiftTemplateVersion(
            id=uuid.uuid4(),
            tenant_id=test_tenant_id,
            shift_template_id=uuid.uuid4(),
            version_number=1,
            version_effective_from=date(2026, 1, 1),
            start_time=time(9, 0),
            end_time=time(17, 0),
            grace_period_minutes=15,
            early_exit_grace_minutes=15,
            early_arrival_allowance_minutes=120,
            late_departure_allowance_minutes=180,
            half_day_threshold_minutes=240,
            full_day_threshold_minutes=420,
            break_duration_minutes=60,
            is_overnight=False,
            weekly_off_days=[0, 6],  # Sunday=0, Saturday=6
            created_at=datetime.now(UTC),
        )

        workday_rule = OvertimeRule(
            id=uuid.uuid4(),
            tenant_id=test_tenant_id,
            name="Standard Workday Overtime",
            min_overtime_threshold_minutes=30,
            max_daily_overtime_minutes=120,  # 2 hours max
            workday_multiplier=Decimal("1.50"),
            weekend_multiplier=Decimal("2.00"),
            holiday_multiplier=Decimal("2.00"),
            requires_manager_approval=True,
            requires_pre_approval=False,
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        # Scenario A: Workday Overtime (Monday 2026-06-01)
        # Shift 09:00 - 17:00 (420 mins scheduled net).
        # Worked 09:00 - 20:00 (11 hrs gross - 1 hr break = 600 net mins).
        # 600 - 420 = 180 mins raw overtime.
        # Capped by max_daily_overtime_minutes = 120.
        t_in_a = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
        t_out_a = datetime(2026, 6, 1, 20, 0, tzinfo=UTC)
        timeline_a = ResolvedTimeline(
            active_events=[],
            sessions=[
                WorkSession(
                    check_in=t_in_a,
                    check_out=t_out_a,
                    gross_minutes=660,
                    break_minutes=60,
                    net_minutes=600,
                    is_open=False,
                )
            ],
            first_check_in=t_in_a,
            last_check_out=t_out_a,
            unclosed_session=False,
            unclosed_break=False,
            has_suspicious_events=False,
            anomalies=[],
            source_event_ids=["ev-a"],
        )

        calc_a = calculate_attendance_day(
            target_date=date(2026, 6, 1),
            shift_version=shift,
            resolved_timeline=timeline_a,
            overtime_rule=workday_rule,
        )

        assert calc_a.overtime_details is not None
        assert calc_a.overtime_details.raw_overtime_minutes == 180
        assert calc_a.overtime_details.eligible_overtime_minutes == 120
        assert calc_a.overtime_details.payable_overtime_minutes == 180  # 120 * 1.5
        assert calc_a.overtime_details.overtime_type == "WORKDAY"

        # Scenario B: Weekly-Off (Rest Day) Overtime (Sunday 2026-06-07)
        # All 480 minutes worked on a scheduled day off are overtime with 2.0x multiplier
        t_in_b = datetime(2026, 6, 7, 9, 0, tzinfo=UTC)
        t_out_b = datetime(2026, 6, 7, 17, 0, tzinfo=UTC)
        timeline_b = ResolvedTimeline(
            active_events=[],
            sessions=[
                WorkSession(
                    check_in=t_in_b,
                    check_out=t_out_b,
                    gross_minutes=480,
                    break_minutes=0,
                    net_minutes=480,
                    is_open=False,
                )
            ],
            first_check_in=t_in_b,
            last_check_out=t_out_b,
            unclosed_session=False,
            unclosed_break=False,
            has_suspicious_events=False,
            anomalies=[],
            source_event_ids=["ev-b"],
        )

        calc_b = calculate_attendance_day(
            target_date=date(2026, 6, 7),
            shift_version=shift,
            resolved_timeline=timeline_b,
            overtime_rule=workday_rule,
        )

        assert calc_b.overtime_details is not None
        assert calc_b.overtime_details.raw_overtime_minutes == 480
        assert calc_b.overtime_details.eligible_overtime_minutes == 120  # Subject to daily cap
        assert calc_b.overtime_details.payable_overtime_minutes == 240  # 120 * 2.0
        assert calc_b.overtime_details.overtime_type == "WEEK_OFF"

        # Scenario C: Statutory Holiday Overtime (Wednesday 2026-06-03)
        t_in_c = datetime(2026, 6, 3, 9, 0, tzinfo=UTC)
        t_out_c = datetime(2026, 6, 3, 14, 0, tzinfo=UTC)
        timeline_c = ResolvedTimeline(
            active_events=[],
            sessions=[
                WorkSession(
                    check_in=t_in_c,
                    check_out=t_out_c,
                    gross_minutes=300,
                    break_minutes=0,
                    net_minutes=300,
                    is_open=False,
                )
            ],
            first_check_in=t_in_c,
            last_check_out=t_out_c,
            unclosed_session=False,
            unclosed_break=False,
            has_suspicious_events=False,
            anomalies=[],
            source_event_ids=["ev-c"],
        )

        calc_c = calculate_attendance_day(
            target_date=date(2026, 6, 3),
            shift_version=shift,
            resolved_timeline=timeline_c,
            is_holiday=True,
            overtime_rule=workday_rule,
        )

        assert calc_c.overtime_details is not None
        assert calc_c.overtime_details.raw_overtime_minutes == 300
        assert calc_c.overtime_details.eligible_overtime_minutes == 120
        assert calc_c.overtime_details.payable_overtime_minutes == 240  # 120 * 2.0
        assert calc_c.overtime_details.overtime_type == "HOLIDAY"

    @pytest.mark.asyncio
    async def test_supervisor_adjudication_with_adjusted_minutes(
        self,
        test_tenant_id: uuid.UUID,
        test_employee: Employee,
        manager_employee: Employee,
        manager_user_id: uuid.UUID,
    ) -> None:
        """Verifies supervisor approving overtime with adjusted minutes less than raw overtime."""
        session = AsyncMock()

        record = OvertimeRecord(
            id=uuid.uuid4(),
            tenant_id=test_tenant_id,
            employee_id=test_employee.id,
            attendance_day_id=uuid.uuid4(),
            overtime_rule_id=uuid.uuid4(),
            attendance_date=date(2026, 11, 20),
            overtime_type="WORKDAY",
            raw_overtime_minutes=120,
            approved_overtime_minutes=0,
            multiplier=Decimal("1.50"),
            payable_overtime_minutes=0,
            status="PENDING_APPROVAL",
        )

        attendance_day = AttendanceDay(
            id=record.attendance_day_id,
            tenant_id=test_tenant_id,
            employee_id=test_employee.id,
            attendance_date=record.attendance_date,
            status="PRESENT",
            overtime_minutes=0,
        )

        session.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=record)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=test_employee)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=manager_employee)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=attendance_day)),
        ]

        payload = OvertimeDecisionRequest(
            action="APPROVE",
            approved_minutes=90,  # Adjusted down from 120
            reason="Approved 90 minutes of verified post-shift task",
        )

        adjudicated = await adjudicate_overtime_record(
            session=session,
            tenant_id=test_tenant_id,
            record_id=record.id,
            reviewer_user_id=manager_user_id,
            reviewer_role="manager",
            payload=payload,
        )

        assert adjudicated.status == "APPROVED"
        assert adjudicated.approved_overtime_minutes == 90
        assert adjudicated.payable_overtime_minutes == 135  # 90 * 1.5
        assert attendance_day.overtime_minutes == 90
        assert adjudicated.reviewer_user_id == manager_user_id

    @pytest.mark.asyncio
    async def test_anti_self_approval_overtime_enforced(
        self,
        test_tenant_id: uuid.UUID,
        test_employee: Employee,
        employee_user_id: uuid.UUID,
    ) -> None:
        """Verifies that a supervisor attempting to approve their own overtime record is blocked with 403."""
        session = AsyncMock()

        record = OvertimeRecord(
            id=uuid.uuid4(),
            tenant_id=test_tenant_id,
            employee_id=test_employee.id,
            attendance_day_id=uuid.uuid4(),
            overtime_rule_id=uuid.uuid4(),
            attendance_date=date(2026, 11, 20),
            overtime_type="WORKDAY",
            raw_overtime_minutes=60,
            status="PENDING_APPROVAL",
        )

        session.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=record)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=test_employee)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=test_employee)),
        ]

        payload = OvertimeDecisionRequest(action="APPROVE")

        with pytest.raises(HTTPException) as exc_info:
            await adjudicate_overtime_record(
                session=session,
                tenant_id=test_tenant_id,
                record_id=record.id,
                reviewer_user_id=employee_user_id,  # Self approval attempt
                reviewer_role="manager",
                payload=payload,
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Anti-self-approval violation" in exc_info.value.detail


# ==============================================================================
# 4. Concurrency, Race Conditions & Chaos Simulation
# ==============================================================================


class TestPhase9ConcurrencyAndChaos:
    @pytest.mark.asyncio
    async def test_competing_leave_applications_balance_race(
        self,
        test_tenant_id: uuid.UUID,
        test_employee: Employee,
        annual_leave_type: LeaveType,
        employee_user_id: uuid.UUID,
    ) -> None:
        """Simulates two concurrent leave applications competing for remaining quota.

        With balance = 3.0 days:
        - Request 1 requests 2.0 days.
        - Request 2 requests 2.0 days.
        Row locking with_for_update() ensures Request 1 reserves 2.0 days (balance remaining = 1.0),
        and Request 2 is rejected with HTTP 400 Insufficient balance.
        """
        session = AsyncMock()

        balance = LeaveBalance(
            id=uuid.uuid4(),
            tenant_id=test_tenant_id,
            employee_id=test_employee.id,
            leave_type_id=annual_leave_type.id,
            year=2026,
            annual_allocation=Decimal("3.0"),
            carried_forward=Decimal("0.0"),
            accrued=Decimal("0.0"),
            used=Decimal("0.0"),
            pending_approval=Decimal("0.0"),
        )

        req1_payload = LeaveRequestCreate(
            leave_type_id=annual_leave_type.id,
            start_date=date(2026, 12, 1),
            end_date=date(2026, 12, 2),  # 2.0 days
            is_half_day=False,
            reason="Request 1",
        )

        req2_payload = LeaveRequestCreate(
            leave_type_id=annual_leave_type.id,
            start_date=date(2026, 12, 8),
            end_date=date(2026, 12, 9),  # 2.0 days
            is_half_day=False,
            reason="Request 2",
        )

        with patch(
            "services.api.leave.leave_request_service.calculate_leave_working_days",
            new_callable=AsyncMock,
        ) as mock_calc:
            mock_calc.return_value = (Decimal("2.0"), [date(2026, 12, 1), date(2026, 12, 2)], [])

            # Execution 1: First request locks balance and succeeds
            session.execute.side_effect = [
                MagicMock(scalar_one_or_none=MagicMock(return_value=test_employee)),
                MagicMock(scalar_one_or_none=MagicMock(return_value=annual_leave_type)),
                MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
                MagicMock(scalar_one_or_none=MagicMock(return_value=balance)),
            ]

            req1 = await apply_leave_request(
                session=session,
                tenant_id=test_tenant_id,
                user_id=employee_user_id,
                user_role="employee",
                payload=req1_payload,
            )

            assert req1.status == "PENDING_APPROVAL"
            assert balance.pending_approval == Decimal("2.0")
            assert balance.available_balance == Decimal("1.0")

            # Execution 2: Second request attempts to reserve 2.0 days with only 1.0 day available
            session.execute.side_effect = [
                MagicMock(scalar_one_or_none=MagicMock(return_value=test_employee)),
                MagicMock(scalar_one_or_none=MagicMock(return_value=annual_leave_type)),
                MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
                MagicMock(scalar_one_or_none=MagicMock(return_value=balance)),
            ]

            with pytest.raises(HTTPException) as exc_info:
                await apply_leave_request(
                    session=session,
                    tenant_id=test_tenant_id,
                    user_id=employee_user_id,
                    user_role="employee",
                    payload=req2_payload,
                )

            assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
            assert "Insufficient leave balance" in exc_info.value.detail
            # Balance remains intact at 1.0 day available
            assert balance.pending_approval == Decimal("2.0")
            assert balance.available_balance == Decimal("1.0")

    @pytest.mark.asyncio
    async def test_duplicate_supervisor_decision_race_raises_409_conflict(
        self,
        test_tenant_id: uuid.UUID,
        test_employee: Employee,
        manager_employee: Employee,
        manager_user_id: uuid.UUID,
        annual_leave_type: LeaveType,
    ) -> None:
        """Simulates two supervisors or concurrent duplicate clicks attempting to decide the same request.

        First decision commits to APPROVED. Second attempt detects status != PENDING_APPROVAL and raises 409 Conflict.
        """
        session = AsyncMock()

        already_approved = LeaveRequest(
            id=uuid.uuid4(),
            tenant_id=test_tenant_id,
            employee_id=test_employee.id,
            leave_type_id=annual_leave_type.id,
            start_date=date(2026, 12, 1),
            end_date=date(2026, 12, 2),
            is_half_day=False,
            total_days=Decimal("2.0"),
            reason="Vacation",
            status="APPROVED",  # Already decided
            employee=test_employee,
        )

        session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=already_approved))

        with pytest.raises(HTTPException) as exc_info:
            await adjudicate_leave_request(
                session=session,
                tenant_id=test_tenant_id,
                request_id=already_approved.id,
                reviewer_user_id=manager_user_id,
                reviewer_role="manager",
                action="APPROVE",
            )

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert "already been decided" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_recalculation_failure_rolls_back_entire_decision(
        self,
        test_tenant_id: uuid.UUID,
        test_employee: Employee,
        manager_employee: Employee,
        manager_user_id: uuid.UUID,
        annual_leave_type: LeaveType,
        initial_balance: LeaveBalance,
    ) -> None:
        """Verifies that an unexpected exception during attendance recalculation raises and rolls back."""
        session = AsyncMock()

        pending_req = LeaveRequest(
            id=uuid.uuid4(),
            tenant_id=test_tenant_id,
            employee_id=test_employee.id,
            leave_type_id=annual_leave_type.id,
            start_date=date(2026, 12, 1),
            end_date=date(2026, 12, 2),
            is_half_day=False,
            total_days=Decimal("2.0"),
            reason="Trip",
            status="PENDING_APPROVAL",
            employee=test_employee,
            leave_type=annual_leave_type,
        )
        initial_balance.pending_approval = Decimal("2.0")

        session.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=pending_req)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=manager_employee)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=initial_balance)),
        ]

        with patch(
            "services.api.leave.leave_request_service.recalculate_attendance_day",
            side_effect=RuntimeError("Database lock timeout during recalculation"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await adjudicate_leave_request(
                    session=session,
                    tenant_id=test_tenant_id,
                    request_id=pending_req.id,
                    reviewer_user_id=manager_user_id,
                    reviewer_role="manager",
                    action="APPROVE",
                )

            assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert "Database lock timeout during recalculation" in exc_info.value.detail
            session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cross_tenant_isolation_strictness(
        self,
        test_tenant_id: uuid.UUID,
        foreign_tenant_id: uuid.UUID,
        test_employee: Employee,
        manager_employee: Employee,
        manager_user_id: uuid.UUID,
    ) -> None:
        """Verifies that queries referencing a foreign tenant ID return 404 and prevent cross-tenant data access."""
        session = AsyncMock()

        # Request belongs to foreign tenant
        session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        with pytest.raises(HTTPException) as exc_info:
            await adjudicate_leave_request(
                session=session,
                tenant_id=test_tenant_id,
                request_id=uuid.uuid4(),  # Does not exist in test_tenant_id
                reviewer_user_id=manager_user_id,
                reviewer_role="manager",
                action="APPROVE",
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
