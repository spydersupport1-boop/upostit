"""Comprehensive unit and API integration tests for Phase 5 Milestone 2:
Attendance Event Ledger, Idempotency & Punch APIs.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from services.api.attendance.models import AttendanceEvent, AttendanceIdempotencyRecord
from services.api.attendance.schemas import (
    AttendanceEventResponse,
    PunchRequest,
    PunchResponse,
)
from services.api.attendance.service import (
    compute_request_fingerprint,
    get_attendance_event,
    list_attendance_events,
    record_punch,
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
        email=f"test_{role}@company.test",
        password_hash="argon2id$mock",
        role=role,
        status="active",
    )
    tenant = Tenant(
        id=tid,
        name="Test Presence Corp",
        slug=f"presence-{tid.hex[:6]}",
        company_email="admin@presence.test",
        country_code="IN",
        status="active",
    )
    return AuthenticatedContext(user=user, tenant=tenant)


def _create_mock_employee(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    status: str = "active",
) -> Employee:
    return Employee(
        id=employee_id or uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id or uuid.uuid4(),
        employee_id="EMP-2001",
        first_name="Alice",
        last_name="Smith",
        work_email="alice.smith@presence.test",
        employment_type="full_time",
        joining_date=date(2026, 1, 1),
        status=status,
    )


def _create_mock_event(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    event_type: str = "CHECK_IN",
    effective_at: datetime | None = None,
) -> AttendanceEvent:
    now = effective_at or datetime.now(UTC)
    return AttendanceEvent(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=employee_id,
        event_type=event_type,
        event_category="STANDARD",
        supersedes_event_id=None,
        correction_reason=None,
        server_received_at=now,
        device_reported_at=now,
        effective_at=now,
        clock_drift_seconds=Decimal("0.000"),
        source="WEB",
        device_id="browser-session-xyz",
        timestamp_verification_status="SERVER_AUTHORITATIVE",
        review_status="NOT_REQUIRED",
        idempotency_key=str(uuid.uuid4()),
        location_id=None,
        latitude=None,
        longitude=None,
        accuracy_meters=None,
        actor_user_id=None,
        metadata_json={},
        created_at=now,
    )


# ==============================================================================
# 1. Fingerprint Computation & Canonicalization Tests
# ==============================================================================


def test_fingerprint_deterministic_for_identical_payloads():
    """Verify compute_request_fingerprint generates identical SHA-256 for identical inputs."""
    emp_id = uuid.uuid4()
    req1 = PunchRequest(
        event_type="CHECK_IN",
        idempotency_key="idemp-key-12345678",
        latitude=Decimal("12.9715987"),
        longitude=Decimal("77.5945627"),
        accuracy_meters=Decimal("15.50"),
        device_id="chrome-v120-macos",
        metadata={"network": "wifi", "ip": "1.2.3.4"},
    )
    req2 = PunchRequest(
        event_type="CHECK_IN",
        idempotency_key="idemp-key-12345678",
        latitude=Decimal("12.9715987"),
        longitude=Decimal("77.5945627"),
        accuracy_meters=Decimal("15.50"),
        device_id="chrome-v120-macos",
        metadata={"ip": "1.2.3.4", "network": "wifi"},  # Out of order key
    )
    fp1 = compute_request_fingerprint(req1, emp_id)
    fp2 = compute_request_fingerprint(req2, emp_id)

    assert fp1 == fp2
    assert len(fp1) == 64


def test_fingerprint_changes_on_any_behavior_altering_field():
    """Verify compute_request_fingerprint changes if any field changes."""
    emp_id = uuid.uuid4()
    base_req = PunchRequest(
        event_type="CHECK_IN",
        idempotency_key="idemp-key-12345678",
        latitude=Decimal("12.9715987"),
        longitude=Decimal("77.5945627"),
        accuracy_meters=Decimal("15.50"),
    )
    base_fp = compute_request_fingerprint(base_req, emp_id)

    # 1. Different event_type
    req_type = base_req.model_copy(update={"event_type": "CHECK_OUT"})
    assert compute_request_fingerprint(req_type, emp_id) != base_fp

    # 2. Different employee
    assert compute_request_fingerprint(base_req, uuid.uuid4()) != base_fp

    # 3. Different coordinates
    req_coord = base_req.model_copy(update={"latitude": Decimal("12.9716000")})
    assert compute_request_fingerprint(req_coord, emp_id) != base_fp

    # 4. Different device_reported_at
    req_time = base_req.model_copy(update={"device_reported_at": datetime.now(UTC)})
    assert compute_request_fingerprint(req_time, emp_id) != base_fp

    # 5. Different location_id
    req_loc = base_req.model_copy(update={"location_id": uuid.uuid4()})
    assert compute_request_fingerprint(req_loc, emp_id) != base_fp


# ==============================================================================
# 2. Pydantic Schemas Validation Tests
# ==============================================================================


def test_punch_request_schema_validation():
    """Verify validation constraints on PunchRequest fields."""
    # Valid payload
    req = PunchRequest(
        event_type="CHECK_IN",
        idempotency_key="punch-key-12345",
    )
    assert req.event_type == "CHECK_IN"

    # Too short idempotency_key (< 8 chars)
    with pytest.raises(ValidationError):
        PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="short",
        )

    # Invalid event_type
    with pytest.raises(ValidationError):
        PunchRequest(
            event_type="UNKNOWN_PUNCH",  # type: ignore
            idempotency_key="punch-key-12345",
        )

    # Invalid latitude (> 90)
    with pytest.raises(ValidationError):
        PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="punch-key-12345",
            latitude=Decimal("95.0"),
        )

    # Invalid longitude (< -180)
    with pytest.raises(ValidationError):
        PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="punch-key-12345",
            longitude=Decimal("-185.0"),
        )


# ==============================================================================
# 3. Business Logic & State Machine Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_punch_check_in_success():
    """Verify recording CHECK_IN when currently checked out succeeds and creates ledger record."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    mock_session = AsyncMock()

    emp = _create_mock_employee(tenant_id, employee_id=emp_id, user_id=user_id)

    # 1. user_emp query -> returns emp
    res_user_emp = MagicMock()
    res_user_emp.scalar_one_or_none.return_value = emp

    # 2. lock emp query -> returns emp
    res_lock_emp = MagicMock()
    res_lock_emp.scalar_one_or_none.return_value = emp

    # 3. idempotency query -> None (new request)
    res_idem = MagicMock()
    res_idem.scalar_one_or_none.return_value = None

    # 4. latest event query -> None (currently checked out)
    res_latest = MagicMock()
    res_latest.scalar_one_or_none.return_value = None

    mock_session.execute.side_effect = [res_user_emp, res_lock_emp, res_idem, res_latest]

    payload = PunchRequest(
        event_type="CHECK_IN",
        idempotency_key="punch-key-checkin-001",
    )

    resp = await record_punch(
        session=mock_session,
        tenant_id=tenant_id,
        user_id=user_id,
        user_role="employee",
        payload=payload,
    )

    assert resp.event.event_type == "CHECK_IN"
    assert resp.event.employee_id == emp_id
    assert resp.event.source == "WEB"
    assert resp.idempotent_replay is False
    assert len(resp.additional_events) == 0
    assert mock_session.commit.called


