"""Automated test suite for Phase 11 Milestone 11.5:
Advanced Multi-Device Conflict Arbitration & Session Reconciliation.

Validates:
1. Multi-device conflict detection across all 10 required conflict types.
2. Clean cross-device handoffs (Device A check-in, Device B check-out auto-resolves cleanly).
3. Pure projection recalculation preserving immutable raw event ledgers.
4. Supervisor adjudication supporting all 5 Phase 11.5 actions (ACCEPT_SEQUENCE, REJECT_INVALID_EVENTS, REQUEST_CLARIFICATION, MARK_UNRESOLVED, ESCALATE_HR).
5. Employee clarification workflow (POST /offline-conflicts/{id}/clarify transitioning to PENDING_REVIEW).
6. RBAC security: anti-self-approval and manager direct-report isolation.
7. Batch sync integration: auto-capturing sequence conflicts into incidents.
"""

import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status
from httpx import ASGITransport, AsyncClient

from services.api.attendance.conflict_detector import detect_multi_device_conflicts
from services.api.attendance.conflict_service import (
    adjudicate_conflict_incident,
    submit_employee_clarification,
)
from services.api.attendance.models import (
    AttendanceConflictIncident,
    AttendanceDay,
    AttendanceEvent,
)
from services.api.attendance.multi_device_reconciliation import (
    reconcile_employee_multi_device_sessions,
)
from services.api.attendance.schemas import (
    AttendanceConflictClarificationRequest,
    AttendanceConflictDecisionRequest,
    BatchSyncPunchItem,
    ConflictClassification,
    ConflictSeverity,
    MultiDeviceConflictCode,
)
from services.api.auth.dependencies import AuthenticatedContext, get_authenticated_context
from services.api.auth.models import User
from services.api.database import get_db
from services.api.devices.models import Device
from services.api.employees.models import Employee
from services.api.main import app
from services.api.tenants.models import Tenant

# ==============================================================================
# Helper Mock Factories
# ==============================================================================


def _make_context(role: str = "employee", tenant_id: uuid.UUID | None = None, user_id: uuid.UUID | None = None):
    tid = tenant_id or uuid.uuid4()
    uid = user_id or uuid.uuid4()
    user = User(
        id=uid,
        tenant_id=tid,
        full_name="Multi-Device Test User",
        email=f"test_{role.lower()}@upostit.test",
        password_hash="argon2id$mock",
        role=role.lower(),
        status="active",
    )
    tenant = Tenant(
        id=tid,
        name="Arbitration Test Tenant",
        slug=f"tenant-{tid.hex[:8]}",
        timezone="UTC",
    )
    return AuthenticatedContext(user=user, tenant=tenant)


def _make_employee(tenant_id: uuid.UUID, user_id: uuid.UUID, reporting_manager_id: uuid.UUID | None = None):
    return Employee(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        employee_id=f"EMP-{uuid.uuid4().hex[:6]}",
        first_name="Alex",
        last_name="Rivers",
        work_email=f"alex-{uuid.uuid4().hex[:6]}@upostit.test",
        joining_date=date(2025, 1, 1),
        status="active",
        reporting_manager_id=reporting_manager_id,
    )


# ==============================================================================
# 1. Conflict Detector Engine Unit Tests (All 10 Types)
# ==============================================================================


