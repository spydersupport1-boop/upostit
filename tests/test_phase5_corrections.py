"""Comprehensive unit and API integration tests for Phase 5 Milestone 4:
Attendance Correction Engine, Audit Trail & Reconciliation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import DBAPIError

from services.api.attendance.correction_service import (
    apply_attendance_correction,
    get_attendance_day_event_audit_trail,
)
from services.api.attendance.engine import resolve_active_timeline
from services.api.attendance.models import (
    AttendanceDay,
    AttendanceEvent,
    AttendanceIdempotencyRecord,
    ShiftTemplateVersion,
)
from services.api.attendance.reconciliation import run_attendance_reconciliation
from services.api.attendance.schemas import (
    AttendanceCorrectionCreateRequest,
    AttendanceCorrectionType,
    ReconciliationRequest,
)
from services.api.auth.models import User
from services.api.employees.models import Employee
from services.api.main import app  # noqa: F401
from services.workers.tasks import reconcile_nightly_attendance_task

# ==============================================================================
# Helper Mock Factories
# ==============================================================================


def _create_mock_user(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
    role: str = "admin",
) -> User:
    u = User(
        id=user_id or uuid.uuid4(),
        tenant_id=tenant_id,
        email="test@example.com",
        password_hash="hash",
        full_name="Test User",
        role=role,
        is_active=True,
    )
    return u


def _create_mock_employee(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    reporting_manager_id: uuid.UUID | None = None,
) -> Employee:
    eid = employee_id or uuid.uuid4()
    emp = Employee(
        id=eid,
        tenant_id=tenant_id,
        user_id=user_id or uuid.uuid4(),
        employee_id=f"EMP-{eid.hex[:6]}",
        first_name="Jane",
        last_name="Doe",
        work_email=f"jane_{eid.hex[:6]}@example.com",
        reporting_manager_id=reporting_manager_id,
        employment_type="full_time",
        status="active",
    )
    return emp


def _create_mock_shift_version(
    tenant_id: uuid.UUID,
    shift_template_id: uuid.UUID | None = None,
    start_time: time = time(9, 0),
    end_time: time = time(17, 0),
    is_overnight: bool = False,
    early_arrival_allowance_minutes: int = 120,
    late_departure_allowance_minutes: int = 180,
) -> ShiftTemplateVersion:
    return ShiftTemplateVersion(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        shift_template_id=shift_template_id or uuid.uuid4(),
        version_number=1,
        version_effective_from=date(2026, 1, 1),
        start_time=start_time,
        end_time=end_time,
        grace_period_minutes=15,
        early_exit_grace_minutes=15,
        early_arrival_allowance_minutes=early_arrival_allowance_minutes,
        late_departure_allowance_minutes=late_departure_allowance_minutes,
        half_day_threshold_minutes=240,
        full_day_threshold_minutes=480,
        break_duration_minutes=60,
        is_overnight=is_overnight,
        is_flexible=False,
        weekly_off_days=[6, 0],
    )


def _create_mock_event(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    event_type: str,
    effective_at: datetime,
    event_id: uuid.UUID | None = None,
    event_category: str = "STANDARD",
    supersedes_event_id: uuid.UUID | None = None,
    correction_reason: str | None = None,
) -> AttendanceEvent:
    return AttendanceEvent(
        id=event_id or uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=employee_id,
        event_type=event_type,
        event_category=event_category,
        supersedes_event_id=supersedes_event_id,
        correction_reason=correction_reason,
        server_received_at=effective_at,
        effective_at=effective_at,
        source="WEB",
        review_status="NOT_REQUIRED",
        timestamp_verification_status="SERVER_AUTHORITATIVE",
        idempotency_key=f"key-{uuid.uuid4().hex[:12]}",
        metadata_json={},
        created_at=effective_at,
    )


# ==============================================================================
# Unit Tests: Pure Timeline Resolution with Corrections
# ==============================================================================


def test_timeline_resolution_correction_insert():
    """Verify CORRECTION_INSERT adds an active punch into the resolved timeline."""
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    t_in = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
    t_out_corr = datetime(2026, 11, 3, 17, 0, tzinfo=UTC)

    e1 = _create_mock_event(tid, eid, "CHECK_IN", t_in)
    e2 = _create_mock_event(
        tid,
        eid,
        "CHECK_OUT",
        t_out_corr,
        event_category="CORRECTION_INSERT",
        correction_reason="Employee forgot to checkout on departure",
    )

    timeline = resolve_active_timeline([e1, e2])
    assert len(timeline.active_events) == 2
    assert timeline.first_check_in == t_in
    assert timeline.last_check_out == t_out_corr
    assert timeline.unclosed_session is False


def test_timeline_resolution_correction_supersede():
    """Verify CORRECTION_SUPERSEDE replaces an incorrect punch with a corrected punch."""
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    t_in = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
    t_out_wrong = datetime(2026, 11, 3, 14, 0, tzinfo=UTC)
    t_out_correct = datetime(2026, 11, 3, 17, 0, tzinfo=UTC)

    e1 = _create_mock_event(tid, eid, "CHECK_IN", t_in)
    e2_wrong = _create_mock_event(tid, eid, "CHECK_OUT", t_out_wrong)
    e3_corr = _create_mock_event(
        tid,
        eid,
        "CHECK_OUT",
        t_out_correct,
        event_category="CORRECTION_SUPERSEDE",
        supersedes_event_id=e2_wrong.id,
        correction_reason="Premature accidental badge checkout superseded",
    )

    timeline = resolve_active_timeline([e1, e2_wrong, e3_corr])
    assert len(timeline.active_events) == 2
    # e2_wrong must be excluded
    active_ids = [e.id for e in timeline.active_events]
    assert e2_wrong.id not in active_ids
    assert e3_corr.id in active_ids
    assert timeline.last_check_out == t_out_correct


def test_timeline_resolution_correction_void():
    """Verify CORRECTION_VOID purges an invalid punch and leaves no active punch in place."""
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    t_in = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
    t_in_accidental = datetime(2026, 11, 3, 11, 0, tzinfo=UTC)
    t_out = datetime(2026, 11, 3, 17, 0, tzinfo=UTC)

    e1 = _create_mock_event(tid, eid, "CHECK_IN", t_in)
    e2_accidental = _create_mock_event(tid, eid, "CHECK_IN", t_in_accidental)
    e3_void = _create_mock_event(
        tid,
        eid,
        "CHECK_IN",
        t_in_accidental,
        event_category="CORRECTION_VOID",
        supersedes_event_id=e2_accidental.id,
        correction_reason="Double badge accidental entry voided",
    )
    e4_out = _create_mock_event(tid, eid, "CHECK_OUT", t_out)

    timeline = resolve_active_timeline([e1, e2_accidental, e3_void, e4_out])
    assert len(timeline.active_events) == 2
    active_ids = [e.id for e in timeline.active_events]
    assert e2_accidental.id not in active_ids
    assert e3_void.id not in active_ids  # Tombstone must not be in active timeline
    assert active_ids == [e1.id, e4_out.id]


def test_timeline_resolution_transitive_supersession():
    """Verify transitive chain E1 -> superseded by E2 -> superseded by E3 retains only E3."""
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    t1 = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
    t2 = datetime(2026, 11, 3, 9, 10, tzinfo=UTC)
    t3 = datetime(2026, 11, 3, 9, 5, tzinfo=UTC)

    e1 = _create_mock_event(tid, eid, "CHECK_IN", t1)
    e2 = _create_mock_event(
        tid,
        eid,
        "CHECK_IN",
        t2,
        event_category="CORRECTION_SUPERSEDE",
        supersedes_event_id=e1.id,
        correction_reason="First correction estimate",
    )
    e3 = _create_mock_event(
        tid,
        eid,
        "CHECK_IN",
        t3,
        event_category="CORRECTION_SUPERSEDE",
        supersedes_event_id=e2.id,
        correction_reason="Second accurate correction verified by CCTV",
    )

    timeline = resolve_active_timeline([e1, e2, e3])
    assert len(timeline.active_events) == 1
    assert timeline.active_events[0].id == e3.id
    assert timeline.first_check_in == t3


# ==============================================================================
# Service Layer Tests: apply_attendance_correction
# ==============================================================================


@pytest.mark.asyncio
async def test_apply_correction_insert_success():
    """Verify admin can insert a missing check-out and trigger projection recalculation."""
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    eid = uuid.uuid4()
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()

    # Mock DB query results
    async def mock_execute(stmt):
        sql = str(stmt)
        res = MagicMock()
        if "FROM employees" in sql:
            res.scalar_one_or_none.return_value = eid
        elif "FROM attendance_idempotency_records" in sql:
            res.scalar_one_or_none.return_value = None
        elif "FROM tenants" in sql:
            res.scalar_one_or_none.return_value = "UTC"
        return res

    mock_session.execute = mock_execute
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.get = AsyncMock(return_value=None)

    payload = AttendanceCorrectionCreateRequest(
        employee_id=eid,
        correction_type=AttendanceCorrectionType.CORRECTION_INSERT,
        event_type="CHECK_OUT",
        effective_at=datetime(2026, 11, 3, 17, 0, tzinfo=UTC),
        correction_reason="Manual check-out recorded by manager",
        idempotency_key="key-corr-ins-01",
    )

    dummy_day = AttendanceDay(
        id=uuid.uuid4(),
        tenant_id=tid,
        employee_id=eid,
        attendance_date=date(2026, 11, 3),
        total_working_minutes=480,
        total_break_minutes=0,
        net_working_minutes=480,
        actual_late_minutes=0,
        late_arrival_minutes=0,
        actual_early_minutes=0,
        early_departure_minutes=0,
        overtime_minutes=0,
        status="PRESENT",
        calculation_status="CALCULATED",
        calculation_version=2,
        is_incomplete=False,
        missing_punch=False,
        source_event_ids=[],
        metadata_json={},
        last_calculated_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    with (
        patch(
            "services.api.attendance.correction_service.determine_shift_date_for_punch",
            return_value=date(2026, 11, 3),
        ),
        patch(
            "services.api.attendance.correction_service.resolve_employee_shift_version",
            return_value=(None, None),
        ),
        patch(
            "services.api.attendance.correction_service.recalculate_attendance_day",
            return_value=dummy_day,
        ),
    ):
        resp = await apply_attendance_correction(
            session=mock_session,
            tenant_id=tid,
            actor_user_id=uid,
            actor_role="admin",
            payload=payload,
        )

        assert resp.correction_event.event_category == "CORRECTION_INSERT"
        assert resp.correction_event.event_type == "CHECK_OUT"
        assert resp.affected_attendance_dates == [date(2026, 11, 3)]
        assert len(resp.recalculated_days) == 1
        assert resp.recalculated_days[0].status == "PRESENT"
        assert resp.idempotent_replay is False


@pytest.mark.asyncio
async def test_apply_correction_supersede_success():
    """Verify admin can supersede an incorrect punch and link to original via supersedes_event_id."""
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    eid = uuid.uuid4()
    orig_event_id = uuid.uuid4()

    orig_event = _create_mock_event(
        tid, eid, "CHECK_OUT", datetime(2026, 11, 3, 14, 0, tzinfo=UTC), event_id=orig_event_id
    )

    mock_session = AsyncMock()

    async def mock_execute(stmt):
        sql = str(stmt)
        res = MagicMock()
        if "FROM employees" in sql:
            res.scalar_one_or_none.return_value = eid
        elif "FROM attendance_idempotency_records" in sql:
            res.scalar_one_or_none.return_value = None
        elif "FROM attendance_events" in sql:
            if "attendance_events.supersedes_event_id =" in sql:
                res.fetchall.return_value = []  # No existing children
            else:
                res.scalar_one_or_none.return_value = orig_event
        elif "FROM tenants" in sql:
            res.scalar_one_or_none.return_value = "UTC"
        return res

    mock_session.execute = mock_execute
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.get = AsyncMock(return_value=None)

    payload = AttendanceCorrectionCreateRequest(
        employee_id=eid,
        correction_type=AttendanceCorrectionType.CORRECTION_SUPERSEDE,
        event_type="CHECK_OUT",
        effective_at=datetime(2026, 11, 3, 17, 0, tzinfo=UTC),
        supersedes_event_id=orig_event_id,
        correction_reason="Superseding incorrect early departure punch",
        idempotency_key="key-corr-sup-01",
    )

    dummy_day = AttendanceDay(
        id=uuid.uuid4(),
        tenant_id=tid,
        employee_id=eid,
        attendance_date=date(2026, 11, 3),
        total_working_minutes=480,
        total_break_minutes=0,
        net_working_minutes=480,
        actual_late_minutes=0,
        late_arrival_minutes=0,
        actual_early_minutes=0,
        early_departure_minutes=0,
        overtime_minutes=0,
        status="PRESENT",
        calculation_status="CALCULATED",
        calculation_version=2,
        is_incomplete=False,
        missing_punch=False,
        source_event_ids=[],
        metadata_json={},
        last_calculated_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    with (
        patch(
            "services.api.attendance.correction_service.determine_shift_date_for_punch",
            return_value=date(2026, 11, 3),
        ),
        patch(
            "services.api.attendance.correction_service.resolve_employee_shift_version",
            return_value=(None, None),
        ),
        patch(
            "services.api.attendance.correction_service.recalculate_attendance_day",
            return_value=dummy_day,
        ),
    ):
        resp = await apply_attendance_correction(
            session=mock_session,
            tenant_id=tid,
            actor_user_id=uid,
            actor_role="admin",
            payload=payload,
        )

        assert resp.correction_event.event_category == "CORRECTION_SUPERSEDE"
        assert resp.correction_event.supersedes_event_id == orig_event_id
        # Original event was not modified
        assert orig_event.event_type == "CHECK_OUT"
        assert orig_event.effective_at == datetime(2026, 11, 3, 14, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_apply_correction_void_success():
    """Verify admin can void an erroneous duplicate punch."""
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    eid = uuid.uuid4()
    orig_event_id = uuid.uuid4()

    orig_event = _create_mock_event(
        tid, eid, "CHECK_IN", datetime(2026, 11, 3, 12, 0, tzinfo=UTC), event_id=orig_event_id
    )

    mock_session = AsyncMock()

    async def mock_execute(stmt):
        sql = str(stmt)
        res = MagicMock()
        if "FROM employees" in sql:
            res.scalar_one_or_none.return_value = eid
        elif "FROM attendance_idempotency_records" in sql:
            res.scalar_one_or_none.return_value = None
        elif "FROM attendance_events" in sql:
            if "attendance_events.supersedes_event_id =" in sql:
                res.fetchall.return_value = []
            else:
                res.scalar_one_or_none.return_value = orig_event
        elif "FROM tenants" in sql:
            res.scalar_one_or_none.return_value = "UTC"
        return res

    mock_session.execute = mock_execute
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.get = AsyncMock(return_value=None)

    payload = AttendanceCorrectionCreateRequest(
        employee_id=eid,
        correction_type=AttendanceCorrectionType.CORRECTION_VOID,
        supersedes_event_id=orig_event_id,
        correction_reason="Voiding accidental duplicate badge punch",
        idempotency_key="key-corr-void-01",
    )

    dummy_day = AttendanceDay(
        id=uuid.uuid4(),
        tenant_id=tid,
        employee_id=eid,
        attendance_date=date(2026, 11, 3),
        total_working_minutes=480,
        total_break_minutes=0,
        net_working_minutes=480,
        actual_late_minutes=0,
        late_arrival_minutes=0,
        actual_early_minutes=0,
        early_departure_minutes=0,
        overtime_minutes=0,
        status="PRESENT",
        calculation_status="CALCULATED",
        calculation_version=2,
        is_incomplete=False,
        missing_punch=False,
        source_event_ids=[],
        metadata_json={},
        last_calculated_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    with (
        patch(
            "services.api.attendance.correction_service.determine_shift_date_for_punch",
            return_value=date(2026, 11, 3),
        ),
        patch(
            "services.api.attendance.correction_service.resolve_employee_shift_version",
            return_value=(None, None),
        ),
        patch(
            "services.api.attendance.correction_service.recalculate_attendance_day",
            return_value=dummy_day,
        ),
    ):
        resp = await apply_attendance_correction(
            session=mock_session,
            tenant_id=tid,
            actor_user_id=uid,
            actor_role="admin",
            payload=payload,
        )

        assert resp.correction_event.event_category == "CORRECTION_VOID"
        assert resp.correction_event.supersedes_event_id == orig_event_id


# ==============================================================================
# Security, RBAC & Reporting Scope Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_employee_cannot_submit_correction():
    """Verify employees receive HTTP 403 when attempting to submit corrections."""
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    eid = uuid.uuid4()
    mock_session = AsyncMock()

    payload = AttendanceCorrectionCreateRequest(
        employee_id=eid,
        correction_type=AttendanceCorrectionType.CORRECTION_INSERT,
        event_type="CHECK_IN",
        effective_at=datetime(2026, 11, 3, 9, 0, tzinfo=UTC),
        correction_reason="Employee self-correction attempt",
        idempotency_key="key-emp-fail",
    )

    with pytest.raises(HTTPException) as exc_info:
        await apply_attendance_correction(
            session=mock_session,
            tenant_id=tid,
            actor_user_id=uid,
            actor_role="employee",
            payload=payload,
        )
    assert exc_info.value.status_code == 403
    assert "Employees cannot directly submit attendance corrections" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_manager_cannot_correct_non_report():
    """Verify manager cannot correct attendance of an employee who does not report to them."""
    tid = uuid.uuid4()
    mgr_user_id = uuid.uuid4()
    mgr_emp_id = uuid.uuid4()
    other_emp_id = uuid.uuid4()

    mock_session = AsyncMock()

    async def mock_execute(stmt):
        sql = str(stmt)
        res = MagicMock()
        if "reporting_manager_id" in sql:
            res.scalar_one_or_none.return_value = None  # Not a report!
        elif "employees" in sql:
            res.scalar_one_or_none.return_value = mgr_emp_id
        return res

    mock_session.execute = mock_execute

    payload = AttendanceCorrectionCreateRequest(
        employee_id=other_emp_id,
        correction_type=AttendanceCorrectionType.CORRECTION_INSERT,
        event_type="CHECK_IN",
        effective_at=datetime(2026, 11, 3, 9, 0, tzinfo=UTC),
        correction_reason="Manager trying to correct unrelated employee",
        idempotency_key="key-mgr-unrelated",
    )

    with pytest.raises(HTTPException) as exc_info:
        await apply_attendance_correction(
            session=mock_session,
            tenant_id=tid,
            actor_user_id=mgr_user_id,
            actor_role="manager",
            payload=payload,
        )
    assert exc_info.value.status_code == 403
    assert "Managers may only correct attendance records of their direct reports" in str(
        exc_info.value.detail
    )


@pytest.mark.asyncio
async def test_manager_cannot_correct_self():
    """Verify manager cannot administratively correct their own attendance."""
    tid = uuid.uuid4()
    mgr_user_id = uuid.uuid4()
    mgr_emp_id = uuid.uuid4()

    mock_session = AsyncMock()

    async def mock_execute(stmt):
        sql = str(stmt)
        res = MagicMock()
        if "employees" in sql:
            res.scalar_one_or_none.return_value = mgr_emp_id
        return res

    mock_session.execute = mock_execute

    payload = AttendanceCorrectionCreateRequest(
        employee_id=mgr_emp_id,
        correction_type=AttendanceCorrectionType.CORRECTION_INSERT,
        event_type="CHECK_IN",
        effective_at=datetime(2026, 11, 3, 9, 0, tzinfo=UTC),
        correction_reason="Manager self-correction attempt",
        idempotency_key="key-mgr-self",
    )

    with pytest.raises(HTTPException) as exc_info:
        await apply_attendance_correction(
            session=mock_session,
            tenant_id=tid,
            actor_user_id=mgr_user_id,
            actor_role="manager",
            payload=payload,
        )
    assert exc_info.value.status_code == 403
    assert "Managers cannot correct their own attendance records" in str(exc_info.value.detail)


# ==============================================================================
# Disallowed & Invalid Correction Attempts
# ==============================================================================


@pytest.mark.asyncio
async def test_cannot_correct_event_belonging_to_another_employee():
    """Verify error when target event employee does not match correction request employee."""
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    emp_a = uuid.uuid4()
    emp_b = uuid.uuid4()
    orig_event_id = uuid.uuid4()

    orig_event = _create_mock_event(
        tid, emp_b, "CHECK_OUT", datetime(2026, 11, 3, 17, 0, tzinfo=UTC), event_id=orig_event_id
    )

    mock_session = AsyncMock()

    async def mock_execute(stmt):
        sql = str(stmt)
        res = MagicMock()
        if "FROM employees" in sql:
            res.scalar_one_or_none.return_value = emp_a
        elif "FROM attendance_idempotency_records" in sql:
            res.scalar_one_or_none.return_value = None
        elif "FROM attendance_events" in sql:
            res.scalar_one_or_none.return_value = orig_event
        return res

    mock_session.execute = mock_execute
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    payload = AttendanceCorrectionCreateRequest(
        employee_id=emp_a,
        correction_type=AttendanceCorrectionType.CORRECTION_SUPERSEDE,
        event_type="CHECK_OUT",
        effective_at=datetime(2026, 11, 3, 18, 0, tzinfo=UTC),
        supersedes_event_id=orig_event_id,
        correction_reason="Mismatched employee correction attempt",
        idempotency_key="key-mismatch-emp",
    )

    with pytest.raises(HTTPException) as exc_info:
        await apply_attendance_correction(
            session=mock_session,
            tenant_id=tid,
            actor_user_id=uid,
            actor_role="admin",
            payload=payload,
        )
    assert exc_info.value.status_code == 400
    assert "Cannot correct an attendance event belonging to a different employee" in str(
        exc_info.value.detail
    )


@pytest.mark.asyncio
async def test_cannot_supersede_already_superseded_event():
    """Verify error when attempting to supersede an event that was already superseded."""
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    eid = uuid.uuid4()
    orig_event_id = uuid.uuid4()

    orig_event = _create_mock_event(
        tid, eid, "CHECK_OUT", datetime(2026, 11, 3, 17, 0, tzinfo=UTC), event_id=orig_event_id
    )

    existing_child = MagicMock(event_category="CORRECTION_SUPERSEDE")

    mock_session = AsyncMock()

    async def mock_execute(stmt):
        sql = str(stmt)
        res = MagicMock()
        if "FROM employees" in sql:
            res.scalar_one_or_none.return_value = eid
        elif "FROM attendance_idempotency_records" in sql:
            res.scalar_one_or_none.return_value = None
        elif "FROM attendance_events" in sql:
            if "attendance_events.supersedes_event_id =" in sql:
                res.fetchall.return_value = [existing_child]  # Already has supersede child!
            else:
                res.scalar_one_or_none.return_value = orig_event
        return res

    mock_session.execute = mock_execute
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    payload = AttendanceCorrectionCreateRequest(
        employee_id=eid,
        correction_type=AttendanceCorrectionType.CORRECTION_SUPERSEDE,
        event_type="CHECK_OUT",
        effective_at=datetime(2026, 11, 3, 18, 0, tzinfo=UTC),
        supersedes_event_id=orig_event_id,
        correction_reason="Attempting double-supersede on same target",
        idempotency_key="key-double-sup",
    )

    with pytest.raises(HTTPException) as exc_info:
        await apply_attendance_correction(
            session=mock_session,
            tenant_id=tid,
            actor_user_id=uid,
            actor_role="admin",
            payload=payload,
        )
    assert exc_info.value.status_code == 400
    assert "Cannot correct an attendance event that has already been superseded" in str(
        exc_info.value.detail
    )


@pytest.mark.asyncio
async def test_cannot_void_already_voided_event():
    """Verify error when attempting to void an event that was already voided."""
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    eid = uuid.uuid4()
    orig_event_id = uuid.uuid4()

    orig_event = _create_mock_event(
        tid, eid, "CHECK_IN", datetime(2026, 11, 3, 9, 0, tzinfo=UTC), event_id=orig_event_id
    )

    existing_child = MagicMock(event_category="CORRECTION_VOID")

    mock_session = AsyncMock()

    async def mock_execute(stmt):
        sql = str(stmt)
        res = MagicMock()
        if "FROM employees" in sql:
            res.scalar_one_or_none.return_value = eid
        elif "FROM attendance_idempotency_records" in sql:
            res.scalar_one_or_none.return_value = None
        elif "FROM attendance_events" in sql:
            if "attendance_events.supersedes_event_id =" in sql:
                res.fetchall.return_value = [existing_child]
            else:
                res.scalar_one_or_none.return_value = orig_event
        return res

    mock_session.execute = mock_execute
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    payload = AttendanceCorrectionCreateRequest(
        employee_id=eid,
        correction_type=AttendanceCorrectionType.CORRECTION_VOID,
        supersedes_event_id=orig_event_id,
        correction_reason="Attempting double-void on same target",
        idempotency_key="key-double-void",
    )

    with pytest.raises(HTTPException) as exc_info:
        await apply_attendance_correction(
            session=mock_session,
            tenant_id=tid,
            actor_user_id=uid,
            actor_role="admin",
            payload=payload,
        )
    assert exc_info.value.status_code == 400
    assert "Cannot correct an attendance event that has already been voided" in str(
        exc_info.value.detail
    )


# ==============================================================================
# Idempotency & Payload Divergence
# ==============================================================================


@pytest.mark.asyncio
async def test_correction_idempotency_replay():
    """Verify replaying exact same correction returns cached completed response with idempotent_replay=True."""
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    eid = uuid.uuid4()

    cached_resp = {
        "correction_event": {
            "id": str(uuid.uuid4()),
            "tenant_id": str(tid),
            "employee_id": str(eid),
            "event_type": "CHECK_IN",
            "event_category": "CORRECTION_INSERT",
            "effective_at": "2026-11-03T09:00:00Z",
            "server_received_at": "2026-11-03T09:00:00Z",
            "source": "ADMIN",
            "review_status": "NOT_REQUIRED",
            "timestamp_verification_status": "SERVER_AUTHORITATIVE",
            "idempotency_key": "key-cached-01",
            "created_at": "2026-11-03T09:00:00Z",
        },
        "affected_attendance_dates": ["2026-11-03"],
        "recalculated_days": [],
    }

    payload = AttendanceCorrectionCreateRequest(
        employee_id=eid,
        correction_type=AttendanceCorrectionType.CORRECTION_INSERT,
        event_type="CHECK_IN",
        effective_at=datetime(2026, 11, 3, 9, 0, tzinfo=UTC),
        correction_reason="Valid audit reason here",
        idempotency_key="key-cached-01",
    )

    from services.api.attendance.correction_service import _compute_correction_fingerprint

    fingerprint = _compute_correction_fingerprint(tid, payload)

    existing_record = AttendanceIdempotencyRecord(
        tenant_id=tid,
        employee_id=eid,
        idempotency_key="key-cached-01",
        request_fingerprint=fingerprint,
        status="COMPLETED",
        response_payload=cached_resp,
    )

    mock_session = AsyncMock()

    async def mock_execute(stmt):
        sql = str(stmt)
        res = MagicMock()
        if "employees" in sql:
            res.scalar_one_or_none.return_value = eid
        elif "idempotency" in sql:
            res.scalar_one_or_none.return_value = existing_record
        return res

    mock_session.execute = mock_execute

    resp = await apply_attendance_correction(
        session=mock_session,
        tenant_id=tid,
        actor_user_id=uid,
        actor_role="admin",
        payload=payload,
    )

    assert resp.idempotent_replay is True
    assert resp.affected_attendance_dates == [date(2026, 11, 3)]


@pytest.mark.asyncio
async def test_correction_idempotency_conflict_divergent_payload():
    """Verify reusing an idempotency key with different request payload raises HTTP 409 Conflict."""
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    eid = uuid.uuid4()

    existing_record = AttendanceIdempotencyRecord(
        tenant_id=tid,
        employee_id=eid,
        idempotency_key="key-reused-divergent",
        request_fingerprint="original_sha256_hash_different",
        status="COMPLETED",
        response_payload={},
    )

    mock_session = AsyncMock()

    async def mock_execute(stmt):
        sql = str(stmt)
        res = MagicMock()
        if "employees" in sql:
            res.scalar_one_or_none.return_value = eid
        elif "idempotency" in sql:
            res.scalar_one_or_none.return_value = existing_record
        return res

    mock_session.execute = mock_execute

    payload = AttendanceCorrectionCreateRequest(
        employee_id=eid,
        correction_type=AttendanceCorrectionType.CORRECTION_INSERT,
        event_type="CHECK_IN",
        effective_at=datetime(2026, 11, 3, 9, 0, tzinfo=UTC),
        correction_reason="Valid reason but divergent fingerprint",
        idempotency_key="key-reused-divergent",
    )

    with pytest.raises(HTTPException) as exc_info:
        await apply_attendance_correction(
            session=mock_session,
            tenant_id=tid,
            actor_user_id=uid,
            actor_role="admin",
            payload=payload,
        )
    assert exc_info.value.status_code == 409
    assert "Idempotency key reused with mismatched correction payload" in str(exc_info.value.detail)


# ==============================================================================
# Transaction & Atomicity Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_correction_atomic_rollback_on_recalculation_failure():
    """Verify that if projection recalculation fails, the exception propagates to roll back the transaction."""
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    eid = uuid.uuid4()

    mock_session = AsyncMock()

    async def mock_execute(stmt):
        sql = str(stmt)
        res = MagicMock()
        if "employees" in sql:
            res.scalar_one_or_none.return_value = eid
        elif "idempotency" in sql:
            res.scalar_one_or_none.return_value = None
        elif "tenants" in sql:
            res.scalar_one_or_none.return_value = "UTC"
        return res

    mock_session.execute = mock_execute
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    payload = AttendanceCorrectionCreateRequest(
        employee_id=eid,
        correction_type=AttendanceCorrectionType.CORRECTION_INSERT,
        event_type="CHECK_IN",
        effective_at=datetime(2026, 11, 3, 9, 0, tzinfo=UTC),
        correction_reason="Valid correction that triggers failed recalculation",
        idempotency_key="key-recalc-err",
    )

    with (
        patch(
            "services.api.attendance.correction_service.determine_shift_date_for_punch",
            return_value=date(2026, 11, 3),
        ),
        patch(
            "services.api.attendance.correction_service.resolve_employee_shift_version",
            return_value=(None, None),
        ),
        patch(
            "services.api.attendance.correction_service.recalculate_attendance_day",
            side_effect=DBAPIError(
                "UPDATE attendance_days ...", {}, Exception("Disk full / DB dead")
            ),
        ),
    ):
        with pytest.raises(DBAPIError):
            await apply_attendance_correction(
                session=mock_session,
                tenant_id=tid,
                actor_user_id=uid,
                actor_role="admin",
                payload=payload,
            )


# ==============================================================================
# Audit History & Reconciliation Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_get_attendance_day_event_audit_trail():
    """Verify retrieving complete annotated audit trail for an attendance day record."""
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    eid = uuid.uuid4()
    record_id = uuid.uuid4()
    ev1_id = uuid.uuid4()
    ev2_id = uuid.uuid4()

    target_day = AttendanceDay(
        id=record_id,
        tenant_id=tid,
        employee_id=eid,
        attendance_date=date(2026, 11, 3),
        total_working_minutes=480,
        total_break_minutes=0,
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
        source_event_ids=[str(ev1_id)],
        metadata_json={},
        last_calculated_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    ev1 = _create_mock_event(
        tid, eid, "CHECK_IN", datetime(2026, 11, 3, 9, 0, tzinfo=UTC), event_id=ev1_id
    )
    ev2_corr = _create_mock_event(
        tid,
        eid,
        "CHECK_IN",
        datetime(2026, 11, 3, 8, 55, tzinfo=UTC),
        event_id=ev2_id,
        event_category="CORRECTION_SUPERSEDE",
        supersedes_event_id=ev1_id,
        correction_reason="Badge reader 5 min slow adjustment",
    )

    mock_session = AsyncMock()

    async def mock_execute(stmt):
        sql = str(stmt)
        res = MagicMock()
        if "attendance_days" in sql:
            res.scalar_one_or_none.return_value = target_day
        elif "tenants" in sql:
            res.scalar_one_or_none.return_value = "UTC"
        elif "attendance_events" in sql:
            res.scalars.return_value.all.return_value = [ev1, ev2_corr]
        return res

    mock_session.execute = mock_execute

    with patch(
        "services.api.attendance.correction_service.resolve_employee_shift_version",
        return_value=(None, None),
    ):
        res = await get_attendance_day_event_audit_trail(
            session=mock_session,
            tenant_id=tid,
            user_id=uid,
            user_role="admin",
            record_id=record_id,
        )

        assert res.total == 2
        # ev1 was superseded by ev2_corr -> is_active must be False
        assert res.items[0].id == ev1_id
        assert res.items[0].is_active is False
        assert res.items[0].superseded_by_event_id == ev2_id

        # ev2_corr is active
        assert res.items[1].id == ev2_id
        assert res.items[1].is_active is True
        assert res.items[1].supersedes_event_id == ev1_id


@pytest.mark.asyncio
async def test_reconciliation_batch_processing_and_sanitization():
    """Verify run_attendance_reconciliation logs errors without employee PII."""
    tid = uuid.uuid4()
    emp1 = uuid.uuid4()
    emp2 = uuid.uuid4()

    mock_session = AsyncMock()

    async def mock_execute(stmt):
        sql = str(stmt)
        res = MagicMock()
        if "shift_assignments" in sql:
            res.scalars.return_value.all.return_value = [emp1, emp2]
        elif "attendance_days" in sql:
            res.scalars.return_value.all.return_value = []
        elif "attendance_events" in sql:
            res.scalars.return_value.all.return_value = []
        return res

    mock_session.execute = mock_execute
    mock_session.begin_nested = MagicMock()

    # Recalculate succeeds for emp1, fails for emp2
    async def mock_recalc(session, tenant_id, employee_id, attendance_date):
        if employee_id == emp2:
            raise ValueError("Simulated unexpected engine calculation failure")
        return MagicMock()

    payload = ReconciliationRequest(
        target_date=date(2026, 11, 3),
        batch_size=10,
    )

    with patch(
        "services.api.attendance.reconciliation.recalculate_attendance_day",
        side_effect=mock_recalc,
    ):
        result = await run_attendance_reconciliation(
            session=mock_session,
            tenant_id=tid,
            payload=payload,
        )

        assert result.status == "PARTIAL"
        assert result.total_candidates == 2
        assert result.recalculated_count == 1
        assert result.failed_count == 1
        # Check error sanitization: only UUID and Exception name, no names/emails
        assert len(result.errors) == 1
        assert f"Employee {emp2} on 2026-11-03: ValueError" in result.errors[0]
        assert "Jane Doe" not in result.errors[0]
        assert "example.com" not in result.errors[0]


def test_celery_nightly_reconciliation_task_registration():
    """Verify Celery task registration and direct execution fallback."""
    tid = uuid.uuid4()
    target_d = "2026-11-03"

    mock_result = {
        "status": "COMPLETED",
        "tenant_id": str(tid),
        "target_dates": [target_d],
        "total_candidates": 5,
        "recalculated_count": 5,
        "failed_count": 0,
        "errors": [],
    }

    def fake_run_async(coro):
        coro.close()
        return mock_result

    with patch(
        "services.workers.tasks.run_async",
        side_effect=fake_run_async,
    ):
        res = reconcile_nightly_attendance_task(
            tenant_id_str=str(tid),
            target_date_str=target_d,
        )
        assert res["status"] == "COMPLETED"
        assert res["recalculated_count"] == 5


async def test_correction_idempotency_record_completion_regression():
    """Regression test: verify apply_attendance_correction updates idem_record directly without invalid session.get."""
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    eid = uuid.uuid4()
    mock_session = AsyncMock()

    async def mock_execute(stmt):
        sql = str(stmt)
        res = MagicMock()
        if "FROM employees" in sql:
            res.scalar_one_or_none.return_value = eid
        elif "FROM attendance_idempotency_records" in sql:
            res.scalar_one_or_none.return_value = None
        elif "FROM tenants" in sql:
            res.scalar_one_or_none.return_value = "UTC"
        return res

    mock_session.execute = mock_execute
    added_objects = []

    def fake_add(obj):
        added_objects.append(obj)

    mock_session.add = fake_add
    mock_session.flush = AsyncMock()
    # Explicitly verify session.get is not called with invalid composite key
    mock_session.get = AsyncMock(side_effect=AssertionError("session.get should not be called"))

    payload = AttendanceCorrectionCreateRequest(
        employee_id=eid,
        correction_type=AttendanceCorrectionType.CORRECTION_INSERT,
        event_type="CHECK_OUT",
        effective_at=datetime(2026, 11, 3, 17, 0, tzinfo=UTC),
        correction_reason="Regression test check-out",
        idempotency_key="key-regress-01",
    )

    dummy_day = AttendanceDay(
        id=uuid.uuid4(),
        tenant_id=tid,
        employee_id=eid,
        attendance_date=date(2026, 11, 3),
        total_working_minutes=480,
        total_break_minutes=0,
        net_working_minutes=480,
        actual_late_minutes=0,
        late_arrival_minutes=0,
        actual_early_minutes=0,
        early_departure_minutes=0,
        overtime_minutes=0,
        status="PRESENT",
        calculation_status="CALCULATED",
        calculation_version=2,
        is_incomplete=False,
        missing_punch=False,
        source_event_ids=[],
        metadata_json={},
        last_calculated_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    with (
        patch(
            "services.api.attendance.correction_service.determine_shift_date_for_punch",
            return_value=date(2026, 11, 3),
        ),
        patch(
            "services.api.attendance.correction_service.resolve_employee_shift_version",
            return_value=(None, None),
        ),
        patch(
            "services.api.attendance.correction_service.recalculate_attendance_day",
            return_value=dummy_day,
        ),
    ):
        resp = await apply_attendance_correction(
            session=mock_session,
            tenant_id=tid,
            actor_user_id=uid,
            actor_role="admin",
            payload=payload,
        )

    assert resp is not None
    # Verify idempotency record in added_objects was updated to COMPLETED
    idem_records = [o for o in added_objects if isinstance(o, AttendanceIdempotencyRecord)]
    assert len(idem_records) == 1
    assert idem_records[0].status == "COMPLETED"
    assert idem_records[0].event_id is not None
    assert idem_records[0].response_payload is not None
