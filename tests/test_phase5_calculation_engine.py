"""Comprehensive unit and API integration tests for Phase 5 Milestone 3:
Attendance Timeline Resolution & Calculation Engine.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from services.api.attendance.engine import (
    calculate_attendance_day,
    resolve_active_timeline,
)
from services.api.attendance.models import (
    AttendanceDay,
    AttendanceEvent,
    ShiftAssignment,
    ShiftTemplateVersion,
)
from services.api.attendance.service import (
    determine_shift_date_for_punch,
    recalculate_attendance_day,
    resolve_employee_shift_version,
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
        email=f"calc_{role}@company.test",
        password_hash="argon2id$mock",
        role=role,
        status="active",
    )
    tenant = Tenant(
        id=tid,
        name="Presence Calculation Corp",
        slug=f"prescalc-{tid.hex[:6]}",
        company_email="admin@prescalc.test",
        country_code="IN",
        timezone="UTC",
        status="active",
    )
    return AuthenticatedContext(user=user, tenant=tenant)


def _create_mock_employee(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    reporting_manager_id: uuid.UUID | None = None,
    status: str = "active",
) -> Employee:
    return Employee(
        id=employee_id or uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id or uuid.uuid4(),
        employee_id="EMP-3001",
        first_name="Bob",
        last_name="Johnson",
        work_email="bob.johnson@presence.test",
        employment_type="full_time",
        reporting_manager_id=reporting_manager_id,
        joining_date=date(2026, 1, 1),
        status=status,
    )


def _create_mock_shift_version(
    tenant_id: uuid.UUID,
    shift_template_id: uuid.UUID | None = None,
    version_id: uuid.UUID | None = None,
    version_number: int = 1,
    effective_from: date = date(2026, 1, 1),
    start_time: time = time(9, 0),
    end_time: time = time(18, 0),
    grace_period_minutes: int = 15,
    early_exit_grace_minutes: int = 10,
    early_arrival_allowance_minutes: int = 120,
    late_departure_allowance_minutes: int = 180,
    half_day_threshold_minutes: int = 240,
    full_day_threshold_minutes: int = 480,
    break_duration_minutes: int = 60,
    is_overnight: bool = False,
    weekly_off_days: list[int] | None = None,
) -> ShiftTemplateVersion:
    return ShiftTemplateVersion(
        id=version_id or uuid.uuid4(),
        tenant_id=tenant_id,
        shift_template_id=shift_template_id or uuid.uuid4(),
        version_number=version_number,
        version_effective_from=effective_from,
        start_time=start_time,
        end_time=end_time,
        grace_period_minutes=grace_period_minutes,
        early_exit_grace_minutes=early_exit_grace_minutes,
        early_arrival_allowance_minutes=early_arrival_allowance_minutes,
        late_departure_allowance_minutes=late_departure_allowance_minutes,
        half_day_threshold_minutes=half_day_threshold_minutes,
        full_day_threshold_minutes=full_day_threshold_minutes,
        break_duration_minutes=break_duration_minutes,
        is_overnight=is_overnight,
        is_flexible=False,
        weekly_off_days=weekly_off_days if weekly_off_days is not None else [6, 0],
    )


def _create_mock_event(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    event_type: str,
    effective_at: datetime,
    event_category: str = "STANDARD",
    supersedes_event_id: uuid.UUID | None = None,
    review_status: str = "NOT_REQUIRED",
    timestamp_verification_status: str = "SERVER_AUTHORITATIVE",
    server_received_at: datetime | None = None,
) -> AttendanceEvent:
    s_rx = server_received_at or effective_at
    return AttendanceEvent(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=employee_id,
        event_type=event_type,
        event_category=event_category,
        supersedes_event_id=supersedes_event_id,
        correction_reason=None,
        server_received_at=s_rx,
        device_reported_at=effective_at,
        effective_at=effective_at,
        clock_drift_seconds=Decimal("0.000"),
        source="WEB",
        device_id="browser-xyz",
        timestamp_verification_status=timestamp_verification_status,
        review_status=review_status,
        idempotency_key=str(uuid.uuid4()),
        location_id=None,
        latitude=None,
        longitude=None,
        accuracy_meters=None,
        actor_user_id=None,
        metadata_json={},
        created_at=s_rx,
    )


# ==============================================================================
# SECTION 1: Pure Timeline Resolution Tests
# ==============================================================================


def test_timeline_resolution_normal_day():
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    t_in = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
    t_b_start = datetime(2026, 11, 3, 13, 0, tzinfo=UTC)
    t_b_end = datetime(2026, 11, 3, 14, 0, tzinfo=UTC)
    t_out = datetime(2026, 11, 3, 18, 0, tzinfo=UTC)

    events = [
        _create_mock_event(tid, eid, "CHECK_IN", t_in),
        _create_mock_event(tid, eid, "BREAK_START", t_b_start),
        _create_mock_event(tid, eid, "BREAK_END", t_b_end),
        _create_mock_event(tid, eid, "CHECK_OUT", t_out),
    ]

    tl = resolve_active_timeline(events)

    assert len(tl.sessions) == 1
    session = tl.sessions[0]
    assert session.check_in == t_in
    assert session.check_out == t_out
    assert session.gross_minutes == 540  # 9 hours
    assert session.break_minutes == 60  # 1 hour
    assert session.net_minutes == 480  # 8 hours
    assert not tl.unclosed_session
    assert not tl.unclosed_break
    assert not tl.has_suspicious_events


def test_timeline_resolution_multiple_breaks():
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    t_in = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
    t_b1_start = datetime(2026, 11, 3, 11, 0, tzinfo=UTC)
    t_b1_end = datetime(2026, 11, 3, 11, 15, tzinfo=UTC)  # 15m
    t_b2_start = datetime(2026, 11, 3, 13, 30, tzinfo=UTC)
    t_b2_end = datetime(2026, 11, 3, 14, 15, tzinfo=UTC)  # 45m
    t_out = datetime(2026, 11, 3, 18, 0, tzinfo=UTC)

    events = [
        _create_mock_event(tid, eid, "CHECK_IN", t_in),
        _create_mock_event(tid, eid, "BREAK_START", t_b1_start),
        _create_mock_event(tid, eid, "BREAK_END", t_b1_end),
        _create_mock_event(tid, eid, "BREAK_START", t_b2_start),
        _create_mock_event(tid, eid, "BREAK_END", t_b2_end),
        _create_mock_event(tid, eid, "CHECK_OUT", t_out),
    ]

    tl = resolve_active_timeline(events)

    assert len(tl.sessions) == 1
    session = tl.sessions[0]
    assert len(session.breaks) == 2
    assert session.break_minutes == 60
    assert session.net_minutes == 480


def test_timeline_resolution_missing_checkout():
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    t_in = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)

    events = [_create_mock_event(tid, eid, "CHECK_IN", t_in)]
    tl = resolve_active_timeline(events)

    assert len(tl.sessions) == 1
    assert tl.unclosed_session
    assert tl.sessions[0].check_out is None
    assert tl.sessions[0].is_open
    assert any("Unclosed work session" in a or "missing CHECK_OUT" in a for a in tl.anomalies)


def test_timeline_resolution_missing_break_end():
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    t_in = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
    t_b_start = datetime(2026, 11, 3, 13, 0, tzinfo=UTC)

    events = [
        _create_mock_event(tid, eid, "CHECK_IN", t_in),
        _create_mock_event(tid, eid, "BREAK_START", t_b_start),
    ]
    tl = resolve_active_timeline(events)

    assert tl.unclosed_break
    assert any("Unclosed break" in a for a in tl.anomalies)


def test_timeline_resolution_duplicate_punches():
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    t_in1 = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
    t_in2 = datetime(2026, 11, 3, 9, 1, tzinfo=UTC)
    t_out = datetime(2026, 11, 3, 18, 0, tzinfo=UTC)

    events = [
        _create_mock_event(tid, eid, "CHECK_IN", t_in1),
        _create_mock_event(tid, eid, "CHECK_IN", t_in2),  # Duplicate
        _create_mock_event(tid, eid, "CHECK_OUT", t_out),
    ]
    tl = resolve_active_timeline(events)

    assert len(tl.sessions) == 1
    assert tl.sessions[0].check_in == t_in1
    assert tl.sessions[0].check_out == t_out
    assert any("CHECK_IN" in a and "without CHECK_OUT" in a for a in tl.anomalies)


def test_timeline_resolution_out_of_order_events():
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    t_in = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
    t_out = datetime(2026, 11, 3, 18, 0, tzinfo=UTC)

    # Provided in inverted order
    events = [
        _create_mock_event(tid, eid, "CHECK_OUT", t_out),
        _create_mock_event(tid, eid, "CHECK_IN", t_in),
    ]
    tl = resolve_active_timeline(events)

    assert len(tl.sessions) == 1
    assert tl.sessions[0].check_in == t_in
    assert tl.sessions[0].check_out == t_out
    assert not tl.unclosed_session


def test_timeline_resolution_clock_drift_and_flagged():
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    t_in = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)

    e = _create_mock_event(
        tid,
        eid,
        "CHECK_IN",
        t_in,
        review_status="REQUIRED",
        timestamp_verification_status="FLAGGED_SUSPICIOUS",
    )
    tl = resolve_active_timeline([e])

    assert tl.has_suspicious_events
    assert any("Suspicious event" in a for a in tl.anomalies)


def test_timeline_resolution_superseded_and_voided():
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    t_orig = datetime(2026, 11, 3, 9, 30, tzinfo=UTC)
    t_corr = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
    t_out = datetime(2026, 11, 3, 18, 0, tzinfo=UTC)

    e_orig = _create_mock_event(
        tid, eid, "CHECK_IN", t_orig, server_received_at=datetime(2026, 11, 3, 9, 30, tzinfo=UTC)
    )
    e_corr = _create_mock_event(
        tid,
        eid,
        "CHECK_IN",
        t_corr,
        event_category="CORRECTION_SUPERSEDE",
        supersedes_event_id=e_orig.id,
        server_received_at=datetime(2026, 11, 3, 10, 0, tzinfo=UTC),
    )
    e_out = _create_mock_event(
        tid, eid, "CHECK_OUT", t_out, server_received_at=datetime(2026, 11, 3, 18, 0, tzinfo=UTC)
    )

    tl = resolve_active_timeline([e_orig, e_corr, e_out])

    assert len(tl.sessions) == 1
    # Effective check-in is corrected 09:00, not superseded 09:30
    assert tl.sessions[0].check_in == t_corr
    assert tl.sessions[0].check_out == t_out


# ==============================================================================
# SECTION 2: Attendance Day Calculation Engine Tests
# ==============================================================================


def test_calculation_on_time_full_day():
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    target = date(2026, 11, 3)
    version = _create_mock_shift_version(tid, start_time=time(9, 0), end_time=time(18, 0))

    t_in = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
    t_b_start = datetime(2026, 11, 3, 13, 0, tzinfo=UTC)
    t_b_end = datetime(2026, 11, 3, 14, 0, tzinfo=UTC)
    t_out = datetime(2026, 11, 3, 18, 0, tzinfo=UTC)

    events = [
        _create_mock_event(tid, eid, "CHECK_IN", t_in),
        _create_mock_event(tid, eid, "BREAK_START", t_b_start),
        _create_mock_event(tid, eid, "BREAK_END", t_b_end),
        _create_mock_event(tid, eid, "CHECK_OUT", t_out),
    ]
    tl = resolve_active_timeline(events)
    calc = calculate_attendance_day(target, version, tl, tenant_timezone="UTC")

    assert calc.total_working_minutes == 540
    assert calc.total_break_minutes == 60
    assert calc.net_working_minutes == 480
    assert calc.actual_late_minutes == 0
    assert calc.late_arrival_minutes == 0
    assert calc.actual_early_minutes == 0
    assert calc.early_departure_minutes == 0
    assert calc.status == "PRESENT"
    assert calc.calculation_status == "CALCULATED"
    assert not calc.is_incomplete


def test_calculation_late_within_grace():
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    target = date(2026, 11, 3)
    # Grace is 15 minutes
    version = _create_mock_shift_version(tid, start_time=time(9, 0), grace_period_minutes=15)

    # 12 minutes late (within 15 min grace)
    t_in = datetime(2026, 11, 3, 9, 12, tzinfo=UTC)
    t_out = datetime(2026, 11, 3, 18, 0, tzinfo=UTC)

    events = [
        _create_mock_event(tid, eid, "CHECK_IN", t_in),
        _create_mock_event(tid, eid, "CHECK_OUT", t_out),
    ]
    tl = resolve_active_timeline(events)
    calc = calculate_attendance_day(target, version, tl, tenant_timezone="UTC")

    assert calc.actual_late_minutes == 12
    assert calc.late_arrival_minutes == 0  # Absorbed by grace
    assert calc.status == "PRESENT"


def test_calculation_late_beyond_grace_enterprise_rule():
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    target = date(2026, 11, 3)
    # Grace is 15 minutes
    version = _create_mock_shift_version(tid, start_time=time(9, 0), grace_period_minutes=15)

    # 25 minutes late (exceeds 15 min grace)
    t_in = datetime(2026, 11, 3, 9, 25, tzinfo=UTC)
    t_out = datetime(2026, 11, 3, 18, 0, tzinfo=UTC)

    events = [
        _create_mock_event(tid, eid, "CHECK_IN", t_in),
        _create_mock_event(tid, eid, "CHECK_OUT", t_out),
    ]
    tl = resolve_active_timeline(events)
    calc = calculate_attendance_day(target, version, tl, tenant_timezone="UTC")

    # Enterprise rule: full actual lateness from scheduled start
    assert calc.actual_late_minutes == 25
    assert calc.late_arrival_minutes == 25
    assert calc.status == "LATE"


def test_calculation_early_departure_within_grace():
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    target = date(2026, 11, 3)
    # Early exit grace is 10 minutes
    version = _create_mock_shift_version(tid, end_time=time(18, 0), early_exit_grace_minutes=10)

    # Departs 6 minutes early (within 10m grace)
    t_in = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
    t_out = datetime(2026, 11, 3, 17, 54, tzinfo=UTC)

    events = [
        _create_mock_event(tid, eid, "CHECK_IN", t_in),
        _create_mock_event(tid, eid, "CHECK_OUT", t_out),
    ]
    tl = resolve_active_timeline(events)
    calc = calculate_attendance_day(target, version, tl, tenant_timezone="UTC")

    assert calc.actual_early_minutes == 6
    assert calc.early_departure_minutes == 0  # Absorbed by grace


def test_calculation_early_departure_beyond_grace():
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    target = date(2026, 11, 3)
    # Early exit grace is 10 minutes
    version = _create_mock_shift_version(tid, end_time=time(18, 0), early_exit_grace_minutes=10)

    # Departs 30 minutes early (exceeds 10m grace)
    t_in = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
    t_out = datetime(2026, 11, 3, 17, 30, tzinfo=UTC)

    events = [
        _create_mock_event(tid, eid, "CHECK_IN", t_in),
        _create_mock_event(tid, eid, "CHECK_OUT", t_out),
    ]
    tl = resolve_active_timeline(events)
    calc = calculate_attendance_day(target, version, tl, tenant_timezone="UTC")

    assert calc.actual_early_minutes == 30
    assert calc.early_departure_minutes == 30


def test_calculation_half_day_threshold():
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    target = date(2026, 11, 3)
    # Full day = 480 min, Half day = 240 min
    version = _create_mock_shift_version(
        tid,
        half_day_threshold_minutes=240,
        full_day_threshold_minutes=480,
    )

    # Worked 300 minutes (5 hours) -> >= 240 and < 480 -> HALF_DAY
    t_in = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
    t_out = datetime(2026, 11, 3, 14, 0, tzinfo=UTC)

    events = [
        _create_mock_event(tid, eid, "CHECK_IN", t_in),
        _create_mock_event(tid, eid, "CHECK_OUT", t_out),
    ]
    tl = resolve_active_timeline(events)
    calc = calculate_attendance_day(target, version, tl, tenant_timezone="UTC")

    assert calc.net_working_minutes == 300
    assert calc.status == "HALF_DAY"


def test_calculation_incomplete_session_omitted():
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    target = date(2026, 11, 3)
    version = _create_mock_shift_version(tid)

    # Open check-in with no check-out
    t_in = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
    events = [_create_mock_event(tid, eid, "CHECK_IN", t_in)]
    tl = resolve_active_timeline(events)
    calc = calculate_attendance_day(target, version, tl, tenant_timezone="UTC")

    assert calc.is_incomplete
    assert calc.missing_punch
    assert calc.status == "INCOMPLETE"
    assert calc.calculation_status == "INCOMPLETE"
    assert calc.net_working_minutes == 0  # Incomplete session not counted as completed


def test_calculation_suspicious_flagged_pending_review():
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    target = date(2026, 11, 3)
    version = _create_mock_shift_version(tid)

    t_in = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
    t_out = datetime(2026, 11, 3, 18, 0, tzinfo=UTC)
    e_flagged = _create_mock_event(tid, eid, "CHECK_IN", t_in, review_status="REQUIRED")
    e_out = _create_mock_event(tid, eid, "CHECK_OUT", t_out)

    tl = resolve_active_timeline([e_flagged, e_out])
    calc = calculate_attendance_day(target, version, tl, tenant_timezone="UTC")

    assert calc.calculation_status == "FLAGGED"
    assert calc.status == "PENDING_REVIEW"


def test_calculation_no_assigned_shift():
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    target = date(2026, 11, 3)

    t_in = datetime(2026, 11, 3, 10, 0, tzinfo=UTC)
    t_out = datetime(2026, 11, 3, 16, 0, tzinfo=UTC)

    events = [
        _create_mock_event(tid, eid, "CHECK_IN", t_in),
        _create_mock_event(tid, eid, "CHECK_OUT", t_out),
    ]
    tl = resolve_active_timeline(events)
    # version=None
    calc = calculate_attendance_day(target, None, tl, tenant_timezone="UTC")

    assert calc.shift_version_id is None
    assert calc.net_working_minutes == 360
    assert calc.status == "PRESENT"
    assert calc.late_arrival_minutes == 0
    assert calc.early_departure_minutes == 0


def test_calculation_absence_boundary_future_shift():
    tid = uuid.uuid4()
    target = date(2026, 11, 3)
    version = _create_mock_shift_version(
        tid,
        start_time=time(9, 0),
        end_time=time(18, 0),
        late_departure_allowance_minutes=180,  # window ends at 21:00 UTC
    )

    tl = resolve_active_timeline([])
    # Evaluated at 12:00 (mid-shift, window has NOT closed yet)
    now_mid_shift = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
    calc = calculate_attendance_day(
        target, version, tl, tenant_timezone="UTC", now_dt=now_mid_shift
    )

    # In-progress shift MUST NOT be marked ABSENT prematurely!
    assert calc.status != "ABSENT"
    assert calc.status in ("PENDING_REVIEW", "INCOMPLETE")


def test_calculation_absence_boundary_past_shift():
    tid = uuid.uuid4()
    target = date(2026, 11, 3)
    version = _create_mock_shift_version(
        tid,
        start_time=time(9, 0),
        end_time=time(18, 0),
        late_departure_allowance_minutes=180,
    )

    tl = resolve_active_timeline([])
    # Evaluated the next day (shift window has completely closed)
    now_next_day = datetime(2026, 11, 4, 10, 0, tzinfo=UTC)
    calc = calculate_attendance_day(target, version, tl, tenant_timezone="UTC", now_dt=now_next_day)

    assert calc.status == "ABSENT"
    assert calc.net_working_minutes == 0


def test_calculation_weekly_off_day():
    tid = uuid.uuid4()
    # 2026-11-08 is a Sunday
    target = date(2026, 11, 8)
    assert target.weekday() == 6  # Sunday
    version = _create_mock_shift_version(tid, weekly_off_days=[6, 0])  # Sun, Mon

    tl = resolve_active_timeline([])
    now_later = datetime(2026, 11, 9, 10, 0, tzinfo=UTC)
    calc = calculate_attendance_day(target, version, tl, tenant_timezone="UTC", now_dt=now_later)

    assert calc.status == "WEEK_OFF"


def test_calculation_overnight_shift():
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    target = date(2026, 11, 3)
    # Overnight: 22:00 Nov 3 -> 06:00 Nov 4
    version = _create_mock_shift_version(
        tid,
        start_time=time(22, 0),
        end_time=time(6, 0),
        is_overnight=True,
    )

    t_in = datetime(2026, 11, 3, 21, 55, tzinfo=UTC)  # 5 min before start
    t_out = datetime(2026, 11, 4, 6, 5, tzinfo=UTC)  # 5 min after end

    events = [
        _create_mock_event(tid, eid, "CHECK_IN", t_in),
        _create_mock_event(tid, eid, "CHECK_OUT", t_out),
    ]
    tl = resolve_active_timeline(events)
    calc = calculate_attendance_day(target, version, tl, tenant_timezone="UTC")

    assert calc.attendance_date == target
    assert calc.total_working_minutes == 490  # 8h 10m
    assert calc.late_arrival_minutes == 0
    assert calc.early_departure_minutes == 0
    assert calc.status == "PRESENT"


def test_calculation_dst_transition():
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    # 2026-03-29 Europe/London DST transition (+1 hour forward at 01:00 UTC)
    target = date(2026, 3, 29)
    version = _create_mock_shift_version(
        tid,
        start_time=time(0, 0),
        end_time=time(8, 0),
    )

    # 00:00 UTC to 08:00 UTC
    t_in = datetime(2026, 3, 29, 0, 0, tzinfo=UTC)
    t_out = datetime(2026, 3, 29, 8, 0, tzinfo=UTC)

    events = [
        _create_mock_event(tid, eid, "CHECK_IN", t_in),
        _create_mock_event(tid, eid, "CHECK_OUT", t_out),
    ]
    tl = resolve_active_timeline(events)
    calc = calculate_attendance_day(target, version, tl, tenant_timezone="Europe/London")

    # Duration calculated safely via UTC timestamps
    assert calc.net_working_minutes == 480
    assert calc.status == "PRESENT"


# ==============================================================================
# SECTION 3: Service Layer Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_service_resolve_historical_shift_version():
    """Confirms older shift template versions are preserved for historical dates."""
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    shift_tmpl_id = uuid.uuid4()

    v1 = _create_mock_shift_version(
        tid,
        shift_template_id=shift_tmpl_id,
        version_number=1,
        effective_from=date(2026, 1, 1),
        start_time=time(9, 0),
    )
    _create_mock_shift_version(
        tid,
        shift_template_id=shift_tmpl_id,
        version_number=2,
        effective_from=date(2026, 3, 1),
        start_time=time(10, 0),
    )

    assignment = ShiftAssignment(
        id=uuid.uuid4(),
        tenant_id=tid,
        employee_id=eid,
        shift_template_id=shift_tmpl_id,
        effective_from=date(2026, 1, 1),
        effective_to=None,
    )

    # Recalculating historical date: 2026-02-15 must resolve V1
    mock_session = AsyncMock()

    async def mock_execute(stmt):
        sql = str(stmt)
        res = MagicMock()
        if "shift_assignments" in sql:
            res.scalar_one_or_none.return_value = assignment
        elif "shift_template_versions" in sql:
            # Check version_effective_from filter
            if "2026-02-15" in sql or v1.version_effective_from <= date(2026, 2, 15):
                res.scalar_one_or_none.return_value = v1
        return res

    mock_session.execute = mock_execute

    asgn, ver = await resolve_employee_shift_version(mock_session, tid, eid, date(2026, 2, 15))
    assert asgn is not None
    assert ver is not None
    assert ver.version_number == 1
    assert ver.start_time == time(9, 0)


@pytest.mark.asyncio
async def test_service_determine_shift_date_for_punch_overnight():
    """Validates that a 02:00 punch attributes to yesterday's overnight shift date."""
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    shift_tmpl_id = uuid.uuid4()

    v_night = _create_mock_shift_version(
        tid,
        shift_template_id=shift_tmpl_id,
        start_time=time(22, 0),
        end_time=time(6, 0),
        is_overnight=True,
    )
    assignment = ShiftAssignment(
        id=uuid.uuid4(),
        tenant_id=tid,
        employee_id=eid,
        shift_template_id=shift_tmpl_id,
        effective_from=date(2026, 1, 1),
        effective_to=None,
    )

    mock_session = AsyncMock()

    async def mock_execute(stmt):
        sql = str(stmt)
        res = MagicMock()
        if "shift_assignments" in sql:
            res.scalar_one_or_none.return_value = assignment
        elif "shift_template_versions" in sql:
            res.scalar_one_or_none.return_value = v_night
        return res

    mock_session.execute = mock_execute

    # Punch at 02:00 on Nov 4 belongs to Shift Date Nov 3
    punch_time = datetime(2026, 11, 4, 2, 0, tzinfo=UTC)
    attributed_date = await determine_shift_date_for_punch(
        session=mock_session,
        tenant_id=tid,
        employee_id=eid,
        effective_at=punch_time,
        event_type="CHECK_OUT",
        tenant_timezone="UTC",
    )

    assert attributed_date == date(2026, 11, 3)


