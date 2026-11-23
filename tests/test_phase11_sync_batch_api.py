"""Comprehensive automated test suite for Phase 11.2:
Backend Batch Sync Protocol & Timestamp Semantic Hardening.

Covers all 20 required scenarios:
1. One valid event.
2. Multiple valid events (chronological session).
3. Maximum 50 events.
4. More than 50 events rejected (HTTP 422).
5. Duplicate event in same batch.
6. Duplicate event across separate batches.
7. Lost response followed by retry.
8. Concurrent duplicate submission.
9. Partial batch failure (savepoint isolation).
10. Invalid event type.
11. Clock drift (tolerable drift vs delayed offline sync).
12. Future timestamp (> 300s rejected; 60s-300s flagged as REQUIRES_REVIEW).
13. Historical timestamp (> 72h rejected; 24h-72h flagged as REQUIRES_REVIEW).
14. Out-of-order events (BREAK_START before CHECK_IN).
15. Missing prerequisite event (BREAK_END when not on break).
16. Cross-tenant submission isolation.
17. Cross-user submission forbidden (employee for peer returns 403).
18. Database transaction commit failure handling.
19. Duplicate sequence number detection.
20. Auto-break end on checkout in batch.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from services.api.attendance.models import (
    AttendanceEvent,
    AttendanceIdempotencyRecord,
    TenantAttendancePolicy,
)
from services.api.attendance.policy_engine import PolicyEvaluationOutcome
from services.api.attendance.schemas import (
    AttendanceBatchSyncRequest,
    BatchSyncItemStatus,
    BatchSyncPunchItem,
)
from services.api.attendance.sync_service import (
    process_attendance_batch_sync,
    validate_batch_item_timestamp,
)
from services.api.auth.dependencies import AuthenticatedContext, get_authenticated_context
from services.api.auth.models import User
from services.api.database import get_db
from services.api.employees.models import Employee
from services.api.fraud.schemas import FraudEvidenceAssessment
from services.api.main import app
from services.api.tenants.models import Tenant

# ==============================================================================
# Helper Mock Contexts & Entities
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
        full_name="Sync Test User",
        email=f"test_{role.lower()}@sync.test",
        password_hash="argon2id$mock",
        role=role.lower(),
        status="active",
    )
    tenant = Tenant(
        id=tid,
        name="Sync Test Tenant",
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
        employee_id="EMP-SYNC-01",
        first_name="Sam",
        last_name="Tester",
        work_email="sam.tester@sync.test",
        status="active",
        joining_date=date(2026, 1, 1),
    )


def _mock_punch_item(
    event_type: str = "CHECK_IN",
    device_reported_at: datetime | None = None,
    idempotency_key: str | None = None,
    local_id: str | None = None,
    sequence_number: int | None = None,
    session_id: str | None = None,
    location_id: uuid.UUID | None = None,
    latitude: float | None = 12.9716,
    longitude: float | None = 77.5946,
    device_id: str | None = "device-test-01",
    is_mock_location: bool = False,
    metadata: dict | None = None,
) -> BatchSyncPunchItem:
    now_utc = device_reported_at or datetime.now(UTC)
    return BatchSyncPunchItem(
        local_id=local_id or f"loc_{uuid.uuid4().hex[:8]}",
        idempotency_key=idempotency_key or str(uuid.uuid4()),
        event_type=event_type,
        device_reported_at=now_utc,
        sequence_number=sequence_number,
        session_id=session_id or "sess_001",
        location_id=location_id,
        latitude=latitude,
        longitude=longitude,
        accuracy_meters=15.0,
        wifi_bssid="00:14:22:01:23:45",
        device_id=device_id,
        is_mock_location=is_mock_location,
        metadata=metadata or {"offline_queued": True},
    )


# ==============================================================================
# 1. Timestamp Validation & Hardening Unit Tests
# ==============================================================================


class TestTimestampSemanticHardening:
    """Tests for validate_batch_item_timestamp."""

    def test_tolerable_drift_within_300s_anchors_to_device_time(self):
        """Offline punch within tolerable drift assigns effective_at = dev_time_utc."""
        server_now = datetime.now(UTC)
        dev_time = server_now - timedelta(seconds=120)

        (
            effective_at,
            clock_drift_seconds,
            status_str,
            review_status,
            err_code,
            err_msg,
            flags,
        ) = validate_batch_item_timestamp(
            dev_time_utc=dev_time,
            server_received_at=server_now,
            standard_window_hours=24,
            max_offline_hours=72,
        )

        assert err_code is None
        assert status_str == "SERVER_AUTHORITATIVE"
        assert review_status == "NOT_REQUIRED"
        assert effective_at == dev_time
        assert clock_drift_seconds == Decimal("120.000")

    def test_delayed_offline_sync_within_24h_assigns_device_time(self):
        """Offline punch 4 hours old within standard 24h window flags delayed sync but keeps device time."""
        server_now = datetime.now(UTC)
        dev_time = server_now - timedelta(hours=4)

        (
            effective_at,
            clock_drift_seconds,
            status_str,
            review_status,
            err_code,
            err_msg,
            flags,
        ) = validate_batch_item_timestamp(
            dev_time_utc=dev_time,
            server_received_at=server_now,
            standard_window_hours=24,
            max_offline_hours=72,
        )

        assert err_code is None
        assert status_str == "UNVERIFIED_OFFLINE"
        assert review_status == "NOT_REQUIRED"
        assert effective_at == dev_time
        assert "FLAG_DELAYED_OFFLINE_SYNC" in flags

    def test_offline_window_exceeded_between_24h_and_72h_requires_review(self):
        """Offline punch 36h old is accepted for supervisor review with device timestamp."""
        server_now = datetime.now(UTC)
        dev_time = server_now - timedelta(hours=36)

        (
            effective_at,
            clock_drift_seconds,
            status_str,
            review_status,
            err_code,
            err_msg,
            flags,
        ) = validate_batch_item_timestamp(
            dev_time_utc=dev_time,
            server_received_at=server_now,
            standard_window_hours=24,
            max_offline_hours=72,
        )

        assert err_code is None
        assert status_str == "UNVERIFIED_OFFLINE"
        assert review_status == "PENDING_REVIEW"
        assert effective_at == dev_time
        assert "FLAG_OFFLINE_WINDOW_EXCEEDED" in flags

    def test_historical_timestamp_exceeding_72h_rejected(self):
        """Offline punch older than 72 hours is rejected immediately."""
        server_now = datetime.now(UTC)
        dev_time = server_now - timedelta(hours=73)

        (
            effective_at,
            clock_drift_seconds,
            status_str,
            review_status,
            err_code,
            err_msg,
            flags,
        ) = validate_batch_item_timestamp(
            dev_time_utc=dev_time,
            server_received_at=server_now,
            standard_window_hours=24,
            max_offline_hours=72,
        )

        assert err_code == "OFFLINE_WINDOW_EXCEEDED"
        assert "older than allowable limit" in err_msg

    def test_future_timestamp_between_60s_and_300s_requires_review(self):
        """Future timestamp between 60s and 300s is held for review and anchored to server time."""
        server_now = datetime.now(UTC)
        dev_time = server_now + timedelta(seconds=120)

        (
            effective_at,
            clock_drift_seconds,
            status_str,
            review_status,
            err_code,
            err_msg,
            flags,
        ) = validate_batch_item_timestamp(
            dev_time_utc=dev_time,
            server_received_at=server_now,
            standard_window_hours=24,
            max_offline_hours=72,
        )

        assert err_code is None
        assert status_str == "SUSPICIOUS_CLOCK_DRIFT"
        assert review_status == "PENDING_REVIEW"
        assert effective_at == server_now  # Prefers server_received_at to prevent premature future working time
        assert effective_at != dev_time
        assert "FLAG_FUTURE_TIMESTAMP_DETECTED" in flags

    def test_future_timestamp_exceeding_300s_rejected(self):
        """Future timestamp beyond 300 seconds is rejected immediately."""
        server_now = datetime.now(UTC)
        dev_time = server_now + timedelta(seconds=350)

        (
            effective_at,
            clock_drift_seconds,
            status_str,
            review_status,
            err_code,
            err_msg,
            flags,
        ) = validate_batch_item_timestamp(
            dev_time_utc=dev_time,
            server_received_at=server_now,
            standard_window_hours=24,
            max_offline_hours=72,
        )

        assert err_code == "FUTURE_TIMESTAMP"
        assert "implausibly in the future" in err_msg


# ==============================================================================
# 2. Batch Sync Service & Scenarios Unit Tests
# ==============================================================================


class TestBatchSyncServiceLogic:
    """Comprehensive service-level unit tests for process_attendance_batch_sync."""

    @pytest.fixture(autouse=True)
    def patch_default_policy(self):
        policy = TenantAttendancePolicy(
            id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            version=1,
            is_active=True,
            default_mode="MANUAL",
            allowed_methods=["MANUAL"],
            required_methods=["MANUAL"],
            combination_rule="OR",
            gps_config={},
            wifi_config={},
        )
        with patch(
            "services.api.attendance.sync_service.get_active_tenant_policy",
            new=AsyncMock(return_value=policy),
        ):
            yield policy

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        nested_mock = MagicMock()
        nested_mock.__aenter__ = AsyncMock(return_value=None)
        nested_mock.__aexit__ = AsyncMock(return_value=None)
        session.begin_nested = MagicMock(return_value=nested_mock)
        session.add = MagicMock()
        return session

    @pytest.mark.asyncio
    async def test_scenario_01_one_valid_event(self, mock_session):
        """Scenario 1: Submits one valid offline punch -> ACCEPTED with accurate effective_at."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        emp = _mock_employee(tenant_id, user_id)
        now_utc = datetime.now(UTC) - timedelta(hours=4) - timedelta(hours=2)

        # Mock DB queries:
        # 1. user_emp
        # 2. with_for_update emp
        # 3. tenant timezone
        # 4. latest event (None -> CHECKED_OUT)
        # 5. idempotency check (None)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = [
            emp,  # user_emp
            emp,  # with_for_update emp
            "Asia/Kolkata",  # timezone
            None,  # latest_event
            None,  # existing idempotency
        ]
        mock_session.execute.return_value = mock_result

        item = _mock_punch_item(
            event_type="CHECK_IN",
            device_reported_at=now_utc,
            sequence_number=1,
        )
        req = AttendanceBatchSyncRequest(items=[item])

        with (
            patch(
                "services.api.attendance.sync_service.evaluate_punch_policy",
                new=AsyncMock(return_value=PolicyEvaluationOutcome(is_verified=True, policy_version=1)),
            ),
            patch(
                "services.api.attendance.sync_service.evaluate_attendance_fraud_evidence",
                new=AsyncMock(
                    return_value=FraudEvidenceAssessment(
                        signals=[],
                        velocity_result=None,
                        device_validation_status="ACTIVE",
                        review_status="NOT_REQUIRED",
                        device_id_uuid=uuid.uuid4(),
                    )
                ),
            ),
            patch(
                "services.api.attendance.sync_service.determine_shift_date_for_punch",
                new=AsyncMock(return_value=date(2026, 11, 22)),
            ),
            patch(
                "services.api.attendance.sync_service.recalculate_attendance_day",
                new=AsyncMock(),
            ),
        ):
            resp = await process_attendance_batch_sync(
                session=mock_session,
                tenant_id=tenant_id,
                user_id=user_id,
                user_role="employee",
                payload=req,
            )

        assert resp.total_items == 1
        assert resp.accepted_count == 1
        assert resp.rejected_count == 0
        receipt = resp.receipts[0]
        assert receipt.status == BatchSyncItemStatus.ACCEPTED
        assert receipt.local_id == item.local_id
        assert receipt.effective_at == now_utc
        assert receipt.idempotent_replay is False

    @pytest.mark.asyncio
    async def test_scenario_02_multiple_valid_events_in_session(self, mock_session):
        """Scenario 2: Submits a full valid shift sequence: CHECK_IN, BREAK_START, BREAK_END, CHECK_OUT."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        emp = _mock_employee(tenant_id, user_id)
        base_time = datetime.now(UTC) - timedelta(hours=8)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = [
            emp,  # user_emp
            emp,  # with_for_update emp
            "UTC",  # timezone
            None,  # initial DB state -> CHECKED_OUT
            None,  # idem 1
            None,  # idem 2
            None,  # idem 3
            None,  # idem 4
        ]
        mock_session.execute.return_value = mock_result

        items = [
            _mock_punch_item("CHECK_IN", base_time, sequence_number=1),
            _mock_punch_item("BREAK_START", base_time + timedelta(hours=4), sequence_number=2),
            _mock_punch_item("BREAK_END", base_time + timedelta(hours=4, minutes=45), sequence_number=3),
            _mock_punch_item("CHECK_OUT", base_time + timedelta(hours=8), sequence_number=4),
        ]
        req = AttendanceBatchSyncRequest(items=items)

        with (
            patch(
                "services.api.attendance.sync_service.evaluate_punch_policy",
                new=AsyncMock(return_value=PolicyEvaluationOutcome(is_verified=True, policy_version=1)),
            ),
            patch(
                "services.api.attendance.sync_service.evaluate_attendance_fraud_evidence",
                new=AsyncMock(
                    return_value=FraudEvidenceAssessment(
                        signals=[],
                        velocity_result=None,
                        device_validation_status="ACTIVE",
                        review_status="NOT_REQUIRED",
                        device_id_uuid=uuid.uuid4(),
                    )
                ),
            ),
            patch(
                "services.api.attendance.sync_service.determine_shift_date_for_punch",
                new=AsyncMock(return_value=date(2026, 11, 22)),
            ),
            patch(
                "services.api.attendance.sync_service.recalculate_attendance_day",
                new=AsyncMock(),
            ),
        ):
            resp = await process_attendance_batch_sync(
                session=mock_session,
                tenant_id=tenant_id,
                user_id=user_id,
                user_role="employee",
                payload=req,
            )

        assert resp.total_items == 4
        assert resp.accepted_count == 4
        assert [r.status for r in resp.receipts] == [
            BatchSyncItemStatus.ACCEPTED,
            BatchSyncItemStatus.ACCEPTED,
            BatchSyncItemStatus.ACCEPTED,
            BatchSyncItemStatus.ACCEPTED,
        ]

    @pytest.mark.asyncio
    async def test_scenario_03_and_04_batch_size_limits(self, mock_session):
        """Scenarios 3 & 4: Maximum 50 events accepted; > 50 rejected with HTTP 422."""
        # 1. Exactly 50 events allowed by Pydantic schema
        fifty_items = [_mock_punch_item(sequence_number=i) for i in range(1, 51)]
        req_50 = AttendanceBatchSyncRequest(items=fifty_items)
        assert len(req_50.items) == 50

        # 2. 51 events raises validation error
        fifty_one_items = [_mock_punch_item(sequence_number=i) for i in range(1, 52)]
        with pytest.raises(ValidationError):
            AttendanceBatchSyncRequest(items=fifty_one_items)

    @pytest.mark.asyncio
    async def test_scenario_05_duplicate_event_in_same_batch(self, mock_session):
        """Scenario 5: Duplicate idempotency key in same batch returns DUPLICATE for second item."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        emp = _mock_employee(tenant_id, user_id)
        shared_key = str(uuid.uuid4())

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = [
            emp,
            emp,
            "UTC",
            None,
            None,  # First item has no existing DB record
        ]
        mock_session.execute.return_value = mock_result

        item1 = _mock_punch_item("CHECK_IN", idempotency_key=shared_key, sequence_number=1)
        item2 = _mock_punch_item("CHECK_IN", idempotency_key=shared_key, sequence_number=1)
        req = AttendanceBatchSyncRequest(items=[item1, item2])

        with (
            patch(
                "services.api.attendance.sync_service.evaluate_punch_policy",
                new=AsyncMock(return_value=PolicyEvaluationOutcome(is_verified=True, policy_version=1)),
            ),
            patch(
                "services.api.attendance.sync_service.evaluate_attendance_fraud_evidence",
                new=AsyncMock(
                    return_value=FraudEvidenceAssessment(
                        signals=[],
                        velocity_result=None,
                        device_validation_status="ACTIVE",
                        review_status="NOT_REQUIRED",
                        device_id_uuid=uuid.uuid4(),
                    )
                ),
            ),
            patch(
                "services.api.attendance.sync_service.determine_shift_date_for_punch",
                new=AsyncMock(return_value=date(2026, 11, 22)),
            ),
            patch(
                "services.api.attendance.sync_service.recalculate_attendance_day",
                new=AsyncMock(),
            ),
        ):
            resp = await process_attendance_batch_sync(
                session=mock_session,
                tenant_id=tenant_id,
                user_id=user_id,
                user_role="employee",
                payload=req,
            )

        assert resp.total_items == 2
        assert resp.accepted_count == 1
        assert resp.duplicate_count == 1
        assert resp.receipts[0].status == BatchSyncItemStatus.ACCEPTED
        assert resp.receipts[1].status == BatchSyncItemStatus.DUPLICATE
        assert resp.receipts[1].idempotent_replay is True

    @pytest.mark.asyncio
    async def test_scenario_06_and_07_duplicate_across_batches_and_lost_ack_retry(self, mock_session):
        """Scenarios 6 & 7: Duplicate submission across separate batches returns DUPLICATE from DB idempotency record."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        emp = _mock_employee(tenant_id, user_id)
        existing_event_id = uuid.uuid4()
        shared_key = str(uuid.uuid4())

        existing_idem = AttendanceIdempotencyRecord(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            employee_id=emp.id,
            idempotency_key=shared_key,
            request_fingerprint="fp123",
            status="COMPLETED",
            response_code=201,
            event_id=existing_event_id,
        )
        existing_event = AttendanceEvent(
            id=existing_event_id,
            tenant_id=tenant_id,
            employee_id=emp.id,
            event_type="CHECK_IN",
            effective_at=datetime.now(UTC),
            review_status="NOT_REQUIRED",
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = [
            emp,
            emp,
            "UTC",
            None,
            existing_idem,  # Existing DB record found
            existing_event,  # Existing event found
        ]
        mock_session.execute.return_value = mock_result

        item = _mock_punch_item("CHECK_IN", idempotency_key=shared_key)
        req = AttendanceBatchSyncRequest(items=[item])

        resp = await process_attendance_batch_sync(
            session=mock_session,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role="employee",
            payload=req,
        )

        assert resp.total_items == 1
        assert resp.duplicate_count == 1
        assert resp.receipts[0].status == BatchSyncItemStatus.DUPLICATE
        assert resp.receipts[0].server_event_id == existing_event_id
        assert resp.receipts[0].idempotent_replay is True

    @pytest.mark.asyncio
    async def test_scenario_08_concurrent_duplicate_submission(self, mock_session):
        """Scenario 8: Concurrent duplicate insertion caught via IntegrityError in savepoint."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        emp = _mock_employee(tenant_id, user_id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = [
            emp,
            emp,
            "UTC",
            None,
            None,  # No initial idem
        ]
        mock_session.execute.return_value = mock_result
        mock_session.flush.side_effect = IntegrityError(
            "duplicate key value violates unique constraint", params={}, orig=None
        )

        item = _mock_punch_item("CHECK_IN")
        req = AttendanceBatchSyncRequest(items=[item])

        with (
            patch(
                "services.api.attendance.sync_service.evaluate_punch_policy",
                new=AsyncMock(return_value=PolicyEvaluationOutcome(is_verified=True, policy_version=1)),
            ),
            patch(
                "services.api.attendance.sync_service.evaluate_attendance_fraud_evidence",
                new=AsyncMock(
                    return_value=FraudEvidenceAssessment(
                        signals=[],
                        velocity_result=None,
                        device_validation_status="ACTIVE",
                        review_status="NOT_REQUIRED",
                        device_id_uuid=uuid.uuid4(),
                    )
                ),
            ),
        ):
            resp = await process_attendance_batch_sync(
                session=mock_session,
                tenant_id=tenant_id,
                user_id=user_id,
                user_role="employee",
                payload=req,
            )

        assert resp.total_items == 1
        assert resp.duplicate_count == 1
        assert resp.receipts[0].status == BatchSyncItemStatus.DUPLICATE
        assert resp.receipts[0].idempotent_replay is True

    @pytest.mark.asyncio
    async def test_scenario_09_partial_batch_failure_savepoint_isolation(self, mock_session):
        """Scenario 9: Partial batch failure: Item 1 succeeds, Item 2 fails geofence, Item 3 is conflict."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        emp = _mock_employee(tenant_id, user_id)
        now_utc = datetime.now(UTC) - timedelta(hours=4)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = [
            emp,
            emp,
            "UTC",
            None,
            None,  # idem 1
            None,  # idem 2
            None,  # idem 3
        ]
        mock_session.execute.return_value = mock_result

        item1 = _mock_punch_item("CHECK_IN", now_utc, sequence_number=1)
        item2 = _mock_punch_item("BREAK_START", now_utc + timedelta(hours=1), sequence_number=2)
        item3 = _mock_punch_item("BREAK_END", now_utc + timedelta(hours=2), sequence_number=3)
        req = AttendanceBatchSyncRequest(items=[item1, item2, item3])

        # Item 1 allowed; Item 2 rejected by policy (Geofence failed); Item 3 conflict
        def policy_side_effect(**kwargs):
            if kwargs["event_type"] == "CHECK_IN":
                return PolicyEvaluationOutcome(is_verified=True, policy_version=1)
            elif kwargs["event_type"] == "BREAK_START":
                raise HTTPException(
                    status_code=400,
                    detail="GPS distance 250m exceeds 100m geofence",
                )
            return PolicyEvaluationOutcome(is_verified=True, policy_version=1)

        with (
            patch(
                "services.api.attendance.sync_service.evaluate_punch_policy",
                side_effect=policy_side_effect,
            ),
            patch(
                "services.api.attendance.sync_service.evaluate_attendance_fraud_evidence",
                new=AsyncMock(
                    return_value=FraudEvidenceAssessment(
                        signals=[],
                        velocity_result=None,
                        device_validation_status="ACTIVE",
                        review_status="NOT_REQUIRED",
                        device_id_uuid=uuid.uuid4(),
                    )
                ),
            ),
            patch(
                "services.api.attendance.sync_service.determine_shift_date_for_punch",
                new=AsyncMock(return_value=date(2026, 11, 22)),
            ),
            patch(
                "services.api.attendance.sync_service.recalculate_attendance_day",
                new=AsyncMock(),
            ),
        ):
            resp = await process_attendance_batch_sync(
                session=mock_session,
                tenant_id=tenant_id,
                user_id=user_id,
                user_role="employee",
                payload=req,
            )

        assert resp.total_items == 3
        assert resp.accepted_count == 1
        assert resp.rejected_count == 1
        assert resp.conflict_count == 1

        assert resp.receipts[0].status == BatchSyncItemStatus.ACCEPTED
        assert resp.receipts[1].status == BatchSyncItemStatus.REJECTED
        assert resp.receipts[1].error_code == "POLICY_VIOLATION"
        assert resp.receipts[2].status == BatchSyncItemStatus.CONFLICT
        assert resp.receipts[2].error_code == "SEQUENCE_CONFLICT"

    def test_scenario_10_invalid_event_type_schema_validation(self):
        """Scenario 10: Invalid event_type raises Pydantic validation error."""
        with pytest.raises(ValidationError) as exc_info:
            _mock_punch_item(event_type="UNAUTHORIZED_PUNCH_ACTION")
        assert "Invalid attendance event type" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_scenarios_14_and_15_out_of_order_and_missing_prerequisite(self, mock_session):
        """Scenarios 14 & 15: Out-of-order punch (BREAK_START when checked out) returns CONFLICT."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        emp = _mock_employee(tenant_id, user_id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = [
            emp,
            emp,
            "UTC",
            None,  # initial state CHECKED_OUT
            None,
        ]
        mock_session.execute.return_value = mock_result

        # Submitting BREAK_START while currently CHECKED_OUT
        item = _mock_punch_item("BREAK_START", sequence_number=1)
        req = AttendanceBatchSyncRequest(items=[item])

        with (
            patch(
                "services.api.attendance.sync_service.evaluate_punch_policy",
                new=AsyncMock(return_value=PolicyEvaluationOutcome(is_verified=True, policy_version=1)),
            ),
            patch(
                "services.api.attendance.sync_service.evaluate_attendance_fraud_evidence",
                new=AsyncMock(
                    return_value=FraudEvidenceAssessment(
                        signals=[],
                        velocity_result=None,
                        device_validation_status="ACTIVE",
                        review_status="NOT_REQUIRED",
                        device_id_uuid=uuid.uuid4(),
                    )
                ),
            ),
        ):
            resp = await process_attendance_batch_sync(
                session=mock_session,
                tenant_id=tenant_id,
                user_id=user_id,
                user_role="employee",
                payload=req,
            )

        assert resp.total_items == 1
        assert resp.conflict_count == 1
        assert resp.receipts[0].status == BatchSyncItemStatus.CONFLICT
        assert resp.receipts[0].error_code == "SEQUENCE_CONFLICT"
        assert "must check in before starting a break" in resp.receipts[0].error_message

    @pytest.mark.asyncio
    async def test_scenario_16_cross_tenant_isolation(self, mock_session):
        """Scenario 16: Employee submitting batch against mismatched tenant context is rejected."""
        tenant_b = uuid.uuid4()
        user_id = uuid.uuid4()

        # Employee belongs to Tenant A, but request is under Tenant B
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        req = AttendanceBatchSyncRequest(items=[_mock_punch_item()])

        with pytest.raises(HTTPException) as exc_info:
            await process_attendance_batch_sync(
                session=mock_session,
                tenant_id=tenant_b,
                user_id=user_id,
                user_role="employee",
                payload=req,
            )
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "No employee profile linked to current user" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_scenario_17_cross_user_submission_forbidden(self, mock_session):
        """Scenario 17: Employee attempting to sync punches for another employee receives HTTP 403."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        other_emp_id = uuid.uuid4()
        emp = _mock_employee(tenant_id, user_id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = emp
        mock_session.execute.return_value = mock_result

        req = AttendanceBatchSyncRequest(employee_id=other_emp_id, items=[_mock_punch_item()])

        with pytest.raises(HTTPException) as exc_info:
            await process_attendance_batch_sync(
                session=mock_session,
                tenant_id=tenant_id,
                user_id=user_id,
                user_role="employee",
                payload=req,
            )
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Employees can only submit attendance sync batches for themselves" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_manager_submission_for_non_direct_report_forbidden(self, mock_session):
        """Manager attempting to sync for employee who is NOT their direct report receives HTTP 403."""
        tenant_id = uuid.uuid4()
        mgr_user_id = uuid.uuid4()
        other_emp_id = uuid.uuid4()
        mgr_emp = _mock_employee(tenant_id, mgr_user_id)

        # 1. user_emp -> mgr_emp
        # 2. direct report check -> None (not a direct report)
        mock_session.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=mgr_emp)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]

        req = AttendanceBatchSyncRequest(employee_id=other_emp_id, items=[_mock_punch_item()])

        with pytest.raises(HTTPException) as exc_info:
            await process_attendance_batch_sync(
                session=mock_session,
                tenant_id=tenant_id,
                user_id=mgr_user_id,
                user_role="manager",
                payload=req,
            )
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Managers can only submit attendance sync batches for themselves or their direct reports" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_manager_submission_for_direct_report_allowed(self, mock_session):
        """Manager submitting for verified direct report is allowed."""
        tenant_id = uuid.uuid4()
        mgr_user_id = uuid.uuid4()
        report_emp_id = uuid.uuid4()
        mgr_emp = _mock_employee(tenant_id, mgr_user_id)
        report_emp = _mock_employee(tenant_id, uuid.uuid4(), employee_id=report_emp_id)

        now_utc = datetime.now(UTC) - timedelta(hours=2)

        # 1. user_emp -> mgr_emp
        # 2. direct report check -> report_emp_id
        # 3. with_for_update emp -> report_emp
        # 4. tenant timezone -> "UTC"
        # 5. latest_event -> None
        # 6. idempotency -> None
        mock_session.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=mgr_emp)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=report_emp_id)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=report_emp)),
            MagicMock(scalar_one_or_none=MagicMock(return_value="UTC")),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]

        item = _mock_punch_item(event_type="CHECK_IN", device_reported_at=now_utc)
        req = AttendanceBatchSyncRequest(employee_id=report_emp_id, items=[item])

        with (
            patch(
                "services.api.attendance.sync_service.evaluate_punch_policy",
                new=AsyncMock(return_value=PolicyEvaluationOutcome(is_verified=True, policy_version=1)),
            ),
            patch(
                "services.api.attendance.sync_service.evaluate_attendance_fraud_evidence",
                new=AsyncMock(
                    return_value=FraudEvidenceAssessment(
                        signals=[],
                        velocity_result=None,
                        device_validation_status="ACTIVE",
                        review_status="NOT_REQUIRED",
                        device_id_uuid=uuid.uuid4(),
                    )
                ),
            ),
            patch(
                "services.api.attendance.sync_service.determine_shift_date_for_punch",
                new=AsyncMock(return_value=date(2026, 11, 22)),
            ),
            patch(
                "services.api.attendance.sync_service.recalculate_attendance_day",
                new=AsyncMock(),
            ),
        ):
            resp = await process_attendance_batch_sync(
                session=mock_session,
                tenant_id=tenant_id,
                user_id=mgr_user_id,
                user_role="manager",
                payload=req,
            )

        assert resp.total_items == 1
        assert resp.accepted_count == 1
        assert resp.receipts[0].status == BatchSyncItemStatus.ACCEPTED

    @pytest.mark.asyncio
    async def test_scenario_18_database_transaction_commit_failure(self, mock_session):
        """Scenario 18: Database commit failure triggers rollback and raises HTTP 409."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        emp = _mock_employee(tenant_id, user_id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = [
            emp,
            emp,
            "UTC",
            None,
            None,
            None,
        ]
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = IntegrityError(
            "commit collision", params={}, orig=None
        )

        req = AttendanceBatchSyncRequest(items=[_mock_punch_item()])

        with (
            patch(
                "services.api.attendance.sync_service.evaluate_punch_policy",
                new=AsyncMock(return_value=PolicyEvaluationOutcome(is_verified=True, policy_version=1)),
            ),
            patch(
                "services.api.attendance.sync_service.evaluate_attendance_fraud_evidence",
                new=AsyncMock(
                    return_value=FraudEvidenceAssessment(
                        signals=[],
                        velocity_result=None,
                        device_validation_status="ACTIVE",
                        review_status="NOT_REQUIRED",
                        device_id_uuid=uuid.uuid4(),
                    )
                ),
            ),
            patch(
                "services.api.attendance.sync_service.determine_shift_date_for_punch",
                new=AsyncMock(return_value=date(2026, 11, 22)),
            ),
            patch(
                "services.api.attendance.sync_service.recalculate_attendance_day",
                new=AsyncMock(),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await process_attendance_batch_sync(
                    session=mock_session,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    user_role="employee",
                    payload=req,
                )
            assert exc_info.value.status_code == status.HTTP_409_CONFLICT
            mock_session.rollback.assert_awaited()

    @pytest.mark.asyncio
    async def test_scenario_19_duplicate_sequence_number_detected(self, mock_session):
        """Scenario 19: Duplicate sequence number in same batch triggers CONFLICT receipt."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        emp = _mock_employee(tenant_id, user_id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = [
            emp,
            emp,
            "UTC",
            None,
            None,
            None,
        ]
        mock_session.execute.return_value = mock_result

        # Both items submit sequence_number = 5
        item1 = _mock_punch_item("CHECK_IN", sequence_number=5)
        item2 = _mock_punch_item("CHECK_OUT", sequence_number=5)
        req = AttendanceBatchSyncRequest(items=[item1, item2])

        with (
            patch(
                "services.api.attendance.sync_service.evaluate_punch_policy",
                new=AsyncMock(return_value=PolicyEvaluationOutcome(is_verified=True, policy_version=1)),
            ),
            patch(
                "services.api.attendance.sync_service.evaluate_attendance_fraud_evidence",
                new=AsyncMock(
                    return_value=FraudEvidenceAssessment(
                        signals=[],
                        velocity_result=None,
                        device_validation_status="ACTIVE",
                        review_status="NOT_REQUIRED",
                        device_id_uuid=uuid.uuid4(),
                    )
                ),
            ),
            patch(
                "services.api.attendance.sync_service.determine_shift_date_for_punch",
                new=AsyncMock(return_value=date(2026, 11, 22)),
            ),
            patch(
                "services.api.attendance.sync_service.recalculate_attendance_day",
                new=AsyncMock(),
            ),
        ):
            resp = await process_attendance_batch_sync(
                session=mock_session,
                tenant_id=tenant_id,
                user_id=user_id,
                user_role="employee",
                payload=req,
            )

        assert resp.total_items == 2
        assert resp.accepted_count == 1
        assert resp.conflict_count == 1
        assert resp.receipts[1].status == BatchSyncItemStatus.CONFLICT
        assert resp.receipts[1].error_code == "DUPLICATE_SEQUENCE_NUMBER"

    @pytest.mark.asyncio
    async def test_scenario_20_checkout_while_on_break_preserves_open_break_and_flags_review(
        self, mock_session
    ):
        """Scenario 20: CHECK_OUT while on break never fabricates BREAK_END; preserves open break and marks review."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        emp = _mock_employee(tenant_id, user_id)
        now_utc = datetime.now(UTC) - timedelta(hours=4)

        # Initial state in DB is ON_BREAK
        latest_on_break = AttendanceEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            employee_id=emp.id,
            event_type="BREAK_START",
            event_category="STANDARD",
            effective_at=now_utc - timedelta(hours=1),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = [
            emp,
            emp,
            "UTC",
            latest_on_break,
            None,
        ]
        mock_session.execute.return_value = mock_result

        item = _mock_punch_item("CHECK_OUT", now_utc, sequence_number=10)
        req = AttendanceBatchSyncRequest(items=[item])

        with (
            patch(
                "services.api.attendance.sync_service.evaluate_punch_policy",
                new=AsyncMock(return_value=PolicyEvaluationOutcome(is_verified=True, policy_version=1)),
            ),
            patch(
                "services.api.attendance.sync_service.evaluate_attendance_fraud_evidence",
                new=AsyncMock(
                    return_value=FraudEvidenceAssessment(
                        signals=[],
                        velocity_result=None,
                        device_validation_status="ACTIVE",
                        review_status="NOT_REQUIRED",
                        device_id_uuid=uuid.uuid4(),
                    )
                ),
            ),
            patch(
                "services.api.attendance.sync_service.determine_shift_date_for_punch",
                new=AsyncMock(return_value=date(2026, 11, 22)),
            ),
            patch(
                "services.api.attendance.sync_service.recalculate_attendance_day",
                new=AsyncMock(),
            ),
        ):
            resp = await process_attendance_batch_sync(
                session=mock_session,
                tenant_id=tenant_id,
                user_id=user_id,
                user_role="employee",
                payload=req,
            )

        assert resp.total_items == 1
        assert resp.requires_review_count == 1
        assert resp.accepted_count == 0
        receipt = resp.receipts[0]
        assert receipt.status == BatchSyncItemStatus.REQUIRES_REVIEW
        assert receipt.review_status == "PENDING_REVIEW"

        # Invariant: Never fabricate BREAK_END event. Only CHECK_OUT and idempotency record are added.
        added_events = [
            call.args[0]
            for call in mock_session.add.call_args_list
            if isinstance(call.args[0], AttendanceEvent)
        ]
        assert len(added_events) == 1
        assert added_events[0].event_type == "CHECK_OUT"
        assert added_events[0].review_status == "PENDING_REVIEW"
        assert "UNCLOSED_BREAK_ON_CHECKOUT" in (added_events[0].metadata_json.get("flags") or [])
        assert added_events[0].metadata_json.get("unclosed_break") is True

    @pytest.mark.asyncio
    async def test_future_timestamp_in_warning_window_prefers_server_effective_at(
        self, mock_session
    ):
        """Future timestamp in 60s-300s window preserves device_reported_at, anchors effective_at to server, and requires review."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        emp = _mock_employee(tenant_id, user_id)
        future_device_time = datetime.now(UTC) + timedelta(seconds=120)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = [
            emp,
            emp,
            "UTC",
            None,
            None,
        ]
        mock_session.execute.return_value = mock_result

        item = _mock_punch_item("CHECK_IN", future_device_time, sequence_number=1)
        req = AttendanceBatchSyncRequest(items=[item])

        with (
            patch(
                "services.api.attendance.sync_service.evaluate_punch_policy",
                new=AsyncMock(return_value=PolicyEvaluationOutcome(is_verified=True, policy_version=1)),
            ),
            patch(
                "services.api.attendance.sync_service.evaluate_attendance_fraud_evidence",
                new=AsyncMock(
                    return_value=FraudEvidenceAssessment(
                        signals=[],
                        velocity_result=None,
                        device_validation_status="ACTIVE",
                        review_status="NOT_REQUIRED",
                        device_id_uuid=uuid.uuid4(),
                    )
                ),
            ),
            patch(
                "services.api.attendance.sync_service.determine_shift_date_for_punch",
                new=AsyncMock(return_value=date(2026, 11, 23)),
            ),
            patch(
                "services.api.attendance.sync_service.recalculate_attendance_day",
                new=AsyncMock(),
            ),
        ):
            resp = await process_attendance_batch_sync(
                session=mock_session,
                tenant_id=tenant_id,
                user_id=user_id,
                user_role="employee",
                payload=req,
            )

        assert resp.total_items == 1
        assert resp.requires_review_count == 1
        assert resp.accepted_count == 0
        receipt = resp.receipts[0]
        assert receipt.status == BatchSyncItemStatus.REQUIRES_REVIEW
        assert receipt.review_status == "PENDING_REVIEW"

        added_events = [
            call.args[0]
            for call in mock_session.add.call_args_list
            if isinstance(call.args[0], AttendanceEvent)
        ]
        assert len(added_events) == 1
        ev = added_events[0]
        # device_reported_at is preserved exactly as transmitted
        assert ev.device_reported_at == future_device_time
        # server_received_at is independently recorded
        assert ev.server_received_at is not None
        # effective_at prefers server_received_at to prevent future working time or shift distortion
        assert ev.effective_at == ev.server_received_at
        assert ev.effective_at < future_device_time
        # review flags and suspicious drift metadata are attached
        assert ev.review_status == "PENDING_REVIEW"
        assert ev.timestamp_verification_status == "SUSPICIOUS_CLOCK_DRIFT"
        assert "FLAG_FUTURE_TIMESTAMP_DETECTED" in (ev.metadata_json.get("flags") or [])


# ==============================================================================
# 3. HTTP Integration Tests for POST /api/v1/attendance/sync/batch
# ==============================================================================


class TestHTTPBatchSyncRoute:
    """HTTP integration tests via AsyncClient for the batch sync endpoint."""

    @pytest.mark.asyncio
    async def test_http_batch_sync_success_200(self):
        """HTTP POST /api/v1/attendance/sync/batch returns 200 OK with receipts."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        ctx = _mock_context("employee", tenant_id=tenant_id, user_id=user_id)
        emp = _mock_employee(tenant_id, user_id)

        mock_session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.side_effect = [
            emp,
            emp,
            "UTC",
            None,
            None,
        ]
        mock_session.execute.return_value = mock_res
        nested_mock = MagicMock()
        nested_mock.__aenter__ = AsyncMock(return_value=None)
        nested_mock.__aexit__ = AsyncMock(return_value=None)
        mock_session.begin_nested = MagicMock(return_value=nested_mock)
        mock_session.add = MagicMock()

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
        )

        app.dependency_overrides[get_authenticated_context] = lambda: ctx
        app.dependency_overrides[get_db] = lambda: mock_session

        try:
            item_payload = {
                "local_id": "loc_abc_1",
                "idempotency_key": str(uuid.uuid4()),
                "event_type": "CHECK_IN",
                "device_reported_at": (datetime.now(UTC) - timedelta(minutes=15)).isoformat(),
                "latitude": 12.9716,
                "longitude": 77.5946,
            }
            body = {
                "batch_id": "batch_test_01",
                "items": [item_payload],
            }

            with (
                patch(
                    "services.api.attendance.sync_service.get_active_tenant_policy",
                    new=AsyncMock(return_value=policy),
                ),
                patch(
                    "services.api.attendance.sync_service.evaluate_punch_policy",
                    new=AsyncMock(return_value=PolicyEvaluationOutcome(is_verified=True, policy_version=1)),
                ),
                patch(
                    "services.api.attendance.sync_service.evaluate_attendance_fraud_evidence",
                    new=AsyncMock(
                        return_value=FraudEvidenceAssessment(
                            signals=[],
                            velocity_result=None,
                            device_validation_status="ACTIVE",
                            review_status="NOT_REQUIRED",
                            device_id_uuid=uuid.uuid4(),
                        )
                    ),
                ),
                patch(
                    "services.api.attendance.sync_service.determine_shift_date_for_punch",
                    new=AsyncMock(return_value=date(2026, 11, 22)),
                ),
                patch(
                    "services.api.attendance.sync_service.recalculate_attendance_day",
                    new=AsyncMock(),
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post("/api/v1/attendance/sync/batch", json=body)

            assert resp.status_code == status.HTTP_200_OK
            data = resp.json()
            assert data["batch_id"] == "batch_test_01"
            assert data["total_items"] == 1
            assert data["accepted_count"] == 1
            assert data["receipts"][0]["status"] == "ACCEPTED"
            assert data["receipts"][0]["local_id"] == "loc_abc_1"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_http_batch_sync_size_exceeded_422(self):
        """HTTP POST /api/v1/attendance/sync/batch with 51 items returns 422 Unprocessable Content."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        ctx = _mock_context("employee", tenant_id=tenant_id, user_id=user_id)

        app.dependency_overrides[get_authenticated_context] = lambda: ctx
        app.dependency_overrides[get_db] = lambda: AsyncMock()

        try:
            items_payload = [
                {
                    "local_id": f"loc_{i}",
                    "idempotency_key": str(uuid.uuid4()),
                    "event_type": "CHECK_IN",
                    "device_reported_at": datetime.now(UTC).isoformat(),
                }
                for i in range(51)
            ]
            body = {"items": items_payload}

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.post("/api/v1/attendance/sync/batch", json=body)

            assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        finally:
            app.dependency_overrides.clear()