@pytest.mark.asyncio
async def test_punch_check_in_when_already_working_fails():
    """Verify recording CHECK_IN when already working raises 400."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    mock_session = AsyncMock()

    emp = _create_mock_employee(tenant_id, employee_id=emp_id, user_id=user_id)
    latest_event = _create_mock_event(tenant_id, emp_id, event_type="CHECK_IN")

    res_user_emp = MagicMock()
    res_user_emp.scalar_one_or_none.return_value = emp
    res_lock_emp = MagicMock()
    res_lock_emp.scalar_one_or_none.return_value = emp
    res_idem = MagicMock()
    res_idem.scalar_one_or_none.return_value = None
    res_latest = MagicMock()
    res_latest.scalar_one_or_none.return_value = latest_event

    mock_session.execute.side_effect = [res_user_emp, res_lock_emp, res_idem, res_latest]

    payload = PunchRequest(
        event_type="CHECK_IN",
        idempotency_key="punch-key-checkin-002",
    )

    with pytest.raises(HTTPException) as exc:
        await record_punch(mock_session, tenant_id, user_id, "employee", payload)

    assert exc.value.status_code == 400
    assert "already checked in" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_punch_break_start_and_end_lifecycle():
    """Verify transition from CHECK_IN -> BREAK_START and BREAK_START -> BREAK_END."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    emp_id = uuid.uuid4()

    # 1. Start break when WORKING
    mock_session = AsyncMock()
    emp = _create_mock_employee(tenant_id, employee_id=emp_id, user_id=user_id)
    in_event = _create_mock_event(tenant_id, emp_id, event_type="CHECK_IN")

    mock_session.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=in_event)),
    ]

    payload_break = PunchRequest(event_type="BREAK_START", idempotency_key="key-break-start-1")
    resp_break = await record_punch(mock_session, tenant_id, user_id, "employee", payload_break)
    assert resp_break.event.event_type == "BREAK_START"

    # 2. End break when ON_BREAK
    mock_session2 = AsyncMock()
    break_event = _create_mock_event(tenant_id, emp_id, event_type="BREAK_START")
    mock_session2.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=break_event)),
    ]

    payload_end = PunchRequest(event_type="BREAK_END", idempotency_key="key-break-end-1")
    resp_end = await record_punch(mock_session2, tenant_id, user_id, "employee", payload_end)
    assert resp_end.event.event_type == "BREAK_END"


