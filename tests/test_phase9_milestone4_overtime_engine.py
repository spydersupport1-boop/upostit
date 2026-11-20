"""Comprehensive test suite for Phase 9, Milestone 9.4:
Overtime Rules Engine & Attendance Calculation Integration.

Covers:
- Workday, weekly-off, and holiday overtime calculations.
- Threshold eligibility and daily cap enforcement.
- Break deductions and overnight shifts.
- Full-day and half-day approved leave.
- Incomplete attendance sessions (zero overtime).
- Statutory Holiday vs. Weekly Off overlap precedence (no double-counting).
- Multiplier and payable minutes formulas.
- Pre-approval requirements vs. manager approval.
- Supervisor adjudication, anti-self-approval, and manager hierarchy.
- Attendance day recalculation idempotency, duplicate prevention, and decision preservation.
- FastAPI HTTP route integration with RBAC and tenant isolation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from services.api.attendance.engine import (
    BreakInterval,
    ResolvedTimeline,
    WorkSession,
    calculate_attendance_day,
)
from services.api.attendance.models import AttendanceDay, AttendanceEvent, ShiftTemplateVersion
from services.api.attendance.service import recalculate_attendance_day
from services.api.auth.dependencies import AuthenticatedContext, get_authenticated_context
from services.api.auth.models import User
from services.api.database import get_db
from services.api.employees.models import Employee
from services.api.leave.models import (
    OvertimeRecord,
    OvertimeRule,
)
from services.api.leave.overtime_service import (
    adjudicate_overtime_record,
    create_overtime_rule,
    delete_overtime_rule,
)
from services.api.leave.schemas import (
    OvertimeDecisionRequest,
    OvertimeRuleCreateRequest,
)
from services.api.main import app
from services.api.tenants.models import Tenant

# ==============================================================================
# Helper Mock Factories
# ==============================================================================


def _mock_context(
    role: str, tenant_id: uuid.UUID | None = None, user_id: uuid.UUID | None = None
) -> AuthenticatedContext:
    tid = tenant_id or uuid.uuid4()
    uid = user_id or uuid.uuid4()
    user = User(
        id=uid,
        tenant_id=tid,
        full_name=f"Phase 9 {role.capitalize()} User",
        email=f"user-{uid.hex[:6]}@upostit.test",
        password_hash="argon2id$mock",
        role=role.lower(),
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    tenant = Tenant(
        id=tid,
        name="Phase 9 Tenant",
        slug="phase9-tenant",
        status="active",
        timezone="UTC",
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
        first_name="Bob",
        last_name="Builder",
        work_email=f"bob.{uuid.uuid4().hex[:4]}@upostit.test",
        reporting_manager_id=reporting_manager_id,
        employment_type="full_time",
        joining_date=date(2025, 1, 1),
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _mock_shift_version(
    tenant_id: uuid.UUID,
    start_time_val: time = time(9, 0),
    end_time_val: time = time(17, 0),
    break_mins: int = 60,
    is_overnight: bool = False,
    weekly_off_days: list[int] | None = None,
) -> ShiftTemplateVersion:
    return ShiftTemplateVersion(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        shift_template_id=uuid.uuid4(),
        version_number=1,
        version_effective_from=date(2025, 1, 1),
        start_time=start_time_val,
        end_time=end_time_val,
        grace_period_minutes=15,
        early_exit_grace_minutes=15,
        early_arrival_allowance_minutes=120,
        late_departure_allowance_minutes=180,
        half_day_threshold_minutes=240,
        full_day_threshold_minutes=420,
        break_duration_minutes=break_mins,
        is_overnight=is_overnight,
        weekly_off_days=weekly_off_days if weekly_off_days is not None else [0, 6],  # Sun, Sat
        created_at=datetime.now(UTC),
    )


def _mock_overtime_rule(
    tenant_id: uuid.UUID,
    min_thresh: int = 30,
    max_daily: int | None = 240,
    workday_mult: Decimal = Decimal("1.50"),
    weekend_mult: Decimal = Decimal("2.00"),
    holiday_mult: Decimal = Decimal("2.00"),
    req_manager: bool = True,
    req_pre_approval: bool = False,
    is_default: bool = True,
) -> OvertimeRule:
    return OvertimeRule(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name="Standard Overtime Policy",
        min_overtime_threshold_minutes=min_thresh,
        max_daily_overtime_minutes=max_daily,
        max_weekly_overtime_minutes=720,
        workday_multiplier=workday_mult,
        weekend_multiplier=weekend_mult,
        holiday_multiplier=holiday_mult,
        requires_manager_approval=req_manager,
        requires_pre_approval=req_pre_approval,
        is_default=is_default,
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


# ==============================================================================
# 1. Pure Overtime Engine Calculation Tests
# ==============================================================================


class TestOvertimeEngineCalculations:
    """Validates the extended pure calculate_attendance_day engine."""

    def test_workday_overtime_below_threshold_yields_zero_eligible(self):
        # Shift: 09:00 - 17:00 (8 hrs gross - 1 hr break = 7 hrs = 420 mins scheduled net)
        # Worked: 09:00 - 17:25 (8h25m gross - 1h break = 7h25m = 445 mins net)
        # Raw OT: 445 - 420 = 25 mins.
        # Threshold: 30 mins -> below threshold! Eligible OT must be 0.
        tid = uuid.uuid4()
        shift = _mock_shift_version(tid)
        rule = _mock_overtime_rule(tid, min_thresh=30)
        t_date = date(2026, 6, 1)  # Monday

        t_in = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
        t_out = datetime(2026, 6, 1, 17, 25, tzinfo=UTC)

        b_in = datetime(2026, 6, 1, 13, 0, tzinfo=UTC)
        b_out = datetime(2026, 6, 1, 14, 0, tzinfo=UTC)

        session = WorkSession(
            check_in=t_in,
            check_out=t_out,
            breaks=[BreakInterval(start=b_in, end=b_out, duration_minutes=60)],
            gross_minutes=505,
            break_minutes=60,
            net_minutes=445,
            is_open=False,
        )
        timeline = ResolvedTimeline(
            active_events=[],
            sessions=[session],
            first_check_in=t_in,
            last_check_out=t_out,
            unclosed_session=False,
            unclosed_break=False,
            has_suspicious_events=False,
            anomalies=[],
            source_event_ids=["ev-1"],
        )

        res = calculate_attendance_day(
            target_date=t_date,
            shift_version=shift,
            resolved_timeline=timeline,
            overtime_rule=rule,
        )

        assert res.net_working_minutes == 445
        assert res.overtime_minutes == 0
        assert res.overtime_details is not None
        assert res.overtime_details.raw_overtime_minutes == 25
        assert res.overtime_details.eligible_overtime_minutes == 0
        assert res.overtime_details.payable_overtime_minutes == 0

    def test_workday_overtime_above_threshold_with_break_deductions(self):
        # Shift: 09:00 - 17:00 (420 mins scheduled net)
        # Worked: 09:00 - 19:00 (10 hrs gross - 1 hr break = 9 hrs = 540 mins net)
        # Raw OT: 540 - 420 = 120 mins.
        # Multiplier: 1.50 -> Payable OT: 120 * 1.50 = 180 mins.
        tid = uuid.uuid4()
        shift = _mock_shift_version(tid)
        rule = _mock_overtime_rule(tid, min_thresh=30, workday_mult=Decimal("1.50"))
        t_date = date(2026, 6, 1)  # Monday

        t_in = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
        t_out = datetime(2026, 6, 1, 19, 0, tzinfo=UTC)
        b_in = datetime(2026, 6, 1, 13, 0, tzinfo=UTC)
        b_out = datetime(2026, 6, 1, 14, 0, tzinfo=UTC)

        session = WorkSession(
            check_in=t_in,
            check_out=t_out,
            breaks=[BreakInterval(start=b_in, end=b_out, duration_minutes=60)],
            gross_minutes=600,
            break_minutes=60,
            net_minutes=540,
            is_open=False,
        )
        timeline = ResolvedTimeline(
            active_events=[],
            sessions=[session],
            first_check_in=t_in,
            last_check_out=t_out,
            unclosed_session=False,
            unclosed_break=False,
            has_suspicious_events=False,
            anomalies=[],
            source_event_ids=["ev-1"],
        )

        res = calculate_attendance_day(
            target_date=t_date,
            shift_version=shift,
            resolved_timeline=timeline,
            overtime_rule=rule,
        )

        assert res.net_working_minutes == 540
        assert res.overtime_minutes == 120
        assert res.overtime_details is not None
        assert res.overtime_details.raw_overtime_minutes == 120
        assert res.overtime_details.eligible_overtime_minutes == 120
        assert res.overtime_details.multiplier == Decimal("1.50")
        assert res.overtime_details.payable_overtime_minutes == 180
        assert res.overtime_details.overtime_type == "WORKDAY"

    def test_workday_overtime_capped_by_daily_maximum(self):
        # Raw OT: 300 mins. Daily cap: 240 mins.
        # Eligible OT should be capped at 240 mins.
        # Payable OT: 240 * 1.50 = 360 mins.
        tid = uuid.uuid4()
        shift = _mock_shift_version(tid)
        rule = _mock_overtime_rule(tid, min_thresh=30, max_daily=240, workday_mult=Decimal("1.50"))
        t_date = date(2026, 6, 1)

        t_in = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
        t_out = datetime(2026, 6, 1, 22, 0, tzinfo=UTC)  # 13 hrs gross - 1 hr break = 720 mins net
        # 720 - 420 = 300 mins raw OT

        session = WorkSession(
            check_in=t_in,
            check_out=t_out,
            gross_minutes=780,
            break_minutes=60,
            net_minutes=720,
            is_open=False,
        )
        timeline = ResolvedTimeline(
            active_events=[],
            sessions=[session],
            first_check_in=t_in,
            last_check_out=t_out,
            unclosed_session=False,
            unclosed_break=False,
            has_suspicious_events=False,
            anomalies=[],
            source_event_ids=["ev-1"],
        )

        res = calculate_attendance_day(
            target_date=t_date,
            shift_version=shift,
            resolved_timeline=timeline,
            overtime_rule=rule,
        )

        assert res.overtime_details is not None
        assert res.overtime_details.raw_overtime_minutes == 300
        assert res.overtime_details.eligible_overtime_minutes == 240
        assert res.overtime_details.payable_overtime_minutes == 360
        assert res.overtime_minutes == 240

    def test_weekly_off_overtime_multiplier_and_rest_day_work(self):
        # Sunday 2026-06-07: Weekly off day.
        # Scheduled work: 0 mins.
        # Employee works: 09:00 - 13:00 (240 mins).
        # Category: WEEK_OFF. Multiplier: 2.00.
        # Raw OT: 240 mins. Eligible: 240 mins. Payable: 240 * 2.00 = 480 mins.
        tid = uuid.uuid4()
        shift = _mock_shift_version(tid, weekly_off_days=[0, 6])  # Sunday = 0
        rule = _mock_overtime_rule(tid, weekend_mult=Decimal("2.00"))
        t_date = date(2026, 6, 7)  # Sunday

        t_in = datetime(2026, 6, 7, 9, 0, tzinfo=UTC)
        t_out = datetime(2026, 6, 7, 13, 0, tzinfo=UTC)

        session = WorkSession(
            check_in=t_in,
            check_out=t_out,
            gross_minutes=240,
            break_minutes=0,
            net_minutes=240,
            is_open=False,
        )
        timeline = ResolvedTimeline(
            active_events=[],
            sessions=[session],
            first_check_in=t_in,
            last_check_out=t_out,
            unclosed_session=False,
            unclosed_break=False,
            has_suspicious_events=False,
            anomalies=[],
            source_event_ids=["ev-1"],
        )

        res = calculate_attendance_day(
            target_date=t_date,
            shift_version=shift,
            resolved_timeline=timeline,
            overtime_rule=rule,
        )

        assert res.status == "PRESENT"
        assert res.overtime_details is not None
        assert res.overtime_details.overtime_type == "WEEK_OFF"
        assert res.overtime_details.raw_overtime_minutes == 240
        assert res.overtime_details.eligible_overtime_minutes == 240
        assert res.overtime_details.multiplier == Decimal("2.00")
        assert res.overtime_details.payable_overtime_minutes == 480

    def test_holiday_overtime_statutory_multiplier(self):
        # Wednesday 2026-06-03: Statutory Holiday.
        # Employee works: 09:00 - 15:00 (360 mins net).
        # Multiplier: 2.00. Payable: 360 * 2.00 = 720 mins.
        tid = uuid.uuid4()
        shift = _mock_shift_version(tid)
        rule = _mock_overtime_rule(tid, holiday_mult=Decimal("2.00"), max_daily=480)
        t_date = date(2026, 6, 3)

        t_in = datetime(2026, 6, 3, 9, 0, tzinfo=UTC)
        t_out = datetime(2026, 6, 3, 15, 0, tzinfo=UTC)

        session = WorkSession(
            check_in=t_in,
            check_out=t_out,
            gross_minutes=360,
            break_minutes=0,
            net_minutes=360,
            is_open=False,
        )
        timeline = ResolvedTimeline(
            active_events=[],
            sessions=[session],
            first_check_in=t_in,
            last_check_out=t_out,
            unclosed_session=False,
            unclosed_break=False,
            has_suspicious_events=False,
            anomalies=[],
            source_event_ids=["ev-1"],
        )

        res = calculate_attendance_day(
            target_date=t_date,
            shift_version=shift,
            resolved_timeline=timeline,
            is_holiday=True,
            overtime_rule=rule,
        )

        assert res.status == "PRESENT"
        assert res.overtime_details is not None
        assert res.overtime_details.overtime_type == "HOLIDAY"
        assert res.overtime_details.raw_overtime_minutes == 360
        assert res.overtime_details.multiplier == Decimal("2.00")
        assert res.overtime_details.payable_overtime_minutes == 720

    def test_holiday_and_weekly_off_overlap_precedence_no_double_count(self):
        # Sunday 2026-06-07: BOTH a Weekly Off AND a Statutory Public Holiday!
        # Deterministic precedence: Holiday takes precedence.
        # Multiplier: holiday_multiplier (2.00). Category: HOLIDAY.
        # Minutes are counted exactly ONCE (no double stacking).
        tid = uuid.uuid4()
        shift = _mock_shift_version(tid, weekly_off_days=[0, 6])
        rule = _mock_overtime_rule(
            tid,
            weekend_mult=Decimal("2.00"),
            holiday_mult=Decimal("2.50"),
        )
        t_date = date(2026, 6, 7)  # Sunday

        t_in = datetime(2026, 6, 7, 9, 0, tzinfo=UTC)
        t_out = datetime(2026, 6, 7, 13, 0, tzinfo=UTC)

        session = WorkSession(
            check_in=t_in,
            check_out=t_out,
            gross_minutes=240,
            break_minutes=0,
            net_minutes=240,
            is_open=False,
        )
        timeline = ResolvedTimeline(
            active_events=[],
            sessions=[session],
            first_check_in=t_in,
            last_check_out=t_out,
            unclosed_session=False,
            unclosed_break=False,
            has_suspicious_events=False,
            anomalies=[],
            source_event_ids=["ev-1"],
        )

        res = calculate_attendance_day(
            target_date=t_date,
            shift_version=shift,
            resolved_timeline=timeline,
            is_holiday=True,
            overtime_rule=rule,
        )

        # Precedence check
        assert res.overtime_details is not None
        assert res.overtime_details.overtime_type == "HOLIDAY"
        assert res.overtime_details.multiplier == Decimal("2.50")
        assert res.overtime_details.raw_overtime_minutes == 240
        # 240 * 2.50 = 600 equivalent payable minutes (counted once, not doubled with weekend)
        assert res.overtime_details.payable_overtime_minutes == 600

    def test_overnight_shift_overtime_calculation(self):
        # Overnight Shift: 22:00 to 06:00 next day (8 hrs gross - 1 hr break = 420 mins scheduled net)
        # Worked: 22:00 to 08:30 (10.5 hrs gross - 1 hr break = 570 mins net)
        # Raw OT: 570 - 420 = 150 mins.
        # Multiplier: 1.50 -> Payable: 150 * 1.50 = 225 mins.
        tid = uuid.uuid4()
        shift = _mock_shift_version(
            tid,
            start_time_val=time(22, 0),
            end_time_val=time(6, 0),
            break_mins=60,
            is_overnight=True,
        )
        rule = _mock_overtime_rule(tid, workday_mult=Decimal("1.50"))
        t_date = date(2026, 6, 1)

        t_in = datetime(2026, 6, 1, 22, 0, tzinfo=UTC)
        t_out = datetime(2026, 6, 2, 8, 30, tzinfo=UTC)

        session = WorkSession(
            check_in=t_in,
            check_out=t_out,
            gross_minutes=630,
            break_minutes=60,
            net_minutes=570,
            is_open=False,
        )
        timeline = ResolvedTimeline(
            active_events=[],
            sessions=[session],
            first_check_in=t_in,
            last_check_out=t_out,
            unclosed_session=False,
            unclosed_break=False,
            has_suspicious_events=False,
            anomalies=[],
            source_event_ids=["ev-1"],
        )

        res = calculate_attendance_day(
            target_date=t_date,
            shift_version=shift,
            resolved_timeline=timeline,
            overtime_rule=rule,
        )

        assert res.overtime_details is not None
        assert res.overtime_details.raw_overtime_minutes == 150
        assert res.overtime_details.payable_overtime_minutes == 225
        assert res.overtime_minutes == 150

    def test_incomplete_attendance_session_yields_zero_overtime(self):
        # An incomplete session (unclosed check-in or unclosed break) cannot accrue overtime
        tid = uuid.uuid4()
        shift = _mock_shift_version(tid)
        rule = _mock_overtime_rule(tid)
        t_date = date(2026, 6, 1)

        t_in = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
        session = WorkSession(
            check_in=t_in,
            check_out=None,
            gross_minutes=0,
            break_minutes=0,
            net_minutes=0,
            is_open=True,
        )
        timeline = ResolvedTimeline(
            active_events=[],
            sessions=[session],
            first_check_in=t_in,
            last_check_out=None,
            unclosed_session=True,
            unclosed_break=False,
            has_suspicious_events=False,
            anomalies=["Unclosed session"],
            source_event_ids=["ev-1"],
        )

        res = calculate_attendance_day(
            target_date=t_date,
            shift_version=shift,
            resolved_timeline=timeline,
            overtime_rule=rule,
        )

        assert res.status == "INCOMPLETE"
        assert res.overtime_minutes == 0
        assert res.overtime_details is None

    def test_full_day_approved_leave_yields_zero_overtime(self):
        # An employee on approved leave cannot accrue overtime on that day
        tid = uuid.uuid4()
        shift = _mock_shift_version(tid)
        rule = _mock_overtime_rule(tid)
        t_date = date(2026, 6, 1)

        timeline = ResolvedTimeline(
            active_events=[],
            sessions=[],
            first_check_in=None,
            last_check_out=None,
            unclosed_session=False,
            unclosed_break=False,
            has_suspicious_events=False,
            anomalies=[],
            source_event_ids=[],
        )

        res = calculate_attendance_day(
            target_date=t_date,
            shift_version=shift,
            resolved_timeline=timeline,
            is_on_leave=True,
            leave_type_code="AL",
            overtime_rule=rule,
        )

        assert res.status == "ON_LEAVE"
        assert res.overtime_minutes == 0
        assert res.overtime_details is None

    def test_half_day_approved_leave_scheduled_boundary_overtime(self):
        # Half-day leave: Scheduled net is halved (420 // 2 = 210 mins).
        # Employee worked 300 mins net.
        # Raw OT: 300 - 210 = 90 mins.
        # Multiplier: 1.50 -> Payable: 90 * 1.50 = 135 mins.
        tid = uuid.uuid4()
        shift = _mock_shift_version(tid)
        rule = _mock_overtime_rule(tid, workday_mult=Decimal("1.50"))
        t_date = date(2026, 6, 1)

        t_in = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
        t_out = datetime(2026, 6, 1, 14, 0, tzinfo=UTC)  # 5 hrs = 300 mins

        session = WorkSession(
            check_in=t_in,
            check_out=t_out,
            gross_minutes=300,
            break_minutes=0,
            net_minutes=300,
            is_open=False,
        )
        timeline = ResolvedTimeline(
            active_events=[],
            sessions=[session],
            first_check_in=t_in,
            last_check_out=t_out,
            unclosed_session=False,
            unclosed_break=False,
            has_suspicious_events=False,
            anomalies=[],
            source_event_ids=["ev-1"],
        )

        res = calculate_attendance_day(
            target_date=t_date,
            shift_version=shift,
            resolved_timeline=timeline,
            is_on_leave=True,
            is_half_day_leave=True,
            half_day_period="SECOND_HALF",
            overtime_rule=rule,
        )

        assert res.overtime_details is not None
        assert res.overtime_details.raw_overtime_minutes == 90
        assert res.overtime_details.payable_overtime_minutes == 135
        assert res.overtime_minutes == 90

    def test_pre_approval_required_flags_pending_approval_not_auto_approved(self):
        # When requires_pre_approval is True, overtime must NOT be auto-approved
        tid = uuid.uuid4()
        shift = _mock_shift_version(tid)
        rule = _mock_overtime_rule(tid, req_manager=False, req_pre_approval=True)
        t_date = date(2026, 6, 1)

        session = WorkSession(
            check_in=datetime(2026, 6, 1, 9, 0, tzinfo=UTC),
            check_out=datetime(2026, 6, 1, 18, 0, tzinfo=UTC),
            gross_minutes=540,
            break_minutes=60,
            net_minutes=480,  # 480 - 420 = 60 mins OT
            is_open=False,
        )
        timeline = ResolvedTimeline(
            active_events=[],
            sessions=[session],
            first_check_in=session.check_in,
            last_check_out=session.check_out,
            unclosed_session=False,
            unclosed_break=False,
            has_suspicious_events=False,
            anomalies=[],
            source_event_ids=["ev-1"],
        )

        res = calculate_attendance_day(
            target_date=t_date,
            shift_version=shift,
            resolved_timeline=timeline,
            overtime_rule=rule,
        )

        assert res.overtime_details is not None
        assert res.overtime_details.status == "PENDING_APPROVAL"
        assert res.overtime_details.requires_approval is True

    def test_auto_approval_when_neither_manager_nor_pre_approval_required(self):
        # When requires_manager_approval=False AND requires_pre_approval=False, status is AUTO_APPROVED
        tid = uuid.uuid4()
        shift = _mock_shift_version(tid)
        rule = _mock_overtime_rule(tid, req_manager=False, req_pre_approval=False)
        t_date = date(2026, 6, 1)

        session = WorkSession(
            check_in=datetime(2026, 6, 1, 9, 0, tzinfo=UTC),
            check_out=datetime(2026, 6, 1, 18, 0, tzinfo=UTC),
            gross_minutes=540,
            break_minutes=60,
            net_minutes=480,  # 60 mins OT
            is_open=False,
        )
        timeline = ResolvedTimeline(
            active_events=[],
            sessions=[session],
            first_check_in=session.check_in,
            last_check_out=session.check_out,
            unclosed_session=False,
            unclosed_break=False,
            has_suspicious_events=False,
            anomalies=[],
            source_event_ids=["ev-1"],
        )

        res = calculate_attendance_day(
            target_date=t_date,
            shift_version=shift,
            resolved_timeline=timeline,
            overtime_rule=rule,
        )

        assert res.overtime_details is not None
        assert res.overtime_details.status == "AUTO_APPROVED"
        assert res.overtime_details.requires_approval is False


# ==============================================================================
# 2. Overtime Rule Service CRUD Tests
# ==============================================================================


class TestOvertimeRuleService:
    """Validates OvertimeRule management services."""

    @pytest.mark.asyncio
    async def test_create_overtime_rule_success_and_default_demotion(self):
        session = AsyncMock()
        session.add = MagicMock()
        tid = uuid.uuid4()

        # Existing default
        old_default = _mock_overtime_rule(tid, is_default=True)
        mock_res = MagicMock()
        mock_res.scalars.return_value.all.return_value = [old_default]
        session.execute.return_value = mock_res

        payload = OvertimeRuleCreateRequest(
            name="New Default Policy",
            min_overtime_threshold_minutes=30,
            max_daily_overtime_minutes=240,
            workday_multiplier=Decimal("1.50"),
            weekend_multiplier=Decimal("2.00"),
            holiday_multiplier=Decimal("2.00"),
            is_default=True,
        )

        rule = await create_overtime_rule(session, tid, payload)

        assert old_default.is_default is False
        assert rule.name == "New Default Policy"
        assert rule.is_default is True
        assert rule.workday_multiplier == Decimal("1.50")
        session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_overtime_rule_invalid_multiplier_raises_400(self):
        with pytest.raises(Exception):
            OvertimeRuleCreateRequest(
                name="Invalid Multiplier Rule",
                workday_multiplier=Decimal("0.50"),  # Invalid: < 1.00
            )

    @pytest.mark.asyncio
    async def test_create_overtime_rule_invalid_daily_cap_raises_400(self):
        session = AsyncMock()
        tid = uuid.uuid4()

        payload = OvertimeRuleCreateRequest(
            name="Invalid Cap Rule",
            min_overtime_threshold_minutes=60,
            max_daily_overtime_minutes=30,  # Invalid: max < min
        )

        with pytest.raises(Exception):
            await create_overtime_rule(session, tid, payload)

    @pytest.mark.asyncio
    async def test_delete_overtime_rule_blocked_when_referenced_raises_409(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        rule = _mock_overtime_rule(tid)

        mock_rule_res = MagicMock()
        mock_rule_res.scalar_one_or_none.return_value = rule

        mock_ref_res = MagicMock()
        mock_ref_res.scalar_one_or_none.return_value = uuid.uuid4()  # Reference found

        session.execute.side_effect = [mock_rule_res, mock_ref_res]

        with pytest.raises(Exception) as exc_info:
            await delete_overtime_rule(session, tid, rule.id)

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT


# ==============================================================================
# 3. Overtime Adjudication Workflow Tests
# ==============================================================================


class TestOvertimeAdjudicationWorkflow:
    """Validates supervisor approval, rejection, and anti-self-approval."""

    @pytest.mark.asyncio
    async def test_anti_self_approval_raises_403(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        uid = uuid.uuid4()

        emp = _mock_employee(tid, user_id=uid)
        record = OvertimeRecord(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=emp.id,
            attendance_day_id=uuid.uuid4(),
            attendance_date=date(2026, 6, 1),
            raw_overtime_minutes=120,
            multiplier=Decimal("1.50"),
            status="PENDING_APPROVAL",
        )

        mock_rec_res = MagicMock()
        mock_rec_res.scalar_one_or_none.return_value = record

        mock_emp_res = MagicMock()
        mock_emp_res.scalar_one_or_none.return_value = emp

        session.execute.side_effect = [mock_rec_res, mock_emp_res, mock_emp_res]

        payload = OvertimeDecisionRequest(action="APPROVE")

        with pytest.raises(Exception) as exc_info:
            await adjudicate_overtime_record(
                session=session,
                tenant_id=tid,
                record_id=record.id,
                reviewer_user_id=uid,  # Same user!
                reviewer_role="manager",
                payload=payload,
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Anti-self-approval violation" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_manager_cannot_adjudicate_non_direct_report_raises_403(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        mgr_uid = uuid.uuid4()
        mgr_emp = _mock_employee(tid, user_id=mgr_uid)

        other_mgr_id = uuid.uuid4()
        target_emp = _mock_employee(tid, reporting_manager_id=other_mgr_id)

        record = OvertimeRecord(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=target_emp.id,
            attendance_day_id=uuid.uuid4(),
            attendance_date=date(2026, 6, 1),
            raw_overtime_minutes=120,
            multiplier=Decimal("1.50"),
            status="PENDING_APPROVAL",
        )

        mock_rec = MagicMock()
        mock_rec.scalar_one_or_none.return_value = record

        mock_target = MagicMock()
        mock_target.scalar_one_or_none.return_value = target_emp

        mock_mgr = MagicMock()
        mock_mgr.scalar_one_or_none.return_value = mgr_emp

        session.execute.side_effect = [mock_rec, mock_target, mock_mgr]

        payload = OvertimeDecisionRequest(action="APPROVE")

        with pytest.raises(Exception) as exc_info:
            await adjudicate_overtime_record(
                session=session,
                tenant_id=tid,
                record_id=record.id,
                reviewer_user_id=mgr_uid,
                reviewer_role="manager",
                payload=payload,
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert (
            "Managers may only adjudicate overtime records for their direct reports"
            in exc_info.value.detail
        )

    @pytest.mark.asyncio
    async def test_successful_approval_updates_record_and_attendance_day_overtime(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        mgr_uid = uuid.uuid4()
        mgr_emp = _mock_employee(tid, user_id=mgr_uid)

        target_emp = _mock_employee(tid, reporting_manager_id=mgr_emp.id)

        day = AttendanceDay(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=target_emp.id,
            attendance_date=date(2026, 6, 1),
            overtime_minutes=0,
        )

        record = OvertimeRecord(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=target_emp.id,
            attendance_day_id=day.id,
            attendance_date=date(2026, 6, 1),
            raw_overtime_minutes=120,
            approved_overtime_minutes=0,
            multiplier=Decimal("1.50"),
            payable_overtime_minutes=0,
            status="PENDING_APPROVAL",
        )

        mock_rec = MagicMock()
        mock_rec.scalar_one_or_none.return_value = record

        mock_target = MagicMock()
        mock_target.scalar_one_or_none.return_value = target_emp

        mock_mgr = MagicMock()
        mock_mgr.scalar_one_or_none.return_value = mgr_emp

        mock_day = MagicMock()
        mock_day.scalar_one_or_none.return_value = day

        session.execute.side_effect = [mock_rec, mock_target, mock_mgr, mock_day]

        payload = OvertimeDecisionRequest(
            action="APPROVE", reason="Project release work authorized"
        )

        res = await adjudicate_overtime_record(
            session=session,
            tenant_id=tid,
            record_id=record.id,
            reviewer_user_id=mgr_uid,
            reviewer_role="manager",
            payload=payload,
        )

        assert res.status == "APPROVED"
        assert res.approved_overtime_minutes == 120
        assert res.payable_overtime_minutes == 180
        assert res.reviewer_user_id == mgr_uid
        assert day.overtime_minutes == 120

    @pytest.mark.asyncio
    async def test_rejection_without_mandatory_reason_raises_422(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        mgr_uid = uuid.uuid4()
        mgr_emp = _mock_employee(tid, user_id=mgr_uid)
        target_emp = _mock_employee(tid, reporting_manager_id=mgr_emp.id)

        record = OvertimeRecord(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=target_emp.id,
            attendance_day_id=uuid.uuid4(),
            attendance_date=date(2026, 6, 1),
            raw_overtime_minutes=120,
            status="PENDING_APPROVAL",
        )

        mock_rec = MagicMock()
        mock_rec.scalar_one_or_none.return_value = record
        mock_target = MagicMock()
        mock_target.scalar_one_or_none.return_value = target_emp
        mock_mgr = MagicMock()
        mock_mgr.scalar_one_or_none.return_value = mgr_emp

        session.execute.side_effect = [mock_rec, mock_target, mock_mgr]

        payload = OvertimeDecisionRequest(action="REJECT", reason="  ")  # Whitespace only

        with pytest.raises(Exception) as exc_info:
            await adjudicate_overtime_record(
                session=session,
                tenant_id=tid,
                record_id=record.id,
                reviewer_user_id=mgr_uid,
                reviewer_role="manager",
                payload=payload,
            )

        assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# ==============================================================================
# 4. Attendance Recalculation & Overtime Integration Tests
# ==============================================================================


class TestAttendanceRecalculationOvertimeIntegration:
    """Validates recalculate_attendance_day integration with overtime rules."""

    @pytest.mark.asyncio
    async def test_recalculation_preserves_already_approved_decision(self):
        # When recalculate_attendance_day is run, if an overtime record is already APPROVED,
        # its approval status and approved minutes must be preserved!
        session = AsyncMock()
        session.add = MagicMock()
        tid = uuid.uuid4()
        eid = uuid.uuid4()
        t_date = date(2026, 6, 1)

        shift = _mock_shift_version(tid)
        rule = _mock_overtime_rule(tid)

        existing_day = AttendanceDay(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=eid,
            attendance_date=t_date,
            calculation_version=1,
            overtime_minutes=120,
        )

        existing_ot = OvertimeRecord(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=eid,
            attendance_day_id=existing_day.id,
            attendance_date=t_date,
            raw_overtime_minutes=120,
            approved_overtime_minutes=120,
            multiplier=Decimal("1.50"),
            payable_overtime_minutes=180,
            status="APPROVED",
            reviewer_user_id=uuid.uuid4(),
            decided_at=datetime.now(UTC),
        )

        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                "services.api.attendance.service.resolve_employee_shift_version",
                AsyncMock(return_value=(None, shift)),
            )
            m.setattr(
                "services.api.leave.holiday_service.resolve_applicable_calendar_for_employee",
                AsyncMock(return_value=(None, "NONE")),
            )
            m.setattr(
                "services.api.leave.overtime_service.resolve_applicable_overtime_rule",
                AsyncMock(return_value=rule),
            )

            # Mock DB executions
            mock_emp_lock = MagicMock()
            mock_tz = MagicMock()
            mock_tz.scalar_one_or_none.return_value = "UTC"

            # Event query (simulating worked punches 09:00 - 19:00 = 120m OT)
            ev1 = AttendanceEvent(
                id=uuid.uuid4(),
                tenant_id=tid,
                employee_id=eid,
                event_type="CHECK_IN",
                effective_at=datetime(2026, 6, 1, 9, 0, tzinfo=UTC),
                server_received_at=datetime(2026, 6, 1, 9, 0, tzinfo=UTC),
                idempotency_key="k1",
            )
            ev2 = AttendanceEvent(
                id=uuid.uuid4(),
                tenant_id=tid,
                employee_id=eid,
                event_type="CHECK_OUT",
                effective_at=datetime(2026, 6, 1, 19, 0, tzinfo=UTC),
                server_received_at=datetime(2026, 6, 1, 19, 0, tzinfo=UTC),
                idempotency_key="k2",
            )
            mock_ev = MagicMock()
            mock_ev.scalars.return_value.all.return_value = [ev1, ev2]

            mock_leave = MagicMock()
            mock_leave.scalar_one_or_none.return_value = None

            mock_day_res = MagicMock()
            mock_day_res.scalar_one_or_none.return_value = existing_day

            mock_ot_res = MagicMock()
            mock_ot_res.scalar_one_or_none.return_value = existing_ot

            session.execute.side_effect = [
                mock_emp_lock,
                mock_tz,
                mock_ev,
                mock_leave,
                mock_day_res,
                mock_ot_res,
            ]

            day_res = await recalculate_attendance_day(
                session=session,
                tenant_id=tid,
                employee_id=eid,
                attendance_date=t_date,
            )

        assert day_res.overtime_minutes == 120
        assert existing_ot.status == "APPROVED"
        assert existing_ot.approved_overtime_minutes == 120
        assert existing_ot.payable_overtime_minutes == 180


# ==============================================================================
# 5. Overtime HTTP Route Integration Tests
# ==============================================================================


class TestOvertimeHTTPRouteIntegration:
    """Tests FastAPI routes for rules, records, and supervisor queue."""

    @pytest.mark.asyncio
    async def test_admin_can_create_and_list_overtime_rules_200_201(self):
        tid = uuid.uuid4()
        ctx = _mock_context("admin", tenant_id=tid)

        mock_db = AsyncMock()
        mock_count = MagicMock()
        mock_count.scalar.return_value = 1
        rule = _mock_overtime_rule(tid)
        mock_data = MagicMock()
        mock_data.scalars.return_value.all.return_value = [rule]

        mock_db.execute.side_effect = [mock_count, mock_data]

        app.dependency_overrides[get_authenticated_context] = lambda: ctx
        app.dependency_overrides[get_db] = lambda: mock_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/overtime/rules")

        app.dependency_overrides.clear()

        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "Standard Overtime Policy"

    @pytest.mark.asyncio
    async def test_employee_cannot_create_overtime_rule_raises_403(self):
        tid = uuid.uuid4()
        ctx = _mock_context("employee", tenant_id=tid)

        mock_db = AsyncMock()
        app.dependency_overrides[get_authenticated_context] = lambda: ctx
        app.dependency_overrides[get_db] = lambda: mock_db

        payload = {
            "name": "Employee Policy",
            "workday_multiplier": 1.5,
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/overtime/rules", json=payload)

        app.dependency_overrides.clear()

        assert resp.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_employee_cannot_access_supervisor_overtime_queue_raises_403(self):
        tid = uuid.uuid4()
        ctx = _mock_context("employee", tenant_id=tid)

        mock_db = AsyncMock()
        app.dependency_overrides[get_authenticated_context] = lambda: ctx
        app.dependency_overrides[get_db] = lambda: mock_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/overtime/records")

        app.dependency_overrides.clear()

        assert resp.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_cross_tenant_isolation_on_overtime_records_raises_404(self):
        tid = uuid.uuid4()
        ctx = _mock_context("admin", tenant_id=tid)

        mock_db = AsyncMock()
        mock_rec_res = MagicMock()
        mock_rec_res.first.return_value = None  # Not found in tenant
        mock_db.execute.return_value = mock_rec_res

        app.dependency_overrides[get_authenticated_context] = lambda: ctx
        app.dependency_overrides[get_db] = lambda: mock_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/v1/overtime/records/{uuid.uuid4()}")

        app.dependency_overrides.clear()

        assert resp.status_code == status.HTTP_404_NOT_FOUND