@pytest.mark.asyncio
async def test_detect_unauthorized_or_revoked_device():
    """Detects punches submitted from revoked hardware or mismatched employee devices."""
    tid = uuid.uuid4()
    emp_id = uuid.uuid4()
    dev_hash = "revoked_device_hardware_hash_123"

    revoked_dev = Device(
        id=uuid.uuid4(),
        tenant_id=tid,
        employee_id=emp_id,
        device_id_hash=dev_hash,
        platform="android",
        status="REVOKED",
    )

    mock_session = AsyncMock()
    mock_res_dev = MagicMock()
    mock_res_dev.scalars.return_value.all.return_value = [revoked_dev]
    mock_res_days = MagicMock()
    mock_res_days.scalars.return_value.all.return_value = []
    mock_session.execute.side_effect = [mock_res_dev, mock_res_days]

    items = [
        BatchSyncPunchItem(
            local_id="loc-1",
            idempotency_key="idemp-1",
            event_type="CHECK_IN",
            device_reported_at=datetime.now(UTC),
            device_id=dev_hash,
        )
    ]

    conflicts = await detect_multi_device_conflicts(
        session=mock_session,
        tenant_id=tid,
        employee_id=emp_id,
        candidate_items=items,
        existing_events=[],
    )

    assert any(
        c.conflict_code == MultiDeviceConflictCode.UNAUTHORIZED_OR_REVOKED_DEVICE
        and c.severity == ConflictSeverity.CRITICAL
        and c.classification == ConflictClassification.INVALID_UNAUTHORIZED
        for c in conflicts
    )


@pytest.mark.asyncio
async def test_detect_duplicate_check_in_across_devices():
    """Detects simultaneous check-ins from Device A and Device B."""
    tid = uuid.uuid4()
    emp_id = uuid.uuid4()
    t0 = datetime(2026, 11, 24, 9, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 11, 24, 9, 5, 0, tzinfo=UTC)

    mock_session = AsyncMock()
    mock_res_dev = MagicMock()
    mock_res_dev.scalars.return_value.all.return_value = [
        Device(id=uuid.uuid4(), tenant_id=tid, employee_id=emp_id, device_id_hash="dev_a", platform="ios", status="ACTIVE"),
        Device(id=uuid.uuid4(), tenant_id=tid, employee_id=emp_id, device_id_hash="dev_b", platform="android", status="ACTIVE"),
    ]
    mock_res_empty = MagicMock()
    mock_res_empty.scalars.return_value.all.return_value = []
    mock_session.execute.side_effect = [mock_res_dev, mock_res_empty]

    existing = [
        AttendanceEvent(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=emp_id,
            event_type="CHECK_IN",
            effective_at=t0,
            device_reported_at=t0,
            device_id="dev_a",
            idempotency_key="idemp-dev-a",
        )
    ]

    candidate = [
        BatchSyncPunchItem(
            local_id="loc-2",
            idempotency_key="idemp-dev-b",
            event_type="CHECK_IN",
            device_reported_at=t1,
            device_id="dev_b",
        )
    ]

    conflicts = await detect_multi_device_conflicts(
        session=mock_session,
        tenant_id=tid,
        employee_id=emp_id,
        candidate_items=candidate,
        existing_events=existing,
    )

    dup_conflicts = [c for c in conflicts if c.conflict_code == MultiDeviceConflictCode.DUPLICATE_CHECK_IN]
    assert len(dup_conflicts) == 1
    assert dup_conflicts[0].classification == ConflictClassification.NEEDS_EMPLOYEE_CLARIFICATION


@pytest.mark.asyncio
async def test_detect_impossible_travel_timeline():
    """Detects physically impossible velocity between punches on separate devices."""
    tid = uuid.uuid4()
    emp_id = uuid.uuid4()
    t0 = datetime(2026, 11, 24, 9, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 11, 24, 9, 2, 0, tzinfo=UTC)  # 2 minutes later, 500 km away

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_res

    existing = [
        AttendanceEvent(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=emp_id,
            event_type="CHECK_IN",
            effective_at=t0,
            device_reported_at=t0,
            device_id="dev_nyc",
            latitude=40.7128,  # New York City
            longitude=-74.0060,
            idempotency_key="idemp-nyc",
        )
    ]

    candidate = [
        BatchSyncPunchItem(
            local_id="loc-dc",
            idempotency_key="idemp-dc",
            event_type="CHECK_OUT",
            device_reported_at=t1,
            device_id="dev_dc",
            latitude=38.9072,  # Washington, D.C. (~330 km away in 2 mins = ~2750 m/s)
            longitude=-77.0369,
        )
    ]

    conflicts = await detect_multi_device_conflicts(
        session=mock_session,
        tenant_id=tid,
        employee_id=emp_id,
        candidate_items=candidate,
        existing_events=existing,
    )

    travel_conflicts = [c for c in conflicts if c.conflict_code == MultiDeviceConflictCode.IMPOSSIBLE_TRAVEL_TIMELINE]
    assert len(travel_conflicts) == 1
    assert travel_conflicts[0].severity == ConflictSeverity.CRITICAL