@pytest.mark.asyncio
async def test_punch_break_start_when_checked_out_fails():
    """Verify starting break without being checked in raises 400."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    mock_session = AsyncMock()

    emp = _create_mock_employee(tenant_id, employee_id=emp_id, user_id=user_id)
    mock_session.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # Checked out
    ]

    payload = PunchRequest(event_type="BREAK_START", idempotency_key="key-break-invalid")
    with pytest.raises(HTTPException) as exc:
        await record_punch(mock_session, tenant_id, user_id, "employee", payload)

    assert exc.value.status_code == 400
    assert "must check in before starting a break" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_punch_checkout_auto_closes_open_break():
    """Verify checking out while ON_BREAK automatically creates BREAK_END prior to CHECK_OUT."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    mock_session = AsyncMock()

    emp = _create_mock_employee(tenant_id, employee_id=emp_id, user_id=user_id)
    on_break_event = _create_mock_event(tenant_id, emp_id, event_type="BREAK_START")

    mock_session.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=on_break_event)),
    ]

    payload = PunchRequest(event_type="CHECK_OUT", idempotency_key="key-checkout-autoclose")
    resp = await record_punch(mock_session, tenant_id, user_id, "employee", payload)

    assert resp.event.event_type == "CHECK_OUT"
    assert len(resp.additional_events) == 1
    assert resp.additional_events[0].event_type == "BREAK_END"
    assert resp.additional_events[0].metadata.get("system_action") == "auto_closed_on_checkout"
    assert mock_session.commit.called


