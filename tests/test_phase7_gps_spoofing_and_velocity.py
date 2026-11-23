"""Comprehensive test suite for Phase 7 Milestone 7.2:
GPS Spoofing Defense, Mock Location Telemetry, Clock Drift, and Velocity Analysis.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from services.api.attendance.models import AttendanceEvent, TenantAttendancePolicy
from services.api.attendance.schemas import PunchRequest
from services.api.attendance.service import record_punch
from services.api.auth.dependencies import AuthenticatedContext, get_authenticated_context
from services.api.auth.models import User
from services.api.database import get_db
from services.api.employees.models import Employee
from services.api.fraud.schemas import (
    FraudSignalSeverity,
    FraudSignalType,
)
from services.api.fraud.service import (
    calculate_punch_velocity,
    evaluate_clock_drift,
    evaluate_gps_evidence,
    get_previous_punch_with_coordinates,
    haversine_distance,
)
from services.api.main import app
from services.api.tenants.models import Tenant

# ==============================================================================
# Helper Mock Factories
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
        email=f"tester_{role.lower()}@upostit.test",
        password_hash="argon2id$mock",
        role=role.lower(),
        status="active",
    )
    tenant = Tenant(
        id=tid,
        name="Fraud Shield Corp",
        slug=f"fraud-{tid.hex[:6]}",
        company_email="admin@fraud.test",
        country_code="IN",
        status="active",
    )
    return AuthenticatedContext(user=user, tenant=tenant)


def _create_mock_employee(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> Employee:
    return Employee(
        id=employee_id or uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id or uuid.uuid4(),
        first_name="Bob",
        last_name="Tester",
        work_email="bob@fraud.test",
        status="active",
    )


def _create_mock_event(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    lat: float | None = 12.9716,
    lon: float | None = 77.5946,
    effective_at: datetime | None = None,
    event_id: uuid.UUID | None = None,
) -> AttendanceEvent:
    now = effective_at or datetime.now(UTC)
    return AttendanceEvent(
        id=event_id or uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=employee_id,
        event_type="CHECK_IN",
        event_category="STANDARD",
        server_received_at=now,
        device_reported_at=now,
        effective_at=now,
        clock_drift_seconds=Decimal("0.000"),
        source="MOBILE",
        device_id="device-mock-123",
        timestamp_verification_status="SERVER_AUTHORITATIVE",
        review_status="NOT_REQUIRED",
        idempotency_key=f"event-{uuid.uuid4()}",
        latitude=Decimal(str(lat)) if lat is not None else None,
        longitude=Decimal(str(lon)) if lon is not None else None,
        accuracy_meters=Decimal("15.0"),
        metadata_json={},
        created_at=now,
    )


# ==============================================================================
# Unit Tests: Haversine Distance & Velocity Calculation
# ==============================================================================


class TestHaversineAndVelocity:
    """Validates physical distance and travel velocity calculations."""

    def test_haversine_same_point(self):
        dist = haversine_distance(12.9716, 77.5946, 12.9716, 77.5946)
        assert dist == 0.0

    def test_haversine_known_distance(self):
        # Bangalore (12.9716, 77.5946) to Mysore (12.2958, 76.6394) is ~128 km
        dist = haversine_distance(12.9716, 77.5946, 12.2958, 76.6394)
        assert 120_000 < dist < 140_000

    def test_velocity_normal_commute(self):
        # 10 km in 30 minutes (1800s) -> ~5.55 m/s (~20 km/h)
        t1 = datetime(2026, 11, 19, 8, 0, 0, tzinfo=UTC)
        t2 = datetime(2026, 11, 19, 8, 30, 0, tzinfo=UTC)
        # Lat change ~0.09 deg ~= 10,000m
        lat1, lon1 = 12.9716, 77.5946
        lat2, lon2 = 13.0616, 77.5946

        res = calculate_punch_velocity(lat2, lon2, t2, lat1, lon1, t1)
        assert res.is_impossible is False
        assert res.velocity_mps < 10.0
        assert res.threshold_mps == 250.0

    def test_velocity_impossible_teleportation(self):
        # Bangalore to Mumbai (980 km) in 10 minutes (600s) -> ~1633 m/s (Mach 4.8)
        t1 = datetime(2026, 11, 19, 8, 0, 0, tzinfo=UTC)
        t2 = datetime(2026, 11, 19, 8, 10, 0, tzinfo=UTC)
        bangalore = (12.9716, 77.5946)
        mumbai = (19.0760, 72.8777)

        res = calculate_punch_velocity(mumbai[0], mumbai[1], t2, bangalore[0], bangalore[1], t1)
        assert res.is_impossible is True
        assert res.velocity_mps > 250.0
        assert res.velocity_mps > 1000.0

    def test_velocity_exact_threshold_boundary(self):
        # Exactly 250,000 meters in 1000 seconds = 250.0 m/s
        t1 = datetime(2026, 11, 19, 8, 0, 0, tzinfo=UTC)
        t2 = datetime(2026, 11, 19, 8, 16, 40, tzinfo=UTC)  # 1000s
        # 250 m/s is threshold; <= 250 is False, > 250 is True
        res = calculate_punch_velocity(12.9716, 77.5946, t2, 12.9716, 77.5946, t1)
        # zero distance -> 0 m/s
        assert res.is_impossible is False

    def test_velocity_zero_elapsed_seconds_same_location(self):
        t = datetime(2026, 11, 19, 8, 0, 0, tzinfo=UTC)
        res = calculate_punch_velocity(12.9716, 77.5946, t, 12.9716, 77.5946, t)
        assert res.is_impossible is False
        assert res.velocity_mps == 0.0

    def test_velocity_zero_elapsed_seconds_different_location(self):
        t = datetime(2026, 11, 19, 8, 0, 0, tzinfo=UTC)
        # Instant jump to different city with 0 elapsed seconds
        res = calculate_punch_velocity(13.5000, 78.0000, t, 12.9716, 77.5946, t)
        assert res.is_impossible is True
        assert res.velocity_mps == float("inf")


# ==============================================================================
# Unit Tests: Clock Drift Evaluation
# ==============================================================================


class TestClockDriftEvaluation:
    """Validates device clock drift thresholding and offline sync handling."""

    def test_no_device_time_returns_authoritative(self):
        now = datetime.now(UTC)
        res = evaluate_clock_drift(now, None)
        assert res.is_suspicious is False
        assert res.status == "SERVER_AUTHORITATIVE"
        assert res.drift_seconds == 0.0

    def test_clock_drift_within_threshold(self):
        server_now = datetime(2026, 11, 19, 8, 0, 0, tzinfo=UTC)
        device_time = datetime(2026, 11, 19, 8, 2, 0, tzinfo=UTC)  # 120s drift
        res = evaluate_clock_drift(server_now, device_time)
        assert res.is_suspicious is False
        assert res.drift_seconds == 120.0
        assert res.status == "SERVER_AUTHORITATIVE"

    def test_clock_drift_exactly_at_threshold(self):
        server_now = datetime(2026, 11, 19, 8, 5, 0, tzinfo=UTC)
        device_time = datetime(2026, 11, 19, 8, 0, 0, tzinfo=UTC)  # 300.0s drift
        res = evaluate_clock_drift(server_now, device_time)
        assert res.is_suspicious is False
        assert res.drift_seconds == 300.0
        assert res.status == "SERVER_AUTHORITATIVE"

    def test_clock_drift_exceeding_threshold_flagged(self):
        server_now = datetime(2026, 11, 19, 8, 6, 0, tzinfo=UTC)
        device_time = datetime(2026, 11, 19, 8, 0, 0, tzinfo=UTC)  # 360s drift
        res = evaluate_clock_drift(server_now, device_time)
        assert res.is_suspicious is True
        assert res.status == "SUSPICIOUS_CLOCK_DRIFT"
        assert res.drift_seconds == 360.0

    def test_offline_sync_delayed_upload_not_flagged_as_clock_fraud(self):
        # Offline punch captured at 08:00, uploaded 4 hours later at 12:00 due to network deadzone
        device_captured_at = datetime(2026, 11, 19, 8, 0, 0, tzinfo=UTC)
        server_uploaded_at = datetime(2026, 11, 19, 12, 0, 0, tzinfo=UTC)

        res = evaluate_clock_drift(server_uploaded_at, device_captured_at, is_offline_sync=True)
        assert res.is_suspicious is False
        assert res.status == "UNVERIFIED_OFFLINE"
        assert res.drift_seconds == 14400.0

    def test_offline_sync_future_timestamp_still_flagged(self):
        # Device clock was set into the future
        device_future = datetime(2026, 11, 19, 13, 0, 0, tzinfo=UTC)
        server_now = datetime(2026, 11, 19, 12, 0, 0, tzinfo=UTC)

        res = evaluate_clock_drift(server_now, device_future, is_offline_sync=True)
        assert res.is_suspicious is True
        assert res.status == "SUSPICIOUS_CLOCK_DRIFT"


# ==============================================================================
# Unit Tests: GPS Telemetry & Mock Detection
# ==============================================================================


class TestGpsTelemetryAndMockDetection:
    """Validates mock location detection, horizontal accuracy, and fix freshness."""

    def test_missing_coordinates(self):
        now = datetime.now(UTC)
        res, signals = evaluate_gps_evidence(
            latitude=None,
            longitude=None,
            accuracy_meters=None,
            location_captured_at=None,
            device_reported_at=None,
            server_received_at=now,
            is_mock_location=None,
        )
        assert res.status == "MISSING_COORDINATES"
        assert len(signals) == 0

    def test_mock_location_reported_generates_high_severity_signal(self):
        now = datetime.now(UTC)
        res, signals = evaluate_gps_evidence(
            latitude=12.9716,
            longitude=77.5946,
            accuracy_meters=10.0,
            location_captured_at=now,
            device_reported_at=now,
            server_received_at=now,
            is_mock_location=True,
        )
        assert res.is_mock_reported is True
        assert len(signals) == 1
        sig = signals[0]
        assert sig.signal_type == FraudSignalType.MOCK_LOCATION_DETECTED
        assert sig.severity == FraudSignalSeverity.HIGH
        assert sig.source == "GPS_TELEMETRY"

    def test_mock_location_false_or_none_safe(self):
        now = datetime.now(UTC)
        res, signals = evaluate_gps_evidence(
            latitude=12.9716,
            longitude=77.5946,
            accuracy_meters=10.0,
            location_captured_at=now,
            device_reported_at=now,
            server_received_at=now,
            is_mock_location=False,
        )
        assert res.is_mock_reported is False
        assert len(signals) == 0

    def test_accuracy_exceeding_100m_flagged(self):
        now = datetime.now(UTC)
        res, signals = evaluate_gps_evidence(
            latitude=12.9716,
            longitude=77.5946,
            accuracy_meters=150.0,
            location_captured_at=now,
            device_reported_at=now,
            server_received_at=now,
            is_mock_location=False,
        )
        assert res.is_poor_accuracy is True
        assert len(signals) == 1
        assert signals[0].signal_type == FraudSignalType.POOR_GPS_ACCURACY
        assert signals[0].severity == FraudSignalSeverity.LOW

    def test_stale_fix_older_than_30s_flagged(self):
        now = datetime.now(UTC)
        captured = now - timedelta(seconds=45)
        res, signals = evaluate_gps_evidence(
            latitude=12.9716,
            longitude=77.5946,
            accuracy_meters=15.0,
            location_captured_at=captured,
            device_reported_at=now,
            server_received_at=now,
            is_mock_location=False,
        )
        assert res.is_stale is True
        assert len(signals) == 1
        assert signals[0].signal_type == FraudSignalType.STALE_GPS_LOCATION
        assert signals[0].severity == FraudSignalSeverity.LOW


# ==============================================================================
# Unit Tests: Previous Punch Finder & Employee Isolation
# ==============================================================================


@pytest.mark.asyncio
class TestPreviousPunchFinder:
    """Validates chronological ordering and multi-tenant isolation in velocity evaluation."""

    async def test_finds_most_recent_punch_with_coordinates(self):
        tenant_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        t1 = datetime(2026, 11, 19, 8, 0, 0, tzinfo=UTC)
        event1 = _create_mock_event(tenant_id, emp_id, effective_at=t1)

        session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = event1
        session.execute.return_value = mock_res

        found = await get_previous_punch_with_coordinates(session, tenant_id, emp_id)
        assert found is not None
        assert found.id == event1.id

    async def test_does_not_find_event_from_different_tenant(self):
        tenant_a = uuid.uuid4()
        emp_id = uuid.uuid4()

        session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_res

        found = await get_previous_punch_with_coordinates(session, tenant_a, emp_id)
        assert found is None


# ==============================================================================
# Integration Tests: record_punch with Phase 7.2 Telemetry & Fraud Evaluation
# ==============================================================================


@pytest.mark.asyncio
class TestRecordPunchFraudIntegration:
    """Verifies that record_punch generates signals, flags PENDING_REVIEW, and preserves evidence."""

    async def test_mock_location_sets_review_status_pending_review(self):
        tenant_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        user_id = uuid.uuid4()
        emp = _create_mock_employee(tenant_id, emp_id, user_id)

        session = AsyncMock()
        # Mock Employee lookup
        mock_emp_res = MagicMock()
        mock_emp_res.scalar_one_or_none.return_value = emp

        # Mock Idempotency check -> None
        mock_idem = MagicMock()
        mock_idem.scalar_one_or_none.return_value = None

        # Mock Tenant policy -> MANUAL
        policy = TenantAttendancePolicy(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            version=1,
            is_active=True,
            default_mode="MANUAL",
            allowed_methods=["MANUAL"],
            required_methods=["MANUAL"],
            combination_rule="OR",
            gps_config={},
            wifi_config={},
            biometric_config={},
            face_config={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        mock_policy = MagicMock()
        mock_policy.scalar_one_or_none.return_value = policy

        # Mock previous punch with coordinates for velocity analysis -> None
        mock_prev_coord = MagicMock()
        mock_prev_coord.scalar_one_or_none.return_value = None

        # Mock latest event -> None (checked out)
        mock_latest = MagicMock()
        mock_latest.scalar_one_or_none.return_value = None

        # Mock timezone query
        mock_tz = MagicMock()
        mock_tz.scalar_one_or_none.return_value = "Asia/Kolkata"

        # Mock shift template query
        mock_shift = MagicMock()
        mock_shift.scalar_one_or_none.return_value = None

        # Mock attendance day query
        mock_day = MagicMock()
        mock_day.scalar_one_or_none.return_value = None

        session.execute.side_effect = [
            mock_emp_res,
            mock_emp_res,
            mock_idem,
            mock_policy,
            mock_prev_coord,
            mock_latest,
            mock_tz,
            mock_shift,
            mock_day,
        ]

        payload = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="idemp-mock-location-test-12345",
            latitude=Decimal("12.9716"),
            longitude=Decimal("77.5946"),
            accuracy_meters=Decimal("10.0"),
            is_mock_location=True,  # Mock GPS provider reported!
        )

        resp = await record_punch(
            session=session,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role="employee",
            payload=payload,
        )

        # Assert event preserved mock location and review status is PENDING_REVIEW
        assert resp.event.is_mock_location is True
        assert resp.event.review_status == "PENDING_REVIEW"
        assert "fraud_signals" in resp.event.metadata
        signals = resp.event.metadata["fraud_signals"]
        assert any(s["signal_type"] == "MOCK_LOCATION_DETECTED" for s in signals)

    async def test_clock_drift_sets_review_status_pending_review(self):
        tenant_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        user_id = uuid.uuid4()
        emp = _create_mock_employee(tenant_id, emp_id, user_id)

        session = AsyncMock()
        mock_emp_res = MagicMock()
        mock_emp_res.scalar_one_or_none.return_value = emp

        mock_idem = MagicMock()
        mock_idem.scalar_one_or_none.return_value = None

        policy = TenantAttendancePolicy(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            version=1,
            is_active=True,
            default_mode="MANUAL",
            allowed_methods=["MANUAL"],
            required_methods=["MANUAL"],
            combination_rule="OR",
            gps_config={},
            wifi_config={},
            biometric_config={},
            face_config={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        mock_policy = MagicMock()
        mock_policy.scalar_one_or_none.return_value = policy

        mock_latest = MagicMock()
        mock_latest.scalar_one_or_none.return_value = None

        mock_tz = MagicMock()
        mock_tz.scalar_one_or_none.return_value = "UTC"

        mock_shift = MagicMock()
        mock_shift.scalar_one_or_none.return_value = None

        mock_day = MagicMock()
        mock_day.scalar_one_or_none.return_value = None

        session.execute.side_effect = [
            mock_emp_res,
            mock_emp_res,
            mock_idem,
            mock_policy,
            mock_latest,
            mock_tz,
            mock_shift,
            mock_day,
        ]

        # Device reported timestamp is 10 minutes (600s) behind server time
        now_utc = datetime.now(UTC)
        past_time = now_utc - timedelta(minutes=10)

        payload = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="idemp-clock-drift-test-12345",
            device_reported_at=past_time,
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


# ==============================================================================
# End-to-End HTTP API Tests with FastAPI Client
# ==============================================================================


@pytest.mark.asyncio
class TestPunchAPIEndpointFraudTelemetry:
    """Verifies HTTP /api/v1/attendance/punch endpoint with mock GPS and velocity evidence."""

    async def test_punch_endpoint_accepts_is_mock_location(self):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        ctx = _mock_context("EMPLOYEE", tenant_id, user_id)
        emp = _create_mock_employee(tenant_id, emp_id, user_id)

        session = AsyncMock()
        mock_emp = MagicMock()
        mock_emp.scalar_one_or_none.return_value = emp
        mock_idem = MagicMock()
        mock_idem.scalar_one_or_none.return_value = None
        mock_policy = MagicMock()
        mock_policy.scalar_one_or_none.return_value = TenantAttendancePolicy(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            version=1,
            is_active=True,
            default_mode="MANUAL",
            allowed_methods=["MANUAL"],
            required_methods=["MANUAL"],
            combination_rule="OR",
            gps_config={},
            wifi_config={},
            biometric_config={},
            face_config={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        mock_prev = MagicMock()
        mock_prev.scalar_one_or_none.return_value = None
        mock_latest = MagicMock()
        mock_latest.scalar_one_or_none.return_value = None
        mock_tz = MagicMock()
        mock_tz.scalar_one_or_none.return_value = "UTC"
        mock_shift = MagicMock()
        mock_shift.scalar_one_or_none.return_value = None
        mock_day = MagicMock()
        mock_day.scalar_one_or_none.return_value = None

        session.execute.side_effect = [
            mock_emp,
            mock_emp,
            mock_idem,
            mock_policy,
            mock_prev,
            mock_latest,
            mock_tz,
            mock_shift,
            mock_day,
        ]

        app.dependency_overrides[get_authenticated_context] = lambda: ctx
        app.dependency_overrides[get_db] = lambda: session

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/attendance/punch",
                    json={
                        "event_type": "CHECK_IN",
                        "idempotency_key": "punch-api-mock-location-test-99",
                        "latitude": 12.9716,
                        "longitude": 77.5946,
                        "accuracy_meters": 12.5,
                        "is_mock_location": True,
                    },
                )
            assert res.status_code == 201
            data = res.json()
            assert data["event"]["is_mock_location"] is True
            assert data["event"]["review_status"] == "PENDING_REVIEW"
            meta = data["event"].get("metadata_json") or data["event"].get("metadata") or {}
            assert "fraud_signals" in meta
            signals = meta["fraud_signals"]
            assert any(s["signal_type"] == "MOCK_LOCATION_DETECTED" for s in signals)
        finally:
            app.dependency_overrides.clear()

    async def test_record_punch_impossible_travel_velocity_flagged(self):
        """Verifies that an impossible geographic jump between consecutive punches flags PENDING_REVIEW."""
        tenant_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        user_id = uuid.uuid4()
        emp = _create_mock_employee(tenant_id, emp_id, user_id)

        # Prior punch at Bangalore 20 minutes ago
        t_curr = datetime.now(UTC) - timedelta(minutes=10)
        t_prev = t_curr - timedelta(minutes=10)
        prev_event = _create_mock_event(tenant_id, emp_id, lat=12.9716, lon=77.5946, effective_at=t_prev)

        session = AsyncMock()
        mock_emp = MagicMock()
        mock_emp.scalar_one_or_none.return_value = emp
        mock_idem = MagicMock()
        mock_idem.scalar_one_or_none.return_value = None
        mock_policy = MagicMock()
        mock_policy.scalar_one_or_none.return_value = TenantAttendancePolicy(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            version=1,
            is_active=True,
            default_mode="MANUAL",
            allowed_methods=["MANUAL"],
            required_methods=["MANUAL"],
            combination_rule="OR",
            gps_config={},
            wifi_config={},
            biometric_config={},
            face_config={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        # Mock previous punch query returning Bangalore coordinates
        mock_prev = MagicMock()
        mock_prev.scalar_one_or_none.return_value = prev_event

        mock_latest = MagicMock()
        mock_latest.scalar_one_or_none.return_value = prev_event
        mock_tz = MagicMock()
        mock_tz.scalar_one_or_none.return_value = "UTC"
        mock_shift = MagicMock()
        mock_shift.scalar_one_or_none.return_value = None
        mock_day = MagicMock()
        mock_day.scalar_one_or_none.return_value = None

        session.execute.side_effect = [
            mock_emp,
            mock_emp,
            mock_idem,
            mock_policy,
            mock_prev,
            mock_latest,
            mock_tz,
            mock_shift,
            mock_day,
        ]

        # Current punch 10 minutes later in Mumbai (980 km away -> velocity ~1633 m/s)
        payload = PunchRequest(
            event_type="CHECK_OUT",
            idempotency_key="punch-velocity-teleport-test-01",
            device_reported_at=t_curr,
            latitude=Decimal("19.0760"),  # Mumbai
            longitude=Decimal("72.8777"),
            accuracy_meters=Decimal("10.0"),
        )

        resp = await record_punch(
            session=session,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role="employee",
            payload=payload,
        )

        assert resp.event.review_status == "PENDING_REVIEW"
        assert "velocity_analysis" in resp.event.metadata
        vel_data = resp.event.metadata["velocity_analysis"]
        assert vel_data["is_impossible"] is True
        assert vel_data["velocity_mps"] > 250.0

    async def test_record_punch_unregistered_device_flagged(self):
        """Verifies that a punch from an unregistered device triggers UNREGISTERED_DEVICE and PENDING_REVIEW."""
        tenant_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        user_id = uuid.uuid4()
        emp = _create_mock_employee(tenant_id, emp_id, user_id)

        session = AsyncMock()
        mock_emp = MagicMock()
        mock_emp.scalar_one_or_none.return_value = emp
        mock_idem = MagicMock()
        mock_idem.scalar_one_or_none.return_value = None
        mock_policy = MagicMock()
        mock_policy.scalar_one_or_none.return_value = TenantAttendancePolicy(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            version=1,
            is_active=True,
            default_mode="MANUAL",
            allowed_methods=["MANUAL"],
            required_methods=["MANUAL"],
            combination_rule="OR",
            gps_config={},
            wifi_config={},
            biometric_config={},
            face_config={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        # Device query: no device record found for this employee and hash
        mock_dev = MagicMock()
        mock_dev.scalar_one_or_none.return_value = None
        # Active device check: employee has an active device registered
        mock_has_active = MagicMock()
        mock_has_active.scalar_one_or_none.return_value = uuid.uuid4()

        mock_latest = MagicMock()
        mock_latest.scalar_one_or_none.return_value = None
        mock_tz = MagicMock()
        mock_tz.scalar_one_or_none.return_value = "UTC"
        mock_shift = MagicMock()
        mock_shift.scalar_one_or_none.return_value = None
        mock_day = MagicMock()
        mock_day.scalar_one_or_none.return_value = None

        session.execute.side_effect = [
            mock_emp,
            mock_emp,
            mock_idem,
            mock_policy,
            mock_dev,
            mock_has_active,
            mock_latest,
            mock_tz,
            mock_shift,
            mock_day,
        ]

        payload = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="punch-unregistered-device-test-01",
            device_id="unregistered-device-hardware-id-999",
        )

        resp = await record_punch(
            session=session,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role="employee",
            payload=payload,
        )

        assert resp.event.review_status == "PENDING_REVIEW"
        assert "fraud_signals" in resp.event.metadata
        signals = resp.event.metadata["fraud_signals"]
        assert any(s["signal_type"] == "UNREGISTERED_DEVICE" for s in signals)
        assert resp.event.metadata["device_validation_status"] == "UNREGISTERED"