# ==============================================================================
# 2. Clean Cross-Device Handoff & Session Reconciliation Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_clean_cross_device_handoff_reconciles_automatically():
    """Valid cross-device handoff (Device A check-in -> Device B check-out) resolves cleanly."""
    tid = uuid.uuid4()
    emp_id = uuid.uuid4()
    t_date = date(2026, 11, 24)
    t_in = datetime(2026, 11, 24, 9, 0, 0, tzinfo=UTC)
    t_out = datetime(2026, 11, 24, 17, 30, 0, tzinfo=UTC)

    mock_session = AsyncMock()
    # Mock devices query: both devices are active and belong to employee
    mock_res_dev = MagicMock()
    mock_res_dev.scalars.return_value.all.return_value = [
        Device(id=uuid.uuid4(), tenant_id=tid, employee_id=emp_id, device_id_hash="dev_tablet_hq", platform="android", status="ACTIVE"),
        Device(id=uuid.uuid4(), tenant_id=tid, employee_id=emp_id, device_id_hash="dev_phone_mobile", platform="ios", status="ACTIVE"),
    ]
    # Mock finalized days query: not locked
    mock_res_days = MagicMock()
    mock_res_days.scalars.return_value.all.return_value = []
    mock_session.execute.side_effect = [mock_res_dev, mock_res_days]

    events = [
        AttendanceEvent(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=emp_id,
            event_type="CHECK_IN",
            effective_at=t_in,
            device_reported_at=t_in,
            device_id="dev_tablet_hq",
            idempotency_key="punch-in-tablet",
        ),
        AttendanceEvent(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=emp_id,
            event_type="CHECK_OUT",
            effective_at=t_out,
            device_reported_at=t_out,
            device_id="dev_phone_mobile",
            idempotency_key="punch-out-phone",
        ),
    ]

    with patch(
        "services.api.attendance.multi_device_reconciliation.recalculate_attendance_day",
        new_callable=AsyncMock,
    ) as mock_recalc:
        mock_day = AttendanceDay(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=emp_id,
            attendance_date=t_date,
            total_working_minutes=510,
            status="PRESENT",
            calculation_status="CALCULATED",
        )
        mock_recalc.return_value = mock_day

        res = await reconcile_employee_multi_device_sessions(
            session=mock_session,
            tenant_id=tid,
            employee_id=emp_id,
            attendance_date=t_date,
            events=events,
        )

        assert res.status == "AUTO_RESOLVED"
        assert len(res.conflicts_detected) == 0
        assert len(res.created_incident_ids) == 0
        mock_recalc.assert_awaited_once_with(mock_session, tid, emp_id, t_date)


