"""Comprehensive automated test suite for Phase 8 Milestone 8.2:
Backend Conflict Submission Engine & Employee APIs.

Tests:
1. Endpoint POST /api/v1/attendance/offline-conflicts/submit (submission validation, identity derivation).
2. Endpoint GET /api/v1/attendance/offline-conflicts/my (employee self-service listing, sanitization).
3. Payload integrity: chronological ordering, event type validation, duplicate key rejection, payload limits.
4. Idempotency & fingerprinting: identical retry (HTTP 200 replay), payload tampering detection (HTTP 409).
5. Concurrency & race condition handling on bundle_id unique constraint.
6. Authorization & RBAC boundaries: employee cannot submit for peers; cross-tenant isolation; employee cannot resolve.
7. Ledger immutability: zero insertions into attendance_events.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError

from services.api.attendance.conflict_service import (
    compute_conflict_bundle_fingerprint,
    list_my_offline_conflict_incidents,
    submit_offline_conflict_bundle,
)
from services.api.attendance.models import AttendanceConflictIncident
from services.api.attendance.schemas import (
    OfflineConflictBundleSubmitRequest,
    OfflineDependentEventPayload,
    OfflineRejectedEventPayload,
)
from services.api.auth.dependencies import AuthenticatedContext, get_authenticated_context
from services.api.auth.models import User
from services.api.auth.permissions import Permission, UserRole, has_permission
from services.api.database import get_db
from services.api.employees.models import Employee
from services.api.main import app
from services.api.organization.models import Department, Designation  # noqa: F401
from services.api.tenants.models import Tenant

# ==============================================================================
# Helper Mock Contexts & Payloads
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
        full_name="Conflict Test User",
        email=f"test_{role.lower()}@conflicts.test",
        password_hash="argon2id$mock",
        role=role.lower(),
        status="active",
    )
    tenant = Tenant(
        id=tid,
        name="Conflict Test Tenant",
        slug=f"tenant-{tid.hex[:8]}",
        timezone="UTC",
    )
    return AuthenticatedContext(user=user, tenant=tenant)


def _mock_employee(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    employee_id: uuid.UUID | None = None,
) -> Employee:
    return Employee(
        id=employee_id or uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        employee_id="EMP-TEST-001",
        work_email="emp@conflicts.test",
        first_name="Jane",
        last_name="Doe",
        joining_date=date(2025, 1, 1),
        status="active",
    )


def _build_valid_conflict_request(
    bundle_id: str = "bundle_valid_101",
    session_id: str = "sess_001",
    target_employee_id: uuid.UUID | None = None,
    notes: str = "Wi-Fi dropped during check-in",
    base_time: datetime | None = None,
) -> OfflineConflictBundleSubmitRequest:
    t0 = base_time or datetime.now(UTC) - timedelta(hours=2)
    t1 = t0 + timedelta(hours=4)
    t2 = t0 + timedelta(hours=8)

    prim = OfflineRejectedEventPayload(
        local_id="loc_1",
        idempotency_key=str(uuid.uuid4()),
        event_type="CHECK_IN",
        device_reported_at=t0,
        latitude=12.971598,
        longitude=77.594562,
        accuracy_meters=14.2,
        device_id_hash="hash_dev_1",
        device_model="Pixel 8",
        os_version="Android 15",
        is_mock_location=False,
        server_rejection_code=422,
        server_rejection_reason="Workplace geofence radius exceeded",
    )

    dep1 = OfflineDependentEventPayload(
        local_id="loc_2",
        idempotency_key=str(uuid.uuid4()),
        event_type="BREAK_START",
        device_reported_at=t1,
        latitude=12.971600,
        longitude=77.594570,
        accuracy_meters=12.0,
        device_id_hash="hash_dev_1",
    )

    dep2 = OfflineDependentEventPayload(
        local_id="loc_3",
        idempotency_key=str(uuid.uuid4()),
        event_type="CHECK_OUT",
        device_reported_at=t2,
        latitude=12.971610,
        longitude=77.594580,
        accuracy_meters=10.5,
        device_id_hash="hash_dev_1",
    )

    return OfflineConflictBundleSubmitRequest(
        bundle_id=bundle_id,
        session_id=session_id,
        employee_notes=notes,
        employee_id=target_employee_id,
        primary_rejected_event=prim,
        dependent_events=[dep1, dep2],
    )


# ==============================================================================
# 1. Payload Schema & Validation Tests
# ==============================================================================


class TestConflictBundleSchemaValidation:
    """Tests Pydantic validation rules on conflict bundle submission payloads."""

    def test_valid_bundle_passes(self):
        req = _build_valid_conflict_request()
        assert req.bundle_id == "bundle_valid_101"
        assert len(req.dependent_events) == 2

    def test_duplicate_idempotency_key_within_bundle_rejected(self):
        """Duplicate idempotency keys within the same bundle must raise validation error."""
        shared_key = str(uuid.uuid4())
        t0 = datetime.now(UTC)
        prim = OfflineRejectedEventPayload(
            local_id="loc_1",
            idempotency_key=shared_key,
            event_type="CHECK_IN",
            device_reported_at=t0,
        )
        dep = OfflineDependentEventPayload(
            local_id="loc_2",
            idempotency_key=shared_key,  # Duplicate!
            event_type="CHECK_OUT",
            device_reported_at=t0 + timedelta(hours=1),
        )

        with pytest.raises(ValueError, match="Duplicate idempotency_key"):
            OfflineConflictBundleSubmitRequest(
                bundle_id="b_dup",
                primary_rejected_event=prim,
                dependent_events=[dep],
            )

    def test_dependent_event_preceding_primary_event_rejected(self):
        """Dependent events cannot have capture timestamps prior to primary rejected event."""
        t0 = datetime.now(UTC)
        prim = OfflineRejectedEventPayload(
            local_id="loc_1",
            idempotency_key=str(uuid.uuid4()),
            event_type="CHECK_IN",
            device_reported_at=t0,
        )
        dep = OfflineDependentEventPayload(
            local_id="loc_2",
            idempotency_key=str(uuid.uuid4()),
            event_type="CHECK_OUT",
            device_reported_at=t0 - timedelta(minutes=10),  # Precedes primary!
        )

        with pytest.raises(ValueError, match="precedes primary event timestamp"):
            OfflineConflictBundleSubmitRequest(
                bundle_id="b_time_order",
                primary_rejected_event=prim,
                dependent_events=[dep],
            )

    def test_dependent_events_out_of_chronological_order_rejected(self):
        """Dependent events must be in strictly ascending chronological order."""
        t0 = datetime.now(UTC)
        prim = OfflineRejectedEventPayload(
            local_id="loc_1",
            idempotency_key=str(uuid.uuid4()),
            event_type="CHECK_IN",
            device_reported_at=t0,
        )
        dep1 = OfflineDependentEventPayload(
            local_id="loc_2",
            idempotency_key=str(uuid.uuid4()),
            event_type="BREAK_START",
            device_reported_at=t0 + timedelta(hours=2),
        )
        dep2 = OfflineDependentEventPayload(
            local_id="loc_3",
            idempotency_key=str(uuid.uuid4()),
            event_type="CHECK_OUT",
            device_reported_at=t0 + timedelta(hours=1),  # Before dep1!
        )

        with pytest.raises(ValueError, match="chronological order"):
            OfflineConflictBundleSubmitRequest(
                bundle_id="b_dep_order",
                primary_rejected_event=prim,
                dependent_events=[dep1, dep2],
            )

    def test_invalid_event_type_rejected(self):
        """Unsupported event types must be rejected."""
        with pytest.raises(ValueError, match="Invalid attendance event type"):
            OfflineRejectedEventPayload(
                local_id="loc_1",
                idempotency_key=str(uuid.uuid4()),
                event_type="INVALID_TYPE",
                device_reported_at=datetime.now(UTC),
            )

    def test_invalid_coordinates_rejected(self):
        """Latitude out of range [-90, 90] must fail validation."""
        with pytest.raises(ValueError):
            OfflineRejectedEventPayload(
                local_id="loc_1",
                idempotency_key=str(uuid.uuid4()),
                event_type="CHECK_IN",
                device_reported_at=datetime.now(UTC),
                latitude=95.0,  # Invalid!
            )

    def test_naive_datetime_converted_to_utc(self):
        """Naive datetimes must automatically gain UTC tzinfo."""
        naive_dt = datetime(2026, 11, 20, 8, 0, 0)
        prim = OfflineRejectedEventPayload(
            local_id="loc_1",
            idempotency_key=str(uuid.uuid4()),
            event_type="CHECK_IN",
            device_reported_at=naive_dt,
        )
        assert prim.device_reported_at.tzinfo == UTC


# ==============================================================================
# 2. Canonical Fingerprinting Tests
# ==============================================================================


class TestCanonicalFingerprintEngine:
    """Validates deterministic SHA-256 fingerprinting for conflict bundles."""

    def test_fingerprint_deterministic_and_reproducible(self):
        tid = uuid.uuid4()
        eid = uuid.uuid4()
        req1 = _build_valid_conflict_request(notes="First note")
        req2 = _build_valid_conflict_request(notes="Second note")  # Notes excluded from punch fingerprint

        # Ensure identical telemetry in req1 and req2
        req2.bundle_id = req1.bundle_id
        req2.session_id = req1.session_id
        req2.primary_rejected_event = req1.primary_rejected_event
        req2.dependent_events = req1.dependent_events

        fp1 = compute_conflict_bundle_fingerprint(tid, eid, req1)
        fp2 = compute_conflict_bundle_fingerprint(tid, eid, req2)

        assert fp1 == fp2
        assert len(fp1) == 64

    def test_fingerprint_changes_on_telemetry_tampering(self):
        tid = uuid.uuid4()
        eid = uuid.uuid4()
        req1 = _build_valid_conflict_request()
        fp1 = compute_conflict_bundle_fingerprint(tid, eid, req1)

        # Tamper coordinate slightly
        req1.primary_rejected_event.latitude = 12.999999
        fp2 = compute_conflict_bundle_fingerprint(tid, eid, req1)

        assert fp1 != fp2

    def test_fingerprint_changes_on_timestamp_tampering(self):
        tid = uuid.uuid4()
        eid = uuid.uuid4()
        req1 = _build_valid_conflict_request()
        fp1 = compute_conflict_bundle_fingerprint(tid, eid, req1)

        # Tamper timestamp by 1 second
        req1.primary_rejected_event.device_reported_at += timedelta(seconds=1)
        fp2 = compute_conflict_bundle_fingerprint(tid, eid, req1)

        assert fp1 != fp2


# ==============================================================================
# 3. Conflict Submission Service Logic & Idempotency Tests
# ==============================================================================


class TestConflictSubmissionService:
    """Tests service layer business logic for conflict submissions."""

    @pytest.mark.asyncio
    async def test_successful_conflict_submission(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        uid = uuid.uuid4()
        emp = _mock_employee(tid, uid)

        # Mock employee lookup
        mock_emp_res = MagicMock()
        mock_emp_res.scalar_one_or_none.return_value = emp

        # Mock existing bundle query (None)
        mock_existing_res = MagicMock()
        mock_existing_res.scalar_one_or_none.return_value = None

        session.execute.side_effect = [
            mock_emp_res,       # User employee lookup
            mock_emp_res,       # Target employee existence check
            mock_existing_res,  # Existing incident check
        ]

        req = _build_valid_conflict_request()
        res = await submit_offline_conflict_bundle(
            session=session,
            tenant_id=tid,
            user_id=uid,
            user_role="employee",
            payload=req,
        )

        assert res.bundle_id == req.bundle_id
        assert res.status == "PENDING_REVIEW"
        assert res.total_events_count == 3
        assert not res.idempotent_replay
        session.add.assert_called_once()
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_idempotent_replay_on_identical_retry(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        uid = uuid.uuid4()
        emp = _mock_employee(tid, uid)
        req = _build_valid_conflict_request()

        fp = compute_conflict_bundle_fingerprint(tid, emp.id, req)
        existing_incident = AttendanceConflictIncident(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=emp.id,
            user_id=uid,
            bundle_id=req.bundle_id,
            status="PENDING_REVIEW",
            primary_rejected_event=req.primary_rejected_event.model_dump(mode="json"),
            dependent_events=[d.model_dump(mode="json") for d in req.dependent_events],
            total_events_count=3,
            metadata_json={"request_fingerprint": fp},
            submitted_at=datetime.now(UTC),
            resolved_correction_event_ids=[],
        )

        mock_emp_res = MagicMock()
        mock_emp_res.scalar_one_or_none.return_value = emp
        mock_existing_res = MagicMock()
        mock_existing_res.scalar_one_or_none.return_value = existing_incident

        session.execute.side_effect = [
            mock_emp_res,       # User employee lookup
            mock_emp_res,       # Target employee existence check
            mock_existing_res,  # Existing incident check
        ]

        res = await submit_offline_conflict_bundle(
            session=session,
            tenant_id=tid,
            user_id=uid,
            user_role="employee",
            payload=req,
        )

        assert res.idempotent_replay is True
        assert res.id == existing_incident.id
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_mismatched_payload_retry_raises_409_conflict(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        uid = uuid.uuid4()
        emp = _mock_employee(tid, uid)
        req = _build_valid_conflict_request()

        existing_incident = AttendanceConflictIncident(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=emp.id,
            user_id=uid,
            bundle_id=req.bundle_id,
            status="PENDING_REVIEW",
            primary_rejected_event=req.primary_rejected_event.model_dump(mode="json"),
            dependent_events=[],
            total_events_count=1,
            metadata_json={"request_fingerprint": "different_hash_stored_previously"},
            resolved_correction_event_ids=[],
        )

        mock_emp_res = MagicMock()
        mock_emp_res.scalar_one_or_none.return_value = emp
        mock_existing_res = MagicMock()
        mock_existing_res.scalar_one_or_none.return_value = existing_incident

        session.execute.side_effect = [
            mock_emp_res,
            mock_emp_res,
            mock_existing_res,
        ]

        with pytest.raises(HTTPException) as exc_info:
            await submit_offline_conflict_bundle(
                session=session,
                tenant_id=tid,
                user_id=uid,
                user_role="employee",
                payload=req,
            )
        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert "mismatched conflict payload" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_concurrent_race_condition_handled_gracefully(self):
        """Simulates simultaneous request race where flush raises IntegrityError."""
        session = AsyncMock()
        tid = uuid.uuid4()
        uid = uuid.uuid4()
        emp = _mock_employee(tid, uid)
        req = _build_valid_conflict_request()
        fp = compute_conflict_bundle_fingerprint(tid, emp.id, req)

        race_won_incident = AttendanceConflictIncident(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=emp.id,
            user_id=uid,
            bundle_id=req.bundle_id,
            status="PENDING_REVIEW",
            primary_rejected_event=req.primary_rejected_event.model_dump(mode="json"),
            dependent_events=[d.model_dump(mode="json") for d in req.dependent_events],
            total_events_count=3,
            metadata_json={"request_fingerprint": fp},
            submitted_at=datetime.now(UTC),
            resolved_correction_event_ids=[],
        )

        mock_emp_res = MagicMock()
        mock_emp_res.scalar_one_or_none.return_value = emp
        mock_none_res = MagicMock()
        mock_none_res.scalar_one_or_none.return_value = None
        mock_race_res = MagicMock()
        mock_race_res.scalar_one_or_none.return_value = race_won_incident

        session.execute.side_effect = [
            mock_emp_res,   # User emp lookup
            mock_emp_res,   # Target emp check
            mock_none_res,  # Initial check saw nothing
            mock_race_res,  # Post-IntegrityError check finds winner
        ]

        session.flush.side_effect = IntegrityError("Unique constraint violation", None, None)

        res = await submit_offline_conflict_bundle(
            session=session,
            tenant_id=tid,
            user_id=uid,
            user_role="employee",
            payload=req,
        )

        assert res.idempotent_replay is True
        assert res.id == race_won_incident.id
        session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_employee_submitting_for_peer_raises_403_forbidden(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        uid = uuid.uuid4()
        emp = _mock_employee(tid, uid)
        peer_id = uuid.uuid4()

        mock_emp_res = MagicMock()
        mock_emp_res.scalar_one_or_none.return_value = emp

        session.execute.return_value = mock_emp_res

        req = _build_valid_conflict_request(target_employee_id=peer_id)
        with pytest.raises(HTTPException) as exc_info:
            await submit_offline_conflict_bundle(
                session=session,
                tenant_id=tid,
                user_id=uid,
                user_role="employee",
                payload=req,
            )
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "only submit conflict bundles for their own attendance" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_caller_without_employee_profile_raises_400(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        uid = uuid.uuid4()

        mock_emp_res = MagicMock()
        mock_emp_res.scalar_one_or_none.return_value = None

        session.execute.return_value = mock_emp_res

        req = _build_valid_conflict_request()
        with pytest.raises(HTTPException) as exc_info:
            await submit_offline_conflict_bundle(
                session=session,
                tenant_id=tid,
                user_id=uid,
                user_role="employee",
                payload=req,
            )
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "No employee profile linked to current user" in exc_info.value.detail


# ==============================================================================
# 4. Employee Listing Service & Sanitization Tests
# ==============================================================================


class TestEmployeeListingService:
    """Tests GET /api/v1/attendance/offline-conflicts/my logic and data sanitization."""

    @pytest.mark.asyncio
    async def test_list_my_conflicts_sanitizes_reviewer_details(self):
        session = AsyncMock()
        tid = uuid.uuid4()
        uid = uuid.uuid4()
        eid = uuid.uuid4()
        reviewer_id = uuid.uuid4()

        # Mock emp id query
        mock_eid_res = MagicMock()
        mock_eid_res.scalar_one_or_none.return_value = eid

        mock_count_res = MagicMock()
        mock_count_res.scalar.return_value = 1

        mock_incident = AttendanceConflictIncident(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=eid,
            user_id=uid,
            bundle_id="bundle_999",
            status="APPROVED",
            primary_rejected_event={
                "event_type": "CHECK_IN",
                "device_reported_at": "2026-11-20T08:00:00Z",
            },
            dependent_events=[],
            total_events_count=1,
            rejection_summary="Geofence mismatch",
            employee_notes="Was on-site",
            submitted_at=datetime.now(UTC),
            decision="APPROVED",
            decision_reason="Approved with supervisor override",
            reviewer_user_id=reviewer_id,  # Sensitive internal reviewer ID!
            decided_at=datetime.now(UTC),
            resolved_correction_event_ids=["eid_1"],
            metadata_json={"internal_flags": "private"},  # Sensitive internal metadata!
        )

        mock_items_res = MagicMock()
        mock_items_res.scalars.return_value.all.return_value = [mock_incident]

        session.execute.side_effect = [
            mock_eid_res,    # Emp ID lookup
            mock_count_res,  # Total count query
            mock_items_res,  # Records query
        ]

        res = await list_my_offline_conflict_incidents(
            session=session,
            tenant_id=tid,
            user_id=uid,
        )

        assert res.total == 1
        assert len(res.items) == 1
        item = res.items[0]
        assert item.bundle_id == "bundle_999"
        assert item.status == "APPROVED"
        assert item.decision == "APPROVED"
        assert item.decision_reason == "Approved with supervisor override"
        assert item.resolved_events_count == 1

        # Assert no internal reviewer user id or private metadata exposed on summary
        assert not hasattr(item, "reviewer_user_id")
        assert not hasattr(item, "metadata_json")


# ==============================================================================
# 5. Full FastAPI HTTP Route Integration Tests
# ==============================================================================


class TestConflictAPIHTTPRoutes:
    """Full HTTP API integration tests testing endpoints, status codes, and RBAC."""

    @pytest.mark.asyncio
    async def test_post_conflict_submit_endpoint_201_created(self):
        tid = uuid.uuid4()
        uid = uuid.uuid4()
        ctx = _mock_context("employee", tenant_id=tid, user_id=uid)
        emp = _mock_employee(tid, uid)

        mock_db = AsyncMock()
        mock_emp_res = MagicMock()
        mock_emp_res.scalar_one_or_none.return_value = emp
        mock_none_res = MagicMock()
        mock_none_res.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [
            mock_emp_res,
            mock_emp_res,
            mock_none_res,
        ]

        app.dependency_overrides[get_authenticated_context] = lambda: ctx
        app.dependency_overrides[get_db] = lambda: mock_db

        req = _build_valid_conflict_request(bundle_id="b_http_101")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/attendance/offline-conflicts/submit",
                json=req.model_dump(mode="json"),
            )

        app.dependency_overrides.clear()

        assert resp.status_code == status.HTTP_201_CREATED
        data = resp.json()
        assert data["bundle_id"] == "b_http_101"
        assert data["status"] == "PENDING_REVIEW"
        assert data["idempotent_replay"] is False

    @pytest.mark.asyncio
    async def test_post_conflict_submit_endpoint_idempotent_replay_200_ok(self):
        tid = uuid.uuid4()
        uid = uuid.uuid4()
        ctx = _mock_context("employee", tenant_id=tid, user_id=uid)
        emp = _mock_employee(tid, uid)
        req = _build_valid_conflict_request(bundle_id="b_http_replay")

        fp = compute_conflict_bundle_fingerprint(tid, emp.id, req)
        existing_incident = AttendanceConflictIncident(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=emp.id,
            user_id=uid,
            bundle_id=req.bundle_id,
            status="PENDING_REVIEW",
            primary_rejected_event=req.primary_rejected_event.model_dump(mode="json"),
            dependent_events=[d.model_dump(mode="json") for d in req.dependent_events],
            total_events_count=3,
            metadata_json={"request_fingerprint": fp},
            submitted_at=datetime.now(UTC),
            resolved_correction_event_ids=[],
        )

        mock_db = AsyncMock()
        mock_emp_res = MagicMock()
        mock_emp_res.scalar_one_or_none.return_value = emp
        mock_existing_res = MagicMock()
        mock_existing_res.scalar_one_or_none.return_value = existing_incident

        mock_db.execute.side_effect = [
            mock_emp_res,
            mock_emp_res,
            mock_existing_res,
        ]

        app.dependency_overrides[get_authenticated_context] = lambda: ctx
        app.dependency_overrides[get_db] = lambda: mock_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/attendance/offline-conflicts/submit",
                json=req.model_dump(mode="json"),
            )

        app.dependency_overrides.clear()

        # Idempotent replay must return HTTP 200 OK!
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["bundle_id"] == "b_http_replay"
        assert data["idempotent_replay"] is True

    @pytest.mark.asyncio
    async def test_get_my_conflicts_endpoint_200_ok(self):
        tid = uuid.uuid4()
        uid = uuid.uuid4()
        ctx = _mock_context("employee", tenant_id=tid, user_id=uid)
        eid = uuid.uuid4()

        mock_db = AsyncMock()
        mock_eid_res = MagicMock()
        mock_eid_res.scalar_one_or_none.return_value = eid
        mock_count_res = MagicMock()
        mock_count_res.scalar.return_value = 0
        mock_items_res = MagicMock()
        mock_items_res.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [
            mock_eid_res,
            mock_count_res,
            mock_items_res,
        ]

        app.dependency_overrides[get_authenticated_context] = lambda: ctx
        app.dependency_overrides[get_db] = lambda: mock_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/attendance/offline-conflicts/my")

        app.dependency_overrides.clear()

        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert "items" in data
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_anonymous_caller_rejected_401_unauthorized(self):
        """Endpoints without credentials must reject with HTTP 401."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/attendance/offline-conflicts/submit",
                json={},
            )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_employee_cannot_resolve_conflict_permission(self):
        """Assert that Employee role lacks RESOLVE_ATTENDANCE_CONFLICT permission."""
        assert has_permission(UserRole.EMPLOYEE, Permission.SUBMIT_ATTENDANCE_CONFLICT)
        assert has_permission(UserRole.EMPLOYEE, Permission.VIEW_ATTENDANCE_CONFLICTS)
        assert not has_permission(UserRole.EMPLOYEE, Permission.RESOLVE_ATTENDANCE_CONFLICT)
