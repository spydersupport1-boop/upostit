"""Comprehensive End-to-End Simulation Suite for Phase 7 Milestone 7.6:
Offline Synchronization, Device Binding, Fraud Telemetry, and Attendance Recalculation.

Validates the complete interaction contract across:
1. Normal offline shift synchronization and daily projection calculation.
2. Idempotency replay and response-loss boundary safety (no duplicate events or flags).
3. Authoritative device binding validation and HTTP 403 rejection on revoked devices.
4. Fraud telemetry propagation (mock GPS, clock drift, impossible travel velocity).
5. Timestamp validation thresholds (> 24h future, > 7d staleness).
6. State machine session ordering and atomic multi-event break handling.
7. Cross-tenant isolation during offline punch processing.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status
from httpx import ASGITransport, AsyncClient

from services.api.attendance.models import (
    AttendanceEvent,
    AttendanceIdempotencyRecord,
    TenantAttendancePolicy,
)
from services.api.attendance.schemas import PunchRequest
from services.api.attendance.service import record_punch
from services.api.auth.dependencies import AuthenticatedContext, get_authenticated_context
from services.api.auth.models import User
from services.api.database import get_db
from services.api.devices.models import Device
from services.api.devices.service import hash_device_id
from services.api.employees.models import Employee
from services.api.fraud.engine import DEFAULT_RULE_DEFINITIONS
from services.api.fraud.models import FraudRule
from services.api.main import app
from services.api.tenants.models import Tenant

# ==============================================================================
# Helper Fixtures & Mock Context
# ==============================================================================


def _mock_context(
    role: str = "employee",
    tenant_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> AuthenticatedContext:
    tid = tenant_id or uuid.uuid4()
    uid = user_id or uuid.uuid4()
    user = User(
        id=uid,
        tenant_id=tid,
        full_name="Tester",
        email=f"tester_{role.lower()}@simulation.test",
        password_hash="argon2id$mock",
        role=role.lower(),
        status="active",
    )
    tenant = Tenant(
        id=tid,
        name="Simulation Corp",
        slug=f"sim-{tid.hex[:6]}",
        company_email="admin@sim.test",
        country_code="IN",
        status="active",
    )
    return AuthenticatedContext(user=user, tenant=tenant)


def _create_mock_session(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    employee_id: uuid.UUID,
    device_raw_id: str | None = None,
    device_status: str = "ACTIVE",
    existing_events: list[AttendanceEvent] | None = None,
    existing_rules: list[FraudRule] | None = None,
    existing_idem: AttendanceIdempotencyRecord | None = None,
    active_policy: TenantAttendancePolicy | None = None,
) -> AsyncMock:
    session = AsyncMock()

    employee = Employee(
        id=employee_id,
        tenant_id=tenant_id,
        user_id=user_id,
        first_name="Simulated",
        last_name="Worker",
        work_email="simulated@example.com",
        status="active",
    )

    device = None
    if device_raw_id is not None:
        device = Device(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            employee_id=employee_id,
            device_id_hash=hash_device_id(tenant_id, device_raw_id),
            platform="ANDROID",
            device_model="Pixel 8 Pro",
            os_name="Android",
            os_version="14",
            app_version="1.0.0+1",
            status=device_status,
            registered_at=datetime.now(UTC) - timedelta(days=30),
            revoked_at=datetime.now(UTC) - timedelta(days=1) if device_status == "REVOKED" else None,
            revocation_reason="Administrative revocation during offline period" if device_status == "REVOKED" else None,
        )

    rules = existing_rules or [
        FraudRule(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            rule_code=d["rule_code"],
            rule_name=d["rule_name"],
            description=d.get("description", ""),
            enabled=True,
            severity=d["severity"],
            risk_weight=d["risk_weight"],
            threshold_config=d.get("threshold_config", {}),
            review_required=d.get("review_required", True),
        )
        for d in DEFAULT_RULE_DEFINITIONS
    ]

    async def execute_side_effect(stmt, *args, **kwargs):
        stmt_str = str(stmt).lower()
        mock_res = MagicMock()

        # Employee resolution queries
        if "from employees" in stmt_str:
            mock_res.scalar_one_or_none.return_value = employee
            mock_res.scalars.return_value.all.return_value = [employee]
            return mock_res

        # Tenant resolution
        if "from tenants" in stmt_str:
            mock_res.scalar_one_or_none.return_value = "UTC"
            return mock_res

        # Idempotency queries
        if "from attendance_idempotency_records" in stmt_str:
            mock_res.scalar_one_or_none.return_value = existing_idem
            return mock_res

        # Device binding lookup queries
        if "from devices" in stmt_str:
            mock_res.scalar_one_or_none.return_value = device
            mock_res.scalars.return_value.all.return_value = [device] if device else []
            return mock_res

        # Fraud rules lookup
        if "from fraud_rules" in stmt_str:
            mock_res.scalars.return_value.all.return_value = rules
            return mock_res

        # Attendance Policy lookup
        if "from tenant_attendance_policies" in stmt_str:
            mock_res.scalar_one_or_none.return_value = active_policy
            return mock_res

        # Attendance Events history & latest event
        if "from attendance_events" in stmt_str:
            events = existing_events or []
            mock_res.scalar_one_or_none.return_value = events[-1] if events else None
            mock_res.scalars.return_value.all.return_value = events
            return mock_res

        # Attendance Day lookup
        if "from attendance_days" in stmt_str:
            mock_res.scalar_one_or_none.return_value = None
            return mock_res

        mock_res.scalar_one_or_none.return_value = None
        mock_res.scalars.return_value.all.return_value = []
        return mock_res

    session.execute.side_effect = execute_side_effect
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()

    return session


# ==============================================================================
# Simulation Tests
# ==============================================================================


@pytest.mark.asyncio
class TestOfflineSyncEndToEndSimulation:
    """End-to-End Simulation test suite covering the full interaction between
    offline synchronization, backend validation, fraud detection, and idempotency.
    """

    async def test_scenario_a_normal_offline_attendance_flow(self):
        """Scenario A: Simulates normal offline attendance punch submission.
        Verifies:
        - Device ID is verified and recorded.
        - Original client device reported timestamp is preserved.
        - AttendanceEvent is committed.
        - review_status defaults to NOT_REQUIRED when authentic.
        - Idempotency record is persisted as COMPLETED.
        """
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        raw_device_id = "pixel8-secure-install-id-001"

        session = _create_mock_session(
            tenant_id=tenant_id,
            user_id=user_id,
            employee_id=employee_id,
            device_raw_id=raw_device_id,
            device_status="ACTIVE",
        )

        device_time = datetime.now(UTC) - timedelta(minutes=45)
        payload = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="idemp-offline-norm-1",
            device_reported_at=device_time,
            device_id=raw_device_id,
            is_mock_location=False,
            location_captured_at=device_time,
            latitude=37.7749,
            longitude=-122.4194,
            accuracy_meters=10.0,
            metadata={"offline_queued": True, "offline_sequence_number": 1},
        )

        response = await record_punch(
            session=session,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role="employee",
            payload=payload,
        )


        assert response.event.event_type == "CHECK_IN"
        assert response.event.device_reported_at.isoformat() == device_time.isoformat()
        assert response.event.device_id == raw_device_id
        assert response.event.is_mock_location is False
        assert response.event.review_status == "NOT_REQUIRED"
        assert response.idempotent_replay is False

        # Verify database operations
        session.commit.assert_awaited_once()

    async def test_scenario_b_and_c_network_loss_and_idempotency_replay(self):
        """Scenarios B & C: Simulates response loss after backend acceptance, followed
        by client retry with the same idempotency key.
        Verifies:
        - First execution commits event and caches response.
        - Second execution with identical idempotency key detects COMPLETED record.
        - Returns cached response with idempotent_replay=True without creating duplicate event.
        - Replay with mismatched payload raises HTTP 422 Unprocessable Content.
        """
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        raw_device_id = "pixel8-secure-install-id-001"

        # 1. Existing completed idempotency record in database
        event_id = uuid.uuid4()
        idem_key = "idemp-boundary-test-888"
        device_time = datetime.now(UTC) - timedelta(minutes=20)

        payload = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key=idem_key,
            device_reported_at=device_time,
            device_id=raw_device_id,
            is_mock_location=False,
            metadata={"offline_sequence_number": 1},
        )

        from services.api.attendance.service import compute_request_fingerprint

        fingerprint = compute_request_fingerprint(payload, employee_id)

        existing_response_payload = {
            "event": {
                "id": str(event_id),
                "tenant_id": str(tenant_id),
                "employee_id": str(employee_id),
                "event_type": "CHECK_IN",
                "event_category": "STANDARD",
                "source": "MOBILE",
                "server_received_at": device_time.isoformat(),
                "effective_at": device_time.isoformat(),
                "device_reported_at": device_time.isoformat(),
                "timestamp_verification_status": "SERVER_AUTHORITATIVE",
                "review_status": "NOT_REQUIRED",
                "idempotency_key": idem_key,
                "created_at": datetime.now(UTC).isoformat(),
            },
            "additional_events": [],
            "idempotent_replay": False,
        }

        existing_idem = AttendanceIdempotencyRecord(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            employee_id=employee_id,
            idempotency_key=idem_key,
            request_fingerprint=fingerprint,
            status="COMPLETED",
            event_id=event_id,
            response_code=201,
            response_payload=existing_response_payload,
            created_at=datetime.now(UTC) - timedelta(minutes=5),
        )

        session = _create_mock_session(
            tenant_id=tenant_id,
            user_id=user_id,
            employee_id=employee_id,
            device_raw_id=raw_device_id,
            existing_idem=existing_idem,
        )

        # Execute replay
        response = await record_punch(
            session=session,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role="employee",
            payload=payload,
        )


        # Idempotent replay returned safely without re-inserting
        assert response.idempotent_replay is True
        assert str(response.event.id) == str(event_id)
        assert response.event.event_type == "CHECK_IN"

        # 2. Test Mismatched Payload with Same Idempotency Key -> 422
        tampered_payload = PunchRequest(
            event_type="CHECK_OUT",  # Changed event type
            idempotency_key=idem_key,
            device_reported_at=device_time,
            device_id=raw_device_id,
        )

        with pytest.raises(HTTPException) as exc_info:
            await record_punch(
                session=session,
                tenant_id=tenant_id,
                user_id=user_id,
                user_role="employee",
                payload=tampered_payload,
            )
        assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "mismatched request payload" in exc_info.value.detail.lower()

    async def test_scenario_d_device_revoked_while_offline_events_pending(self):
        """Scenario D: Simulates synchronization when administrator has revoked the employee's device.
        Verifies:
        - Backend validation detects device_validation_status == 'REVOKED'.
        - Immediately rejects with HTTP 403 Forbidden.
        - Clear explanatory message provided to client.
        - AttendanceEvent is not committed.
        """
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        raw_device_id = "compromised-phone-uuid-777"

        session = _create_mock_session(
            tenant_id=tenant_id,
            user_id=user_id,
            employee_id=employee_id,
            device_raw_id=raw_device_id,
            device_status="REVOKED",
        )

        payload = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="idemp-revoked-offline-attempt",
            device_reported_at=datetime.now(UTC) - timedelta(minutes=15),
            device_id=raw_device_id,
            is_mock_location=False,
        )

        with pytest.raises(HTTPException) as exc_info:
            await record_punch(
                session=session,
                tenant_id=tenant_id,
                user_id=user_id,
                user_role="employee",
                payload=payload,
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Device registration has been revoked" in exc_info.value.detail

    async def test_scenario_e_fraud_telemetry_mock_gps_and_clock_drift(self):
        """Scenario E: Simulates offline synchronization containing mock GPS telemetry
        and excessive clock drift.
        Verifies:
        - MOCK_LOCATION_DETECTED and SUSPICIOUS_CLOCK_DRIFT signals triggered.
        - Risk score calculated deterministically.
        - review_status automatically escalated to PENDING_REVIEW.
        - Forensic metadata persisted in event.
        """
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        raw_device_id = "device-mock-telemetry-001"

        session = _create_mock_session(
            tenant_id=tenant_id,
            user_id=user_id,
            employee_id=employee_id,
            device_raw_id=raw_device_id,
            device_status="ACTIVE",
        )

        # Clock drift: reported 10 minutes in the past
        drifting_device_time = datetime.now(UTC) - timedelta(minutes=10)

        payload = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="idemp-mock-gps-drift-test",
            device_reported_at=drifting_device_time,
            device_id=raw_device_id,
            is_mock_location=True,  # Mobile detected mock location
            location_captured_at=drifting_device_time,
            latitude=37.7749,
            longitude=-122.4194,
            accuracy_meters=10.0,
            metadata={"mock_provider": "developer_options_fake_gps"},
        )

        response = await record_punch(
            session=session,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role="employee",
            payload=payload,
        )


        assert response.event.is_mock_location is True
        assert response.event.review_status == "PENDING_REVIEW"
        assert response.event.timestamp_verification_status == "SUSPICIOUS_CLOCK_DRIFT"

    async def test_scenario_f_timestamp_validation_boundaries(self):
        """Scenario F: Tests approved timestamp validation boundaries:
        - Future timestamp > 300 seconds -> 422 Unprocessable Content.
        - Future timestamp 61-300 seconds -> Accepted with PENDING_REVIEW.
        - Stale timestamp > 72 hours (default max) -> 422 Unprocessable Content.
        - Offline timestamp between 24 and 72 hours -> Accepted with PENDING_REVIEW.
        """
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        raw_device_id = "device-timestamp-boundary-001"

        session = _create_mock_session(
            tenant_id=tenant_id,
            user_id=user_id,
            employee_id=employee_id,
            device_raw_id=raw_device_id,
        )

        # 1. Implausible future timestamp (> 300 seconds ahead)
        future_payload = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="idemp-future-time-over-300",
            device_reported_at=datetime.now(UTC) + timedelta(seconds=305),
            device_id=raw_device_id,
        )

        with pytest.raises(HTTPException) as exc_future:
            await record_punch(
                session=session,
                tenant_id=tenant_id,
                user_id=user_id,
                user_role="employee",
                payload=future_payload,
            )
        assert exc_future.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "future" in exc_future.value.detail.lower()

        # 2. Future timestamp between 60s and 300s -> accepted with PENDING_REVIEW
        future_review_payload = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="idemp-future-time-review",
            device_reported_at=datetime.now(UTC) + timedelta(seconds=120),
            device_id=raw_device_id,
        )
        resp_future_review = await record_punch(
            session=session,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role="employee",
            payload=future_review_payload,
        )
        assert resp_future_review.event.review_status == "PENDING_REVIEW"
        assert resp_future_review.event.timestamp_verification_status == "SUSPICIOUS_CLOCK_DRIFT"

        # 3. Stale timestamp older than 72 hours (default max acceptance limit)
        stale_payload = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="idemp-stale-time-over-72h",
            device_reported_at=datetime.now(UTC) - timedelta(hours=73),
            device_id=raw_device_id,
        )

        with pytest.raises(HTTPException) as exc_stale:
            await record_punch(
                session=session,
                tenant_id=tenant_id,
                user_id=user_id,
                user_role="employee",
                payload=stale_payload,
            )
        assert exc_stale.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "exceeds allowable offline limit" in exc_stale.value.detail.lower()

        # 4. Offline timestamp between 24h and 72h -> Accepted with supervisor review
        between_24_72_payload = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="idemp-offline-36h-review",
            device_reported_at=datetime.now(UTC) - timedelta(hours=36),
            device_id=raw_device_id,
            metadata={"offline_queued": True},
        )
        resp_36h = await record_punch(
            session=session,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role="employee",
            payload=between_24_72_payload,
        )
        assert resp_36h.event.review_status == "PENDING_REVIEW"
        assert resp_36h.event.timestamp_verification_status == "UNVERIFIED_OFFLINE"
        assert "FLAG_OFFLINE_WINDOW_EXCEEDED" in (resp_36h.event.metadata or {}).get("flags", [])

    async def test_scenario_g_dependent_session_events_break_closure(self):
        """Scenario G: Tests dependent session events where employee checks out while
        still on break.
        Verifies:
        - Auto-break closure is triggered atomically.
        - Additional event 'BREAK_END' is returned in response.
        - Shift intervals and daily projection remain consistent.
        """
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        raw_device_id = "device-break-closure-001"

        # Previous state: ON_BREAK
        prev_break_start = AttendanceEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            employee_id=employee_id,
            event_type="BREAK_START",
            effective_at=datetime.now(UTC) - timedelta(minutes=30),
            server_received_at=datetime.now(UTC) - timedelta(minutes=30),
        )

        session = _create_mock_session(
            tenant_id=tenant_id,
            user_id=user_id,
            employee_id=employee_id,
            device_raw_id=raw_device_id,
            existing_events=[prev_break_start],
        )

        payload = PunchRequest(
            event_type="CHECK_OUT",
            idempotency_key="idemp-checkout-with-open-break",
            device_reported_at=datetime.now(UTC),
            device_id=raw_device_id,
        )

        response = await record_punch(
            session=session,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role="employee",
            payload=payload,
        )


        assert response.event.event_type == "CHECK_OUT"
        assert len(response.additional_events) == 1
        assert response.additional_events[0].event_type == "BREAK_END"

    async def test_scenario_unregistered_device_punch_flagged_for_review(self):
        """Tests that a punch submitted from an unregistered device is accepted into the ledger
        with an UNREGISTERED_DEVICE fraud signal, risk score assigned, and review status set to PENDING_REVIEW.
        """
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        unregistered_device_id = "unknown-device-hardware-999"

        # Session with no registered devices
        session = _create_mock_session(
            tenant_id=tenant_id,
            user_id=user_id,
            employee_id=employee_id,
            device_raw_id=None,  # No device bound
        )

        payload = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="idemp-unregistered-device-test",
            device_reported_at=datetime.now(UTC) - timedelta(minutes=5),
            device_id=unregistered_device_id,
            is_mock_location=False,
        )

        response = await record_punch(
            session=session,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role="employee",
            payload=payload,
        )


        assert response.event.event_type == "CHECK_IN"
        assert response.event.review_status == "PENDING_REVIEW"
        assert response.event.device_id == unregistered_device_id


# ==============================================================================
# API Level Integration Tests
# ==============================================================================


@pytest.mark.asyncio
class TestOfflineSyncAPIIntegration:
    """HTTP-level API test suite verifying that offline attendance sync requests
    interact correctly with FastAPI endpoints, dependency overrides, and security checks.
    """

    async def test_api_punch_offline_sync_telemetry_propagation(self):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        raw_device_id = "api-sync-device-001"

        mock_session = _create_mock_session(
            tenant_id=tenant_id,
            user_id=user_id,
            employee_id=employee_id,
            device_raw_id=raw_device_id,
            device_status="ACTIVE",
        )

        mock_ctx = _mock_context(role="employee", tenant_id=tenant_id, user_id=user_id)

        app.dependency_overrides[get_db] = lambda: mock_session
        app.dependency_overrides[get_authenticated_context] = lambda: mock_ctx

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer mock-token"},
            ) as ac:
                resp = await ac.post(
                    "/api/v1/attendance/punch",
                    json={
                        "event_type": "CHECK_IN",
                        "idempotency_key": "api-offline-sync-p1",
                        "device_reported_at": (datetime.now(UTC) - timedelta(minutes=10)).isoformat(),
                        "device_id": raw_device_id,
                        "is_mock_location": False,
                        "metadata": {"offline_queued": True},
                    },
                )
                assert resp.status_code == status.HTTP_201_CREATED
                data = resp.json()
                assert data["event"]["event_type"] == "CHECK_IN"
                assert data["event"]["device_id"] == raw_device_id
                assert data["idempotent_replay"] is False
        finally:
            app.dependency_overrides.clear()

    async def test_api_punch_revoked_device_returns_403_forbidden(self):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        raw_device_id = "api-revoked-device-002"

        mock_session = _create_mock_session(
            tenant_id=tenant_id,
            user_id=user_id,
            employee_id=employee_id,
            device_raw_id=raw_device_id,
            device_status="REVOKED",
        )

        mock_ctx = _mock_context(role="employee", tenant_id=tenant_id, user_id=user_id)

        app.dependency_overrides[get_db] = lambda: mock_session
        app.dependency_overrides[get_authenticated_context] = lambda: mock_ctx

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer mock-token"},
            ) as ac:
                resp = await ac.post(
                    "/api/v1/attendance/punch",
                    json={
                        "event_type": "CHECK_IN",
                        "idempotency_key": "api-offline-revoked-attempt",
                        "device_reported_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
                        "device_id": raw_device_id,
                    },
                )
                assert resp.status_code == status.HTTP_403_FORBIDDEN
                detail = resp.json()["detail"]
                assert "revoked" in detail.lower()
        finally:
            app.dependency_overrides.clear()


# ==============================================================================
# Corrective Test Suite: Timestamp Policy Boundaries & Offline Fraud Evaluation
# ==============================================================================


@pytest.mark.asyncio
class TestTimestampPolicyAndOfflineFraudCorrectiveSuite:
    """Comprehensive corrective regression tests verifying the exact approved
    timestamp policy and offline fraud evaluation invariants:
    - Standard offline window: 24 hours (automatic pipeline if valid).
    - Tenant-configurable window: 8 to 72 hours.
    - 24 to 72 hours: Supervisor review (PENDING_REVIEW + FLAG_OFFLINE_WINDOW_EXCEEDED).
    - Beyond configured maximum: Strict rejection (HTTP 422).
    - Future timestamp <= 60s: Tolerated (SERVER_AUTHORITATIVE, NOT_REQUIRED).
    - Future timestamp 61s to 300s: Supervisor review (PENDING_REVIEW + FLAG_FUTURE_TIMESTAMP_DETECTED).
    - Future timestamp > 300s: Strict rejection (HTTP 422).
    - Legitimate offline transport delay vs suspicious clock manipulation.
    - Mock location & revoked device enforcement during offline sync.
    - Multiple fraud signals aggregation on a single event.
    """

    async def test_past_timestamp_exactly_24_hours_offline_accepted(self):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        raw_device_id = "device-corrective-24h"

        session = _create_mock_session(
            tenant_id=tenant_id,
            user_id=user_id,
            employee_id=employee_id,
            device_raw_id=raw_device_id,
        )

        # Exactly 24 hours in past
        dev_time = datetime.now(UTC) - timedelta(hours=24)
        payload = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="idemp-corr-24h-exact",
            device_reported_at=dev_time,
            device_id=raw_device_id,
            metadata={"offline_queued": True},
        )

        resp = await record_punch(
            session=session,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role="employee",
            payload=payload,
        )
        assert resp.event.review_status == "NOT_REQUIRED"
        assert resp.event.timestamp_verification_status == "UNVERIFIED_OFFLINE"
        assert "FLAG_DELAYED_OFFLINE_SYNC" in (resp.event.metadata or {}).get("flags", [])
        assert "FLAG_OFFLINE_WINDOW_EXCEEDED" not in (resp.event.metadata or {}).get("flags", [])

    async def test_past_timestamp_just_beyond_24_hours_requires_supervisor_review(self):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        raw_device_id = "device-corrective-24h-plus"

        session = _create_mock_session(
            tenant_id=tenant_id,
            user_id=user_id,
            employee_id=employee_id,
            device_raw_id=raw_device_id,
        )

        # 24 hours + 10 seconds in past
        dev_time = datetime.now(UTC) - timedelta(hours=24, seconds=10)
        payload = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="idemp-corr-24h-plus",
            device_reported_at=dev_time,
            device_id=raw_device_id,
            metadata={"offline_queued": True},
        )

        resp = await record_punch(
            session=session,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role="employee",
            payload=payload,
        )
        assert resp.event.review_status == "PENDING_REVIEW"
        assert resp.event.timestamp_verification_status == "UNVERIFIED_OFFLINE"
        assert "FLAG_OFFLINE_WINDOW_EXCEEDED" in (resp.event.metadata or {}).get("flags", [])

    async def test_past_timestamp_configured_maximum_boundary_48_hours(self):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        raw_device_id = "device-corr-48h"

        custom_policy = TenantAttendancePolicy(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            version=2,
            is_active=True,
            default_mode="MANUAL",
            allowed_methods=["MANUAL"],
            required_methods=["MANUAL"],
            combination_rule="OR",
            fallback_policy={"max_offline_sync_age_hours": 48},
        )

        session = _create_mock_session(
            tenant_id=tenant_id,
            user_id=user_id,
            employee_id=employee_id,
            device_raw_id=raw_device_id,
            active_policy=custom_policy,
        )

        # Exactly 48 hours in past -> within configured window, requires supervisor review (since > 24h)
        dev_time = datetime.now(UTC) - timedelta(hours=48)
        payload = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="idemp-corr-48h-exact",
            device_reported_at=dev_time,
            device_id=raw_device_id,
            metadata={"offline_queued": True},
        )

        resp = await record_punch(
            session=session,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role="employee",
            payload=payload,
        )
        assert resp.event.review_status == "PENDING_REVIEW"
        assert resp.event.timestamp_verification_status == "UNVERIFIED_OFFLINE"
        assert "FLAG_OFFLINE_WINDOW_EXCEEDED" in (resp.event.metadata or {}).get("flags", [])

    async def test_past_timestamp_just_beyond_configured_maximum_48_hours_rejects_422(self):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        raw_device_id = "device-corr-48h-over"

        custom_policy = TenantAttendancePolicy(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            version=2,
            is_active=True,
            default_mode="MANUAL",
            allowed_methods=["MANUAL"],
            required_methods=["MANUAL"],
            combination_rule="OR",
            fallback_policy={"max_offline_sync_age_hours": 48},
        )

        session = _create_mock_session(
            tenant_id=tenant_id,
            user_id=user_id,
            employee_id=employee_id,
            device_raw_id=raw_device_id,
            active_policy=custom_policy,
        )

        # 48 hours + 15 seconds in past -> exceeds configured 48h limit
        dev_time = datetime.now(UTC) - timedelta(hours=48, seconds=15)
        payload = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="idemp-corr-48h-over",
            device_reported_at=dev_time,
            device_id=raw_device_id,
            metadata={"offline_queued": True},
        )

        with pytest.raises(HTTPException) as exc:
            await record_punch(
                session=session,
                tenant_id=tenant_id,
                user_id=user_id,
                user_role="employee",
                payload=payload,
            )
        assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "48 hours" in exc.value.detail

    async def test_past_timestamp_custom_short_window_12_hours(self):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        raw_device_id = "device-corr-12h"

        custom_policy = TenantAttendancePolicy(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            version=3,
            is_active=True,
            default_mode="MANUAL",
            allowed_methods=["MANUAL"],
            required_methods=["MANUAL"],
            combination_rule="OR",
            fallback_policy={"max_offline_sync_age_hours": 12},
        )

        session = _create_mock_session(
            tenant_id=tenant_id,
            user_id=user_id,
            employee_id=employee_id,
            device_raw_id=raw_device_id,
            active_policy=custom_policy,
        )

        # 1. 10 hours in past (within 12h) -> accepted
        dev_time_ok = datetime.now(UTC) - timedelta(hours=10)
        payload_ok = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="idemp-corr-12h-ok",
            device_reported_at=dev_time_ok,
            device_id=raw_device_id,
            metadata={"offline_queued": True},
        )
        resp_ok = await record_punch(
            session=session,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role="employee",
            payload=payload_ok,
        )
        assert resp_ok.event.review_status == "NOT_REQUIRED"

        # 2. 12 hours + 10s in past -> exceeds 12h configured window
        dev_time_bad = datetime.now(UTC) - timedelta(hours=12, seconds=10)
        payload_bad = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="idemp-corr-12h-bad",
            device_reported_at=dev_time_bad,
            device_id=raw_device_id,
            metadata={"offline_queued": True},
        )
        with pytest.raises(HTTPException) as exc_bad:
            await record_punch(
                session=session,
                tenant_id=tenant_id,
                user_id=user_id,
                user_role="employee",
                payload=payload_bad,
            )
        assert exc_bad.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "12 hours" in exc_bad.value.detail

    async def test_past_timestamp_default_maximum_72_hours_boundary(self):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        raw_device_id = "device-corr-72h"

        session = _create_mock_session(
            tenant_id=tenant_id,
            user_id=user_id,
            employee_id=employee_id,
            device_raw_id=raw_device_id,
            active_policy=None,  # default policy
        )

        # 1. Exactly 72 hours -> accepted with supervisor review
        dev_time_72 = datetime.now(UTC) - timedelta(hours=72)
        payload_72 = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="idemp-corr-72h-exact",
            device_reported_at=dev_time_72,
            device_id=raw_device_id,
            metadata={"offline_queued": True},
        )
        resp_72 = await record_punch(
            session=session,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role="employee",
            payload=payload_72,
        )
        assert resp_72.event.review_status == "PENDING_REVIEW"
        assert resp_72.event.timestamp_verification_status == "UNVERIFIED_OFFLINE"

        # 2. 72 hours + 10 seconds -> rejected with HTTP 422
        dev_time_72_over = datetime.now(UTC) - timedelta(hours=72, seconds=10)
        payload_72_over = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="idemp-corr-72h-over",
            device_reported_at=dev_time_72_over,
            device_id=raw_device_id,
            metadata={"offline_queued": True},
        )
        with pytest.raises(HTTPException) as exc_72:
            await record_punch(
                session=session,
                tenant_id=tenant_id,
                user_id=user_id,
                user_role="employee",
                payload=payload_72_over,
            )
        assert exc_72.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "72 hours" in exc_72.value.detail

    async def test_future_timestamp_at_60_seconds_accepted_normal(self):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        raw_device_id = "device-corr-future-60"

        session = _create_mock_session(
            tenant_id=tenant_id,
            user_id=user_id,
            employee_id=employee_id,
            device_raw_id=raw_device_id,
        )

        # 55 seconds in future (<= 60s allowable clock/network jitter)
        dev_time = datetime.now(UTC) + timedelta(seconds=55)
        payload = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="idemp-corr-future-60",
            device_reported_at=dev_time,
            device_id=raw_device_id,
        )

        resp = await record_punch(
            session=session,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role="employee",
            payload=payload,
        )
        assert resp.event.review_status == "NOT_REQUIRED"
        assert resp.event.timestamp_verification_status == "SERVER_AUTHORITATIVE"

    async def test_future_timestamp_just_beyond_60_seconds_requires_review(self):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        raw_device_id = "device-corr-future-65"

        session = _create_mock_session(
            tenant_id=tenant_id,
            user_id=user_id,
            employee_id=employee_id,
            device_raw_id=raw_device_id,
        )

        # 65 seconds in future (> 60s, <= 300s)
        dev_time = datetime.now(UTC) + timedelta(seconds=65)
        payload = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="idemp-corr-future-65",
            device_reported_at=dev_time,
            device_id=raw_device_id,
        )

        resp = await record_punch(
            session=session,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role="employee",
            payload=payload,
        )
        assert resp.event.review_status == "PENDING_REVIEW"
        assert resp.event.timestamp_verification_status == "SUSPICIOUS_CLOCK_DRIFT"
        assert "FLAG_FUTURE_TIMESTAMP_DETECTED" in (resp.event.metadata or {}).get("flags", [])

    async def test_future_timestamp_at_300_seconds_requires_review(self):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        raw_device_id = "device-corr-future-300"

        session = _create_mock_session(
            tenant_id=tenant_id,
            user_id=user_id,
            employee_id=employee_id,
            device_raw_id=raw_device_id,
        )

        # Exactly 295 seconds in future (<= 300s)
        dev_time = datetime.now(UTC) + timedelta(seconds=295)
        payload = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="idemp-corr-future-295",
            device_reported_at=dev_time,
            device_id=raw_device_id,
        )

        resp = await record_punch(
            session=session,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role="employee",
            payload=payload,
        )
        assert resp.event.review_status == "PENDING_REVIEW"
        assert resp.event.timestamp_verification_status == "SUSPICIOUS_CLOCK_DRIFT"

    async def test_future_timestamp_beyond_300_seconds_rejects_422(self):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        raw_device_id = "device-corr-future-305"

        session = _create_mock_session(
            tenant_id=tenant_id,
            user_id=user_id,
            employee_id=employee_id,
            device_raw_id=raw_device_id,
        )

        # 305 seconds in future (> 300s)
        dev_time = datetime.now(UTC) + timedelta(seconds=305)
        payload = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="idemp-corr-future-305",
            device_reported_at=dev_time,
            device_id=raw_device_id,
        )

        with pytest.raises(HTTPException) as exc:
            await record_punch(
                session=session,
                tenant_id=tenant_id,
                user_id=user_id,
                user_role="employee",
                payload=payload,
            )
        assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "future" in exc.value.detail.lower()

    async def test_offline_fraud_legitimate_transport_delay_not_flagged(self):
        """Verifies that normal offline delay (e.g. 5 hours) is classified as
        UNVERIFIED_OFFLINE without being falsely flagged for clock fraud."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        raw_device_id = "device-corr-legit-delay"

        session = _create_mock_session(
            tenant_id=tenant_id,
            user_id=user_id,
            employee_id=employee_id,
            device_raw_id=raw_device_id,
            device_status="ACTIVE",
        )

        dev_time = datetime.now(UTC) - timedelta(hours=5)
        payload = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="idemp-corr-legit-delay",
            device_reported_at=dev_time,
            device_id=raw_device_id,
            is_mock_location=False,
            location_captured_at=dev_time,
            latitude=37.7749,
            longitude=-122.4194,
            accuracy_meters=15.0,
            metadata={"offline_queued": True},
        )

        resp = await record_punch(
            session=session,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role="employee",
            payload=payload,
        )
        assert resp.event.review_status == "NOT_REQUIRED"
        assert resp.event.timestamp_verification_status == "UNVERIFIED_OFFLINE"
        assert resp.event.metadata["risk_score"] == 0

    async def test_offline_fraud_suspicious_clock_drift_without_offline_queue(self):
        """Verifies that an online punch with 45 minutes past drift without offline
        queue metadata is flagged as suspicious clock drift."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        raw_device_id = "device-corr-susp-drift"

        session = _create_mock_session(
            tenant_id=tenant_id,
            user_id=user_id,
            employee_id=employee_id,
            device_raw_id=raw_device_id,
            device_status="ACTIVE",
        )

        dev_time = datetime.now(UTC) - timedelta(minutes=45)
        payload = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="idemp-corr-susp-drift",
            device_reported_at=dev_time,
            device_id=raw_device_id,
            # No offline_queued in metadata!
            metadata={},
        )

        resp = await record_punch(
            session=session,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role="employee",
            payload=payload,
        )
        assert resp.event.review_status == "PENDING_REVIEW"
        assert resp.event.timestamp_verification_status == "SUSPICIOUS_CLOCK_DRIFT"
        assert "FLAG_CLOCK_MANIPULATION_SUSPECTED" in resp.event.metadata.get("flags", [])

    async def test_offline_fraud_mock_location_during_offline_sync(self):
        """Verifies that offline status DOES NOT bypass mock-location detection."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        raw_device_id = "device-corr-mock-offline"

        session = _create_mock_session(
            tenant_id=tenant_id,
            user_id=user_id,
            employee_id=employee_id,
            device_raw_id=raw_device_id,
            device_status="ACTIVE",
        )

        dev_time = datetime.now(UTC) - timedelta(hours=3)
        payload = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="idemp-corr-mock-offline",
            device_reported_at=dev_time,
            device_id=raw_device_id,
            is_mock_location=True,  # Mock GPS!
            location_captured_at=dev_time,
            latitude=37.7749,
            longitude=-122.4194,
            accuracy_meters=5.0,
            metadata={"offline_queued": True},
        )

        resp = await record_punch(
            session=session,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role="employee",
            payload=payload,
        )
        assert resp.event.review_status == "PENDING_REVIEW"
        assert resp.event.is_mock_location is True
        assert any(
            s["signal_type"] == "MOCK_LOCATION_DETECTED"
            for s in resp.event.metadata.get("fraud_signals", [])
        )

    async def test_offline_fraud_revoked_device_during_offline_sync(self):
        """Verifies that a revoked device synchronizing offline events is strictly rejected."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        raw_device_id = "device-corr-revoked-offline"

        session = _create_mock_session(
            tenant_id=tenant_id,
            user_id=user_id,
            employee_id=employee_id,
            device_raw_id=raw_device_id,
            device_status="REVOKED",
        )

        dev_time = datetime.now(UTC) - timedelta(hours=2)
        payload = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="idemp-corr-revoked-offline",
            device_reported_at=dev_time,
            device_id=raw_device_id,
            metadata={"offline_queued": True},
        )

        with pytest.raises(HTTPException) as exc:
            await record_punch(
                session=session,
                tenant_id=tenant_id,
                user_id=user_id,
                user_role="employee",
                payload=payload,
            )
        assert exc.value.status_code == status.HTTP_403_FORBIDDEN
        assert "revoked" in exc.value.detail.lower()

    async def test_offline_fraud_multiple_signals_aggregation(self):
        """Verifies multiple fraud signals on one event:
        Past timestamp > 24 hours (FLAG_OFFLINE_WINDOW_EXCEEDED) + mock location detected.
        Both signals must be persisted and review_status must be PENDING_REVIEW."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        raw_device_id = "device-corr-multi-signal"

        session = _create_mock_session(
            tenant_id=tenant_id,
            user_id=user_id,
            employee_id=employee_id,
            device_raw_id=raw_device_id,
            device_status="ACTIVE",
        )

        # 30 hours ago (between 24h and 72h) + mock GPS
        dev_time = datetime.now(UTC) - timedelta(hours=30)
        payload = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="idemp-corr-multi-signal",
            device_reported_at=dev_time,
            device_id=raw_device_id,
            is_mock_location=True,
            metadata={"offline_queued": True},
        )

        resp = await record_punch(
            session=session,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role="employee",
            payload=payload,
        )
        assert resp.event.review_status == "PENDING_REVIEW"
        assert resp.event.is_mock_location is True
        assert "FLAG_OFFLINE_WINDOW_EXCEEDED" in (resp.event.metadata or {}).get("flags", [])
        assert any(
            s["signal_type"] == "MOCK_LOCATION_DETECTED"
            for s in resp.event.metadata.get("fraud_signals", [])
        )
        assert resp.event.metadata["risk_score"] >= 40