# ==============================================================================
# 4. Idempotency & Duplicate Replay Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_idempotency_same_key_same_payload_returns_cached_response():
    """Verify submitting the same key and identical payload replays cached response."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    mock_session = AsyncMock()

    emp = _create_mock_employee(tenant_id, employee_id=emp_id, user_id=user_id)
    payload = PunchRequest(
        event_type="CHECK_IN",
        idempotency_key="idemp-key-repeat-01",
    )
    fp = compute_request_fingerprint(payload, emp_id)

    # Mock cached event and response
    cached_event = _create_mock_event(tenant_id, emp_id, event_type="CHECK_IN")
    cached_resp_dto = PunchResponse(
        event=AttendanceEventResponse.model_validate(cached_event),
        additional_events=[],
        idempotent_replay=False,
    )

    idem_record = AttendanceIdempotencyRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp_id,
        idempotency_key="idemp-key-repeat-01",
        request_fingerprint=fp,
        status="COMPLETED",
        response_code=201,
        response_payload=cached_resp_dto.model_dump(mode="json"),
        event_id=cached_event.id,
    )

    mock_session.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=idem_record)),
    ]

    resp = await record_punch(mock_session, tenant_id, user_id, "employee", payload)

    assert resp.idempotent_replay is True
    assert resp.event.id == cached_event.id
    # Ensure no new commit was executed because cached response returned early
    assert not mock_session.commit.called


@pytest.mark.asyncio
async def test_idempotency_same_key_different_payload_returns_422():
    """Verify reusing an idempotency key with a changed payload raises HTTP 422."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    mock_session = AsyncMock()

    emp = _create_mock_employee(tenant_id, employee_id=emp_id, user_id=user_id)

    # Existing idempotency record has fingerprint from different payload
    idem_record = AttendanceIdempotencyRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp_id,
        idempotency_key="idemp-key-mismatch-01",
        request_fingerprint="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        status="COMPLETED",
    )

    mock_session.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=idem_record)),
    ]

    payload = PunchRequest(
        event_type="CHECK_IN",
        idempotency_key="idemp-key-mismatch-01",
    )

    with pytest.raises(HTTPException) as exc:
        await record_punch(mock_session, tenant_id, user_id, "employee", payload)

    assert exc.value.status_code == 422
    assert "mismatched request payload" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_idempotency_in_progress_returns_409():
    """Verify concurrent request with IN_PROGRESS idempotency status returns HTTP 409 Conflict."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    mock_session = AsyncMock()

    emp = _create_mock_employee(tenant_id, employee_id=emp_id, user_id=user_id)
    payload = PunchRequest(event_type="CHECK_IN", idempotency_key="idemp-in-progress")
    fp = compute_request_fingerprint(payload, emp_id)

    idem_record = AttendanceIdempotencyRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp_id,
        idempotency_key="idemp-in-progress",
        request_fingerprint=fp,
        status="IN_PROGRESS",
    )

    mock_session.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=idem_record)),
    ]

    with pytest.raises(HTTPException) as exc:
        await record_punch(mock_session, tenant_id, user_id, "employee", payload)

    assert exc.value.status_code == 409
    assert "currently being processed" in exc.value.detail.lower()


# ==============================================================================
# 5. Timestamp Drift & Validation Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_timestamp_drift_flagged_as_suspicious_when_exceeding_300s():
    """Verify clock drift > 300s marks timestamp_verification_status = SUSPICIOUS_CLOCK_DRIFT."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    mock_session = AsyncMock()

    emp = _create_mock_employee(tenant_id, employee_id=emp_id, user_id=user_id)
    mock_session.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # Checked out
    ]

    # Device time is 10 minutes in the past
    device_time = datetime.now(UTC) - timedelta(minutes=10)
    payload = PunchRequest(
        event_type="CHECK_IN",
        idempotency_key="key-drift-test",
        device_reported_at=device_time,
    )

    resp = await record_punch(mock_session, tenant_id, user_id, "employee", payload)

    assert resp.event.timestamp_verification_status == "SUSPICIOUS_CLOCK_DRIFT"
    assert resp.event.review_status == "PENDING_REVIEW"
    assert resp.event.clock_drift_seconds is not None
    assert resp.event.clock_drift_seconds >= Decimal("590")