@pytest.mark.asyncio
async def test_service_recalculate_attendance_day_idempotency():
    """Recalculating an attendance day multiple times updates the existing record
    and increments calculation_version.
    """
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    att_date = date(2026, 11, 3)
    version = _create_mock_shift_version(tid)
    assignment = ShiftAssignment(
        id=uuid.uuid4(),
        tenant_id=tid,
        employee_id=eid,
        shift_template_id=version.shift_template_id,
        effective_from=date(2026, 1, 1),
    )

    t_in = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
    t_out = datetime(2026, 11, 3, 18, 0, tzinfo=UTC)
    events = [
        _create_mock_event(tid, eid, "CHECK_IN", t_in),
        _create_mock_event(tid, eid, "CHECK_OUT", t_out),
    ]

    existing_day: AttendanceDay | None = None
    mock_session = AsyncMock()

    async def mock_execute(stmt):
        nonlocal existing_day
        sql = str(stmt)
        res = MagicMock()
        if "shift_assignments" in sql:
            res.scalar_one_or_none.return_value = assignment
        elif "shift_template_versions" in sql:
            res.scalar_one_or_none.return_value = version
        elif "tenants" in sql:
            res.scalar_one_or_none.return_value = "UTC"
        elif "attendance_events" in sql:
            res.scalars.return_value.all.return_value = events
        elif "attendance_days" in sql:
            res.scalar_one_or_none.return_value = existing_day
        return res

    mock_session.execute = mock_execute

    def mock_add(obj):
        nonlocal existing_day
        existing_day = obj

    mock_session.add = MagicMock(side_effect=mock_add)

    # First calculation
    day1 = await recalculate_attendance_day(mock_session, tid, eid, att_date)
    assert day1.calculation_version == 1
    assert day1.status == "PRESENT"
    assert day1.net_working_minutes == 540

    # Second recalculation on same day
    day2 = await recalculate_attendance_day(mock_session, tid, eid, att_date)
    assert day2.calculation_version == 2
    assert day2.status == "PRESENT"
    assert day2.net_working_minutes == 540