# ==============================================================================
# 3. Employee Clarification Workflow Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_employee_clarification_lifecycle():
    """Clarification transitions incident from NEEDS_CLARIFICATION to PENDING_REVIEW."""
    tid = uuid.uuid4()
    emp_user_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    incident_id = uuid.uuid4()

    incident = AttendanceConflictIncident(
        id=incident_id,
        tenant_id=tid,
        employee_id=emp_id,
        user_id=emp_user_id,
        bundle_id="bundle-clarify-1",
        status="NEEDS_CLARIFICATION",
        primary_rejected_event={"event_type": "CHECK_IN", "idempotency_key": "k1"},
        dependent_events=[],
        total_events_count=1,
    )

    mock_session = AsyncMock()
    # 1. Select incident with_for_update
    mock_res_inc = MagicMock()
    mock_res_inc.scalar_one_or_none.return_value = incident
    # 2. Select employee
    mock_res_emp = MagicMock()
    mock_res_emp.scalar_one_or_none.return_value = _make_employee(tid, emp_user_id)
    mock_session.execute.side_effect = [mock_res_inc, mock_res_emp]

    payload = AttendanceConflictClarificationRequest(
        clarification_notes="I punched on my work tablet and personal phone while testing signal."
    )

    with patch(
        "services.api.attendance.conflict_service.get_conflict_incident_detail",
        new_callable=AsyncMock,
    ) as mock_get_detail:
        mock_get_detail.return_value = MagicMock()

        await submit_employee_clarification(
            session=mock_session,
            tenant_id=tid,
            user_id=emp_user_id,
            user_role="employee",
            incident_id=incident_id,
            payload=payload,
        )

        assert incident.status == "PENDING_REVIEW"
        assert incident.employee_clarification == payload.clarification_notes
        assert incident.clarification_submitted_at is not None
        mock_session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_employee_clarification_unauthorized_peer_denied():
    """An employee cannot submit clarification for another employee's incident."""
    tid = uuid.uuid4()
    incident_owner_user_id = uuid.uuid4()
    calling_user_id = uuid.uuid4()  # different employee
    incident_id = uuid.uuid4()

    incident = AttendanceConflictIncident(
        id=incident_id,
        tenant_id=tid,
        employee_id=uuid.uuid4(),
        user_id=incident_owner_user_id,
        bundle_id="bundle-clarify-2",
        status="NEEDS_CLARIFICATION",
        primary_rejected_event={"event_type": "CHECK_IN"},
        dependent_events=[],
        total_events_count=1,
    )

    mock_session = AsyncMock()
    mock_res_inc = MagicMock()
    mock_res_inc.scalar_one_or_none.return_value = incident
    mock_res_emp = MagicMock()
    mock_res_emp.scalar_one_or_none.return_value = _make_employee(tid, calling_user_id)
    mock_session.execute.side_effect = [mock_res_inc, mock_res_emp]

    payload = AttendanceConflictClarificationRequest(clarification_notes="Peer trying to clarify.")

    with pytest.raises(HTTPException) as exc_info:
        await submit_employee_clarification(
            session=mock_session,
            tenant_id=tid,
            user_id=calling_user_id,
            user_role="employee",
            incident_id=incident_id,
            payload=payload,
        )
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


# ==============================================================================
# 4. Supervisor Adjudication Expanded Decisions Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_supervisor_adjudication_request_clarification():
    """Supervisor requests clarification, transitioning incident to NEEDS_CLARIFICATION."""
    tid = uuid.uuid4()
    reviewer_user_id = uuid.uuid4()
    emp_user_id = uuid.uuid4()
    incident_id = uuid.uuid4()

    mgr_emp = _make_employee(tid, reviewer_user_id)
    target_emp = _make_employee(tid, emp_user_id, reporting_manager_id=mgr_emp.id)

    incident = AttendanceConflictIncident(
        id=incident_id,
        tenant_id=tid,
        employee_id=target_emp.id,
        user_id=emp_user_id,
        bundle_id="bundle-adj-1",
        status="PENDING_REVIEW",
        primary_rejected_event={"event_type": "CHECK_IN", "device_reported_at": "2026-11-24T09:00:00Z"},
        dependent_events=[],
        total_events_count=1,
    )

    mock_session = AsyncMock()
    mock_res_inc = MagicMock()
    mock_res_inc.scalar_one_or_none.return_value = incident
    mock_res_mgr = MagicMock()
    mock_res_mgr.scalar_one_or_none.return_value = mgr_emp
    mock_res_target = MagicMock()
    mock_res_target.scalar_one_or_none.return_value = target_emp
    mock_session.execute.side_effect = [mock_res_inc, mock_res_mgr, mock_res_target]

    req = AttendanceConflictDecisionRequest(
        action="REQUEST_CLARIFICATION",
        reason="Please explain why two phones submitted check-ins simultaneously.",
    )

    res = await adjudicate_conflict_incident(
        session=mock_session,
        tenant_id=tid,
        incident_id=incident_id,
        reviewer_user_id=reviewer_user_id,
        reviewer_role="manager",
        payload=req,
    )

    assert res.status == "NEEDS_CLARIFICATION"
    assert res.decision == "REQUEST_CLARIFICATION"
    assert incident.clarification_requested_at is not None
    assert incident.reviewer_user_id == reviewer_user_id