@pytest.mark.asyncio
async def test_timestamp_implausible_future_rejected():
    """Verify device timestamp > 24 hours in the future is rejected with 422."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    mock_session = AsyncMock()

    emp = _create_mock_employee(tenant_id, employee_id=emp_id, user_id=user_id)
    mock_session.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
    ]

    payload = PunchRequest(
        event_type="CHECK_IN",
        idempotency_key="key-future-time",
        device_reported_at=datetime.now(UTC) + timedelta(days=2),
    )

    with pytest.raises(HTTPException) as exc:
        await record_punch(mock_session, tenant_id, user_id, "employee", payload)

    assert exc.value.status_code == 422
    assert "implausibly in the future" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_timestamp_implausible_past_rejected():
    """Verify device timestamp > 7 days in the past is rejected with 422."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    mock_session = AsyncMock()

    emp = _create_mock_employee(tenant_id, employee_id=emp_id, user_id=user_id)
    mock_session.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
    ]

    payload = PunchRequest(
        event_type="CHECK_IN",
        idempotency_key="key-old-time",
        device_reported_at=datetime.now(UTC) - timedelta(days=10),
    )

    with pytest.raises(HTTPException) as exc:
        await record_punch(mock_session, tenant_id, user_id, "employee", payload)

    assert exc.value.status_code == 422
    assert "older than allowable limit" in exc.value.detail.lower()


# ==============================================================================
# 6. Authorization & RBAC Enforcement Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_employee_cannot_punch_for_another_employee():
    """Verify employee role attempting to specify another employee's UUID raises HTTP 403."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    my_emp_id = uuid.uuid4()
    other_emp_id = uuid.uuid4()
    mock_session = AsyncMock()

    my_emp = _create_mock_employee(tenant_id, employee_id=my_emp_id, user_id=user_id)
    mock_session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=my_emp))

    payload = PunchRequest(
        event_type="CHECK_IN",
        idempotency_key="punch-attempt-spoof",
        employee_id=other_emp_id,  # Trying to punch for someone else
    )

    with pytest.raises(HTTPException) as exc:
        await record_punch(mock_session, tenant_id, user_id, "employee", payload)

    assert exc.value.status_code == 403
    assert "only record punches for themselves" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_manager_cannot_punch_for_another_employee():
    """Verify manager role cannot record punches on behalf of another employee (403)."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    manager_emp_id = uuid.uuid4()
    subordinate_emp_id = uuid.uuid4()
    mock_session = AsyncMock()

    mgr_emp = _create_mock_employee(tenant_id, employee_id=manager_emp_id, user_id=user_id)
    mock_session.execute.return_value = MagicMock(
        scalar_one_or_none=MagicMock(return_value=mgr_emp)
    )

    payload = PunchRequest(
        event_type="CHECK_IN",
        idempotency_key="punch-manager-for-other",
        employee_id=subordinate_emp_id,
    )

    with pytest.raises(HTTPException) as exc:
        await record_punch(mock_session, tenant_id, user_id, "manager", payload)

    assert exc.value.status_code == 403
    assert "only record punches for themselves" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_admin_can_punch_for_employee():
    """Verify admin role with MANAGE_ATTENDANCE can record punch on behalf of an employee."""
    tenant_id = uuid.uuid4()
    admin_user_id = uuid.uuid4()
    target_emp_id = uuid.uuid4()
    mock_session = AsyncMock()

    target_emp = _create_mock_employee(tenant_id, employee_id=target_emp_id)

    # 1. user_emp query -> None (admin might not have employee profile)
    res_user_emp = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    # 2. lock target emp -> returns target_emp
    res_lock_emp = MagicMock(scalar_one_or_none=MagicMock(return_value=target_emp))
    # 3. idempotency -> None
    res_idem = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    # 4. latest event -> None
    res_latest = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

    mock_session.execute.side_effect = [res_user_emp, res_lock_emp, res_idem, res_latest]

    payload = PunchRequest(
        event_type="CHECK_IN",
        idempotency_key="admin-punch-for-emp",
        employee_id=target_emp_id,
    )

    resp = await record_punch(mock_session, tenant_id, admin_user_id, "admin", payload)

    assert resp.event.employee_id == target_emp_id
    assert mock_session.commit.called