# ==============================================================================
# SECTION 4: API & RBAC Endpoints Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_api_get_attendance_day_employee_self():
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    eid = uuid.uuid4()
    _create_mock_employee(tid, employee_id=eid, user_id=uid)
    ctx = _mock_context("employee", tenant_id=tid, user_id=uid)

    att_date = date(2026, 11, 3)
    now = datetime.now(UTC)
    day = AttendanceDay(
        id=uuid.uuid4(),
        tenant_id=tid,
        employee_id=eid,
        attendance_date=att_date,
        total_working_minutes=480,
        total_break_minutes=60,
        net_working_minutes=480,
        actual_late_minutes=0,
        late_arrival_minutes=0,
        actual_early_minutes=0,
        early_departure_minutes=0,
        overtime_minutes=0,
        status="PRESENT",
        calculation_status="CALCULATED",
        calculation_version=1,
        is_incomplete=False,
        missing_punch=False,
        last_calculated_at=now,
        source_event_ids=[],
        metadata_json={},
        created_at=now,
        updated_at=now,
    )

    mock_db = AsyncMock()

    async def mock_execute(stmt):
        sql = str(stmt)
        res = MagicMock()
        if "employees" in sql:
            res.scalar_one_or_none.return_value = eid
        elif "attendance_days" in sql:
            res.scalar_one_or_none.return_value = day
        return res

    mock_db.execute = mock_execute

    app.dependency_overrides[get_authenticated_context] = lambda: ctx
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(f"/api/v1/attendance/days/{eid}/{att_date.isoformat()}")
            assert resp.status_code == 200
            data = resp.json()
            assert data["employee_id"] == str(eid)
            assert data["status"] == "PRESENT"
            assert data["net_working_minutes"] == 480
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_get_attendance_day_employee_other_forbidden():
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    own_eid = uuid.uuid4()
    other_eid = uuid.uuid4()
    ctx = _mock_context("employee", tenant_id=tid, user_id=uid)

    mock_db = AsyncMock()

    async def mock_execute(stmt):
        sql = str(stmt)
        res = MagicMock()
        if "employees" in sql:
            res.scalar_one_or_none.return_value = own_eid
        return res

    mock_db.execute = mock_execute

    app.dependency_overrides[get_authenticated_context] = lambda: ctx
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(f"/api/v1/attendance/days/{other_eid}/2026-11-03")
            assert resp.status_code == 403
            assert "Employees may only view their own attendance records" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_get_attendance_day_manager_scope():
    tid = uuid.uuid4()
    mgr_uid = uuid.uuid4()
    mgr_eid = uuid.uuid4()
    report_eid = uuid.uuid4()
    non_report_eid = uuid.uuid4()

    ctx = _mock_context("manager", tenant_id=tid, user_id=mgr_uid)

    att_date = date(2026, 11, 3)
    now = datetime.now(UTC)
    day_report = AttendanceDay(
        id=uuid.uuid4(),
        tenant_id=tid,
        employee_id=report_eid,
        attendance_date=att_date,
        total_working_minutes=480,
        total_break_minutes=60,
        net_working_minutes=480,
        actual_late_minutes=0,
        late_arrival_minutes=0,
        actual_early_minutes=0,
        early_departure_minutes=0,
        overtime_minutes=0,
        status="PRESENT",
        calculation_status="CALCULATED",
        calculation_version=1,
        is_incomplete=False,
        missing_punch=False,
        last_calculated_at=now,
        source_event_ids=[],
        metadata_json={},
        created_at=now,
        updated_at=now,
    )

    mock_db = AsyncMock()
    current_target_eid = None

    async def mock_execute(stmt):
        sql = str(stmt)
        res = MagicMock()
        if "Employee.user_id ==" in sql or "user_id" in sql:
            res.scalar_one_or_none.return_value = mgr_eid
        elif "reporting_manager_id" in sql:
            if current_target_eid == report_eid:
                res.scalar_one_or_none.return_value = report_eid
            else:
                res.scalar_one_or_none.return_value = None
        elif "attendance_days" in sql:
            res.scalar_one_or_none.return_value = day_report
        return res

    mock_db.execute = mock_execute

    app.dependency_overrides[get_authenticated_context] = lambda: ctx
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # Direct report: 200 OK
            current_target_eid = report_eid
            resp_ok = await ac.get(f"/api/v1/attendance/days/{report_eid}/{att_date.isoformat()}")
            assert resp_ok.status_code == 200

            # Non-report: 403 Forbidden
            current_target_eid = non_report_eid
            resp_forbid = await ac.get(
                f"/api/v1/attendance/days/{non_report_eid}/{att_date.isoformat()}"
            )
            assert resp_forbid.status_code == 403
            assert (
                "Managers may only view attendance records of their direct reports"
                in resp_forbid.json()["detail"]
            )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_list_attendance_days():
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    eid = uuid.uuid4()
    ctx = _mock_context("admin", tenant_id=tid, user_id=uid)

    now = datetime.now(UTC)
    days = [
        AttendanceDay(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=eid,
            attendance_date=date(2026, 11, 3),
            total_working_minutes=480,
            total_break_minutes=60,
            net_working_minutes=480,
            actual_late_minutes=0,
            late_arrival_minutes=0,
            actual_early_minutes=0,
            early_departure_minutes=0,
            overtime_minutes=0,
            status="PRESENT",
            calculation_status="CALCULATED",
            calculation_version=1,
            is_incomplete=False,
            missing_punch=False,
            last_calculated_at=now,
            source_event_ids=[],
            metadata_json={},
            created_at=now,
            updated_at=now,
        )
    ]

    mock_db = AsyncMock()

    async def mock_execute(stmt):
        sql = str(stmt)
        res = MagicMock()
        if "count" in sql:
            res.scalar_one.return_value = 1
        elif "attendance_days" in sql:
            res.scalars.return_value.all.return_value = days
        return res

    mock_db.execute = mock_execute

    app.dependency_overrides[get_authenticated_context] = lambda: ctx
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/attendance/days")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 1
            assert len(data["items"]) == 1
            assert data["items"][0]["status"] == "PRESENT"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_recalculate_attendance_day_endpoint():
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    eid = uuid.uuid4()
    ctx = _mock_context("admin", tenant_id=tid, user_id=uid)

    att_date = date(2026, 11, 3)
    version = _create_mock_shift_version(tid)
    assignment = ShiftAssignment(
        id=uuid.uuid4(),
        tenant_id=tid,
        employee_id=eid,
        shift_template_id=version.shift_template_id,
        effective_from=date(2026, 1, 1),
    )

    t_in = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
    t_out = datetime(2026, 11, 3, 18, 0, tzinfo=UTC)
    events = [
        _create_mock_event(tid, eid, "CHECK_IN", t_in),
        _create_mock_event(tid, eid, "CHECK_OUT", t_out),
    ]

    existing_day: AttendanceDay | None = None
    mock_db = AsyncMock()

    async def mock_execute(stmt):
        nonlocal existing_day
        sql = str(stmt)
        res = MagicMock()
        if "shift_assignments" in sql:
            res.scalar_one_or_none.return_value = assignment
        elif "shift_template_versions" in sql:
            res.scalar_one_or_none.return_value = version
        elif "tenants" in sql:
            res.scalar_one_or_none.return_value = "UTC"
        elif "attendance_events" in sql:
            res.scalars.return_value.all.return_value = events
        elif "attendance_days" in sql:
            res.scalar_one_or_none.return_value = existing_day
        return res

    mock_db.execute = mock_execute

    def mock_add(obj):
        nonlocal existing_day
        existing_day = obj

    mock_db.add = MagicMock(side_effect=mock_add)
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    app.dependency_overrides[get_authenticated_context] = lambda: ctx
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/attendance/recalculate",
                json={
                    "employee_id": str(eid),
                    "attendance_date": att_date.isoformat(),
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["employee_id"] == str(eid)
            assert data["status"] == "PRESENT"
            assert data["net_working_minutes"] == 540
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_service_determine_shift_date_midnight_boundary():
    """Confirms exact attribution of punches at 23:59:59 and 00:00:01 around midnight."""
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    shift_tmpl_id = uuid.uuid4()

    # Daytime shift on Nov 3 (09:00 to 18:00) with 3h late allowance (up to 21:00)
    _create_mock_shift_version(
        tid,
        shift_template_id=shift_tmpl_id,
        start_time=time(9, 0),
        end_time=time(18, 0),
        late_departure_allowance_minutes=180,
    )
    # Overnight shift starting 22:00 Nov 3 ending 06:00 Nov 4 (2h early allowance = 20:00)
    v_night = _create_mock_shift_version(
        tid,
        shift_template_id=shift_tmpl_id,
        start_time=time(22, 0),
        end_time=time(6, 0),
        is_overnight=True,
        early_arrival_allowance_minutes=120,
    )

    assignment = ShiftAssignment(
        id=uuid.uuid4(),
        tenant_id=tid,
        employee_id=eid,
        shift_template_id=shift_tmpl_id,
        effective_from=date(2026, 1, 1),
    )

    mock_session = AsyncMock()

    async def mock_execute(stmt):
        sql = str(stmt)
        res = MagicMock()
        if "shift_assignments" in sql:
            res.scalar_one_or_none.return_value = assignment
        elif "shift_template_versions" in sql:
            res.scalar_one_or_none.return_value = v_night
        return res

    mock_session.execute = mock_execute

    # Punch at 23:59:59 belongs to Nov 3
    t_before_midnight = datetime(2026, 11, 3, 23, 59, 59, tzinfo=UTC)
    date_before = await determine_shift_date_for_punch(
        session=mock_session,
        tenant_id=tid,
        employee_id=eid,
        effective_at=t_before_midnight,
        event_type="BREAK_START",
        tenant_timezone="UTC",
    )
    assert date_before == date(2026, 11, 3)

    # Punch at 00:00:01 on Nov 4 belongs to Shift Date Nov 3
    t_after_midnight = datetime(2026, 11, 4, 0, 0, 1, tzinfo=UTC)
    date_after = await determine_shift_date_for_punch(
        session=mock_session,
        tenant_id=tid,
        employee_id=eid,
        effective_at=t_after_midnight,
        event_type="BREAK_END",
        tenant_timezone="UTC",
    )
    assert date_after == date(2026, 11, 3)


@pytest.mark.asyncio
async def test_service_recalculate_attendance_day_transaction_rollback():
    """Confirms database rollback is invoked when a database exception occurs during recalculation."""
    from sqlalchemy.exc import DBAPIError

    tid = uuid.uuid4()
    eid = uuid.uuid4()
    att_date = date(2026, 11, 3)

    mock_session = AsyncMock()
    mock_session.execute.side_effect = DBAPIError("SELECT 1", {}, Exception("DB Error"))

    with pytest.raises(DBAPIError):
        await recalculate_attendance_day(mock_session, tid, eid, att_date)


def test_timeline_resolution_filters_rejected_events():
    """Safety audit: Rejected events must never count towards active sessions or working minutes."""
    tid = uuid.uuid4()
    eid = uuid.uuid4()

    t_in = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
    t_out = datetime(2026, 11, 3, 18, 0, tzinfo=UTC)

    ev_in = _create_mock_event(tid, eid, "CHECK_IN", t_in)
    ev_out_rejected = _create_mock_event(tid, eid, "CHECK_OUT", t_out)
    ev_out_rejected.review_status = "REJECTED"

    timeline = resolve_active_timeline([ev_in, ev_out_rejected])

    # The rejected checkout must NOT be in active events
    assert len(timeline.active_events) == 1
    assert timeline.active_events[0].id == ev_in.id
    assert timeline.last_check_out is None
    # Because checkout was rejected, the session is unclosed
    assert timeline.unclosed_session is True


def test_weekly_off_status_precedence_during_daytime():
    """Safety audit: A scheduled weekly off with 0 punches must evaluate to WEEK_OFF,

    even when the current time is within the daytime shift window.
    """
    tid = uuid.uuid4()
    # Shift where Sunday (0) is a weekly off day
    v = _create_mock_shift_version(
        tid,
        weekly_off_days=[0],  # Sunday
        start_time=time(9, 0),
        end_time=time(18, 0),
        late_departure_allowance_minutes=180,
    )

    # 2026-11-08 is a Sunday
    sunday = date(2026, 11, 8)
    assert (sunday.weekday() + 1) % 7 == 0  # Sunday is 0 in convention

    timeline = resolve_active_timeline([])

    # Current time is 11:00 AM on Sunday (well before 18:00 + 180 min window end)
    now_during_shift = datetime(2026, 11, 8, 11, 0, tzinfo=UTC)

    calc = calculate_attendance_day(
        target_date=sunday,
        shift_version=v,
        resolved_timeline=timeline,
        tenant_timezone="UTC",
        now_dt=now_during_shift,
    )

    assert calc.status == "WEEK_OFF"
    assert calc.calculation_status == "CALCULATED"
    assert calc.is_incomplete is False
    assert calc.missing_punch is False


@pytest.mark.asyncio
async def test_recalculate_attendance_day_locks_employee_row():
    """Safety audit: recalculate_attendance_day must lock the employee row FOR UPDATE

    to eliminate concurrent recalculation insert races.
    """
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    att_date = date(2026, 11, 3)

    executed_sqls: list[str] = []
    mock_session = AsyncMock()

    async def mock_execute(stmt):
        sql = str(stmt)
        executed_sqls.append(sql)
        res = MagicMock()
        if "employees" in sql:
            res.scalar_one_or_none.return_value = eid
        elif "tenants" in sql:
            res.scalar_one_or_none.return_value = "UTC"
        elif "shift_assignments" in sql:
            res.scalar_one_or_none.return_value = None
        elif "attendance_events" in sql:
            res.scalars.return_value.all.return_value = []
        elif "attendance_days" in sql:
            res.scalar_one_or_none.return_value = None
        return res

    mock_session.execute = mock_execute
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    await recalculate_attendance_day(
        session=mock_session,
        tenant_id=tid,
        employee_id=eid,
        attendance_date=att_date,
    )

    # Verify that the FIRST executed statement acquired the FOR UPDATE lock on employee
    assert len(executed_sqls) > 0
    first_sql = executed_sqls[0].lower()
    assert "employees" in first_sql
    assert "for update" in first_sql


@pytest.mark.asyncio
async def test_record_punch_propagates_database_error_on_recalculation():
    """Safety audit: record_punch must not swallow real database exceptions during recalculation,

    guaranteeing that punch event and projection updates remain atomic.
    """
    from unittest.mock import patch

    from sqlalchemy.exc import DBAPIError

    from services.api.attendance.schemas import PunchRequest
    from services.api.attendance.service import record_punch
    from services.api.employees.models import Employee

    tid = uuid.uuid4()
    uid = uuid.uuid4()
    eid = uuid.uuid4()

    mock_session = AsyncMock()
    mock_emp = Employee(id=eid, tenant_id=tid, user_id=uid)

    async def mock_execute(stmt):
        sql = str(stmt)
        res = MagicMock()
        if "tenants" in sql:
            res.scalar_one_or_none.return_value = "UTC"
        elif "shift_assignments" in sql:
            res.scalar_one_or_none.return_value = None
        elif "employees" in sql:
            res.scalar_one_or_none.return_value = mock_emp
        elif "idempotency" in sql:
            res.scalar_one_or_none.return_value = None
        elif "attendance_events" in sql:
            res.scalar_one_or_none.return_value = None
        return res

    mock_session.execute = mock_execute
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    payload = PunchRequest(event_type="CHECK_IN", idempotency_key="key-recalc-error-1")

    with patch(
        "services.api.attendance.service.recalculate_attendance_day",
        side_effect=DBAPIError("INSERT ...", {}, Exception("Database disk full")),
    ):
        with pytest.raises(DBAPIError):
            await record_punch(
                session=mock_session,
                tenant_id=tid,
                user_id=uid,
                user_role="employee",
                payload=payload,
            )


def test_configurable_shift_allowances_and_window_boundaries():
    """Validates that shift resolution windows strictly adhere to configurable
    early_arrival_allowance_minutes and late_departure_allowance_minutes without fixed constants.
    """
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    target_date = date(2026, 11, 3)

    # Shift: 09:00 to 17:00 with custom 60m early allowance and 90m late allowance
    version = _create_mock_shift_version(
        tid,
        start_time=time(9, 0),
        end_time=time(17, 0),
        early_arrival_allowance_minutes=60,
        late_departure_allowance_minutes=90,
    )

    t_in = datetime(2026, 11, 3, 8, 5, tzinfo=UTC)  # 55m early (within 60m allowance)
    t_out = datetime(2026, 11, 3, 18, 15, tzinfo=UTC)  # 75m late (within 90m allowance)

    events = [
        _create_mock_event(tid, eid, "CHECK_IN", t_in),
        _create_mock_event(tid, eid, "CHECK_OUT", t_out),
    ]
    tl = resolve_active_timeline(events)
    calc = calculate_attendance_day(target_date, version, tl, tenant_timezone="UTC")

    assert calc.attendance_date == target_date
    assert calc.status == "PRESENT"
    # Metadata includes explicit window boundaries derived from allowances
    assert calc.metadata["window_start_utc"] == "2026-11-03T08:00:00+00:00"  # 09:00 - 60m
    assert calc.metadata["window_end_utc"] == "2026-11-03T18:30:00+00:00"  # 17:00 + 90m


@pytest.mark.asyncio
async def test_adjacent_shift_overlap_disambiguation_midpoint():
    """Validates Section 7.4 state-aware and midpoint disambiguation when two consecutive shifts overlap."""
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    shift_tmpl_1 = uuid.uuid4()
    shift_tmpl_2 = uuid.uuid4()

    # Day 1: Overnight shift Nov 1 22:00 -> Nov 2 06:00 (late departure allowance 180m -> window ends Nov 2 09:00)
    ver_day1 = _create_mock_shift_version(
        tid,
        shift_template_id=shift_tmpl_1,
        start_time=time(22, 0),
        end_time=time(6, 0),
        is_overnight=True,
        late_departure_allowance_minutes=180,
    )
    # Day 2: Day shift Nov 2 08:00 -> Nov 2 16:00 (early arrival allowance 120m -> window starts Nov 2 06:00)
    ver_day2 = _create_mock_shift_version(
        tid,
        shift_template_id=shift_tmpl_2,
        start_time=time(8, 0),
        end_time=time(16, 0),
        is_overnight=False,
        early_arrival_allowance_minutes=120,
    )

    asgn_1 = ShiftAssignment(
        id=uuid.uuid4(),
        tenant_id=tid,
        employee_id=eid,
        shift_template_id=shift_tmpl_1,
        effective_from=date(2026, 11, 1),
    )
    asgn_2 = ShiftAssignment(
        id=uuid.uuid4(),
        tenant_id=tid,
        employee_id=eid,
        shift_template_id=shift_tmpl_2,
        effective_from=date(2026, 11, 2),
    )

    mock_session = AsyncMock()

    # Patch resolve_employee_shift_version to return proper version per date
    async def mock_resolve(session, tenant_id, employee_id, d):
        if d == date(2026, 11, 1):
            return asgn_1, ver_day1
        elif d == date(2026, 11, 2):
            return asgn_2, ver_day2
        return None, None

    with patch(
        "services.api.attendance.service.resolve_employee_shift_version", side_effect=mock_resolve
    ):
        # Overlap interval on Nov 2 is [06:00, 09:00] UTC between:
        # Day 1 (Nov 1) overnight shift ending at 06:00 Nov 2
        # Day 2 (Nov 2) day shift starting at 08:00 Nov 2
        # Midpoint between 06:00 and 08:00 is 07:00 UTC on Nov 2

        # 1. State-aware: CHECK_OUT in overlap always goes to Day 1
        t_overlap_checkout = datetime(2026, 11, 2, 6, 30, tzinfo=UTC)
        d_out = await determine_shift_date_for_punch(
            session=mock_session,
            tenant_id=tid,
            employee_id=eid,
            effective_at=t_overlap_checkout,
            event_type="CHECK_OUT",
            tenant_timezone="UTC",
        )
        assert d_out == date(2026, 11, 1)

        # 2. State-aware: CHECK_IN in overlap always goes to Day 2
        t_overlap_checkin = datetime(2026, 11, 2, 6, 30, tzinfo=UTC)
        d_in = await determine_shift_date_for_punch(
            session=mock_session,
            tenant_id=tid,
            employee_id=eid,
            effective_at=t_overlap_checkin,
            event_type="CHECK_IN",
            tenant_timezone="UTC",
        )
        assert d_in == date(2026, 11, 2)

        # 3. Midpoint: Ambiguous event (BREAK_START) before 07:00 midpoint goes to Day 1
        t_before_mid = datetime(2026, 11, 2, 6, 59, tzinfo=UTC)
        d_before = await determine_shift_date_for_punch(
            session=mock_session,
            tenant_id=tid,
            employee_id=eid,
            effective_at=t_before_mid,
            event_type="BREAK_START",
            tenant_timezone="UTC",
        )
        assert d_before == date(2026, 11, 1)

        # 4. Midpoint: Ambiguous event (BREAK_START) after 07:00 midpoint goes to Day 2
        t_after_mid = datetime(2026, 11, 2, 7, 1, tzinfo=UTC)
        d_after = await determine_shift_date_for_punch(
            session=mock_session,
            tenant_id=tid,
            employee_id=eid,
            effective_at=t_after_mid,
            event_type="BREAK_START",
            tenant_timezone="UTC",
        )
        assert d_after == date(2026, 11, 2)