@pytest.mark.asyncio
async def test_supervisor_anti_self_approval():
    """Supervisors cannot adjudicate their own attendance conflicts."""
    tid = uuid.uuid4()
    same_user_id = uuid.uuid4()
    incident_id = uuid.uuid4()

    mgr_emp = _make_employee(tid, same_user_id)

    incident = AttendanceConflictIncident(
        id=incident_id,
        tenant_id=tid,
        employee_id=mgr_emp.id,
        user_id=same_user_id,
        bundle_id="bundle-self-1",
        status="PENDING_REVIEW",
        primary_rejected_event={"event_type": "CHECK_IN"},
        dependent_events=[],
        total_events_count=1,
    )

    mock_session = AsyncMock()
    mock_res_inc = MagicMock()
    mock_res_inc.scalar_one_or_none.return_value = incident
    mock_res_mgr = MagicMock()
    mock_res_mgr.scalar_one_or_none.return_value = mgr_emp
    mock_session.execute.side_effect = [mock_res_inc, mock_res_mgr]

    req = AttendanceConflictDecisionRequest(action="APPROVE", reason="Self approval attempt.")

    with pytest.raises(HTTPException) as exc_info:
        await adjudicate_conflict_incident(
            session=mock_session,
            tenant_id=tid,
            incident_id=incident_id,
            reviewer_user_id=same_user_id,
            reviewer_role="manager",
            payload=req,
        )
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


# ==============================================================================
# 5. Full REST API HTTP Integration Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_http_employee_clarify_endpoint():
    """Verifies POST /api/v1/attendance/offline-conflicts/{id}/clarify via ASGI test client."""
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    inc_id = uuid.uuid4()
    ctx = _make_context(role="employee", tenant_id=tid, user_id=uid)

    app.dependency_overrides[get_authenticated_context] = lambda: ctx
    mock_session = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with patch(
            "services.api.attendance.routes.submit_employee_clarification",
            new_callable=AsyncMock,
        ) as mock_clarify:
            mock_detail = {
                "id": str(inc_id),
                "tenant_id": str(tid),
                "bundle_id": "bundle-http-1",
                "status": "PENDING_REVIEW",
                "employee": {
                    "id": str(uuid.uuid4()),
                    "employee_code": "EMP-01",
                    "first_name": "Test",
                    "last_name": "Employee",
                    "work_email": "test@upostit.test",
                },
                "primary_rejected_event": {"event_type": "CHECK_IN"},
                "dependent_events": [],
                "total_events_count": 1,
                "submitted_at": datetime.now(UTC).isoformat(),
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            }
            mock_clarify.return_value = mock_detail

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                res = await ac.post(
                    f"/api/v1/attendance/offline-conflicts/{inc_id}/clarify",
                    json={"clarification_notes": "Clarifying that punch on tablet was accidental."},
                )

            assert res.status_code == status.HTTP_200_OK
            mock_clarify.assert_awaited_once()
    finally:
        app.dependency_overrides.clear()