# ==============================================================================
# 7. Event Listing & Single Event Retrieval Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_get_attendance_event_success_and_forbidden():
    """Verify single event retrieval succeeds for owner/admin and is forbidden if employee views another's event."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    other_emp_id = uuid.uuid4()
    mock_session = AsyncMock()

    event = _create_mock_event(tenant_id, emp_id)

    # 1. As Admin: succeeds directly
    mock_session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=event))
    retrieved = await get_attendance_event(mock_session, tenant_id, user_id, "admin", event.id)
    assert retrieved.id == event.id

    # 2. As Employee matching event employee_id: succeeds
    res_event = MagicMock(scalar_one_or_none=MagicMock(return_value=event))
    res_emp = MagicMock(scalar_one_or_none=MagicMock(return_value=emp_id))
    mock_session.execute.side_effect = [res_event, res_emp]
    retrieved_emp = await get_attendance_event(
        mock_session, tenant_id, user_id, "employee", event.id
    )
    assert retrieved_emp.id == event.id

    # 3. As Employee attempting to view other employee's event: raises 403
    res_event2 = MagicMock(scalar_one_or_none=MagicMock(return_value=event))
    res_emp2 = MagicMock(scalar_one_or_none=MagicMock(return_value=other_emp_id))
    mock_session.execute.side_effect = [res_event2, res_emp2]
    with pytest.raises(HTTPException) as exc:
        await get_attendance_event(mock_session, tenant_id, user_id, "employee", event.id)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_list_attendance_events_employee_scoped():
    """Verify employee listing attendance events is strictly constrained to their own employee ID."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    mock_session = AsyncMock()

    # Mock user employee lookup
    res_emp = MagicMock(scalar_one_or_none=MagicMock(return_value=emp_id))
    # Mock count
    res_count = MagicMock(scalar_one=MagicMock(return_value=1))
    # Mock rows
    event = _create_mock_event(tenant_id, emp_id)
    res_rows = MagicMock()
    res_rows.scalars.return_value.all.return_value = [event]

    mock_session.execute.side_effect = [res_emp, res_count, res_rows]

    resp = await list_attendance_events(mock_session, tenant_id, user_id, "employee")

    assert resp.total == 1
    assert len(resp.items) == 1
    assert resp.items[0].employee_id == emp_id


# ==============================================================================
# 8. Append-Only Trigger & Database Integrity Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_concurrent_duplicate_punch_integrity_error_handled():
    """Verify concurrent duplicate punch resulting in unique constraint violation raises HTTP 409."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    mock_session = AsyncMock()

    emp = _create_mock_employee(tenant_id, employee_id=emp_id, user_id=user_id)
    mock_session.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
    ]

    # Commit raises unique constraint violation
    mock_session.commit.side_effect = IntegrityError(
        statement="INSERT INTO attendance_events...",
        params={},
        orig=Exception(
            "duplicate key value violates unique constraint 'uq_attendance_events_tenant_idempotency'"
        ),
    )

    payload = PunchRequest(event_type="CHECK_IN", idempotency_key="key-concurrent-race")
    with pytest.raises(HTTPException) as exc:
        await record_punch(mock_session, tenant_id, user_id, "employee", payload)

    assert exc.value.status_code == 409
    assert "concurrent duplicate" in exc.value.detail.lower()
    assert mock_session.rollback.called


@pytest.mark.asyncio
async def test_location_validation_not_found():
    """Verify specifying a non-existent location_id raises HTTP 404."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    mock_session = AsyncMock()

    emp = _create_mock_employee(tenant_id, employee_id=emp_id, user_id=user_id)
    # 1. user_emp -> emp
    # 2. lock emp -> emp
    # 3. location check -> None (not found)
    mock_session.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
    ]

    payload = PunchRequest(
        event_type="CHECK_IN",
        idempotency_key="punch-loc-test",
        location_id=uuid.uuid4(),
    )

    with pytest.raises(HTTPException) as exc:
        await record_punch(mock_session, tenant_id, user_id, "employee", payload)

    assert exc.value.status_code == 404
    assert "location not found" in exc.value.detail.lower()


# ==============================================================================
# 9. HTTP API Integration Tests (AsyncClient)
# ==============================================================================


@pytest.mark.asyncio
async def test_api_punch_unauthenticated_returns_401():
    """Verify calling /api/v1/attendance/punch without JWT returns 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/attendance/punch",
            json={"event_type": "CHECK_IN", "idempotency_key": "12345678"},
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_punch_endpoint_success():
    """Verify POST /api/v1/attendance/punch with authenticated employee returns 201."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    mock_ctx = _mock_context("employee", tenant_id=tenant_id, user_id=user_id)
    emp = _create_mock_employee(tenant_id, employee_id=emp_id, user_id=user_id)

    mock_db = AsyncMock()
    mock_db.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),  # user_emp
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),  # lock emp
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # idempotency check
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # latest event
    ]

    app.dependency_overrides[get_authenticated_context] = lambda: mock_ctx
    app.dependency_overrides[get_db] = lambda: mock_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "event_type": "CHECK_IN",
            "idempotency_key": "api-test-punch-001",
        }
        resp = await client.post("/api/v1/attendance/punch", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["event"]["event_type"] == "CHECK_IN"
        assert data["idempotent_replay"] is False


@pytest.mark.asyncio
async def test_api_get_attendance_events_endpoint():
    """Verify GET /api/v1/attendance/events returns 200 with list response."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    mock_ctx = _mock_context("employee", tenant_id=tenant_id, user_id=user_id)
    event = _create_mock_event(tenant_id, emp_id)

    mock_db = AsyncMock()
    mock_db.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp_id)),  # user_emp
        MagicMock(scalar_one=MagicMock(return_value=1)),  # count
        MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[event])))
        ),  # rows
    ]

    app.dependency_overrides[get_authenticated_context] = lambda: mock_ctx
    app.dependency_overrides[get_db] = lambda: mock_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/attendance/events")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_get_single_attendance_event_endpoint():
    """Verify GET /api/v1/attendance/events/{id} returns 200 with single event."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    mock_ctx = _mock_context("admin", tenant_id=tenant_id, user_id=user_id)
    event = _create_mock_event(tenant_id, emp_id)

    mock_db = AsyncMock()
    mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=event))

    app.dependency_overrides[get_authenticated_context] = lambda: mock_ctx
    app.dependency_overrides[get_db] = lambda: mock_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/v1/attendance/events/{event.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(event.id)
        assert data["event_type"] == event.event_type

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cross_tenant_punch_isolation():
    """Verify employee from Tenant A cannot punch in Tenant B's context (returns 404/400)."""
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    user_id = uuid.uuid4()
    emp_a_id = uuid.uuid4()
    _ = _create_mock_employee(tenant_a, employee_id=emp_a_id)

    mock_session = AsyncMock()
    # Looking for user's employee in Tenant B returns None because employee is in Tenant A
    mock_session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

    payload = PunchRequest(
        event_type="CHECK_IN",
        idempotency_key="cross-tenant-key-1",
        employee_id=emp_a_id,
    )

    # In Tenant B's context, target employee doesn't exist
    with pytest.raises(HTTPException) as exc:
        await record_punch(mock_session, tenant_b, user_id, "admin", payload)

    assert exc.value.status_code == 404
    assert "not found" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_cross_tenant_event_view_isolation():
    """Verify Tenant B cannot view Tenant A's attendance event (returns 404)."""
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    user_id = uuid.uuid4()
    event_in_tenant_a = _create_mock_event(tenant_a, uuid.uuid4())
    event_id = event_in_tenant_a.id

    mock_session = AsyncMock()
    # Query with Tenant B returns None because row has tenant_id = tenant_a
    mock_session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

    with pytest.raises(HTTPException) as exc:
        await get_attendance_event(mock_session, tenant_b, user_id, "admin", event_id)

    assert exc.value.status_code == 404
    assert "not found" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_append_only_ledger_immutability_trigger_behavior():
    """Verify attendance_events rejects UPDATE and DELETE operations."""
    # Read the migration trigger function to assert SQL immutability error code
    import inspect

    from database.migrations.versions.f1b94c8e7a23_phase_05_attendance_events_and_idempotency import (
        upgrade,
    )

    source = inspect.getsource(upgrade)
    assert "trg_attendance_events_immutability" in source
    assert "trg_prevent_attendance_events_mutation" in source
    assert "integrity_constraint_violation" in source
    assert "BEFORE UPDATE OR DELETE ON attendance_events" in source
    assert "GRANT SELECT, INSERT ON attendance_events TO authenticated, service_role;" in source
    assert "UPDATE" not in source.split("GRANT")[1].split("ON attendance_events")[0]


@pytest.mark.asyncio
async def test_completed_idempotency_record_permanently_retained():
    """Verify that completing a punch sets expires_at to None for permanent retention."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    mock_session = AsyncMock()

    emp = _create_mock_employee(tenant_id, employee_id=emp_id, user_id=user_id)
    # 1. user_emp -> emp
    # 2. lock emp -> emp
    # 3. idem record -> None
    # 4. latest event -> None (CHECKED_OUT)
    mock_session.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
    ]

    added_objects: list[object] = []
    mock_session.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))

    payload = PunchRequest(event_type="CHECK_IN", idempotency_key="key-permanent-audit-1")
    resp = await record_punch(mock_session, tenant_id, user_id, "employee", payload)

    assert resp.event.event_type == "CHECK_IN"
    assert resp.idempotent_replay is False

    # Find the created AttendanceIdempotencyRecord
    idem_records = [o for o in added_objects if isinstance(o, AttendanceIdempotencyRecord)]
    assert len(idem_records) == 1
    record = idem_records[0]
    assert record.status == "COMPLETED"
    assert record.expires_at is None, (
        "Completed idempotency records must have expires_at=None for permanent retention"
    )


@pytest.mark.asyncio
async def test_retry_after_24_hours_returns_original_event_as_idempotent_replay():
    """Verify that retrying a punch after 24 hours returns the cached event with idempotent_replay=True."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    event_id = uuid.uuid4()
    mock_session = AsyncMock()

    emp = _create_mock_employee(tenant_id, employee_id=emp_id, user_id=user_id)
    cached_payload = {
        "event": {
            "id": str(event_id),
            "tenant_id": str(tenant_id),
            "employee_id": str(emp_id),
            "event_type": "CHECK_IN",
            "event_category": "STANDARD",
            "server_received_at": datetime.now(UTC).isoformat(),
            "effective_at": datetime.now(UTC).isoformat(),
            "source": "WEB",
            "review_status": "NOT_REQUIRED",
            "timestamp_verification_status": "SERVER_AUTHORITATIVE",
            "idempotency_key": "key-24h-retry",
            "created_at": datetime.now(UTC).isoformat(),
        },
        "additional_events": [],
        "idempotent_replay": False,
    }

    # Simulate an idempotency record created 48 hours ago with expires_at=None
    created_2_days_ago = datetime.now(UTC) - timedelta(days=2)
    punch_request = PunchRequest(event_type="CHECK_IN", idempotency_key="key-24h-retry")
    fingerprint = compute_request_fingerprint(punch_request, emp_id)

    historical_record = AttendanceIdempotencyRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp_id,
        idempotency_key="key-24h-retry",
        request_fingerprint=fingerprint,
        status="COMPLETED",
        response_code=201,
        response_payload=cached_payload,
        event_id=event_id,
        created_at=created_2_days_ago,
        expires_at=None,
    )

    # 1. user_emp -> emp
    # 2. lock emp -> emp
    # 3. idem record -> historical_record
    mock_session.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=historical_record)),
    ]

    resp = await record_punch(mock_session, tenant_id, user_id, "employee", punch_request)
    assert resp.event.id == event_id
    assert resp.idempotent_replay is True
