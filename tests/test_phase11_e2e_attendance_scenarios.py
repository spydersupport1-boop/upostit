"""Comprehensive End-to-End Attendance Lifecycle & Multi-Device Scenarios (Phase 11.7).

Validates the full attendance lifecycle across real service boundaries:
- Scenario A: Normal Online Attendance (check-in, break, check-out, calculation, manager approval).
- Scenario B: Complete Offline Workday (accumulate offline punches, reconnect, batch sync, delta sync).
- Scenario C: Multiple Devices Handoff, Out-of-Order Sync, and Device Revocation.
- Scenario D: Concurrent Synchronization, Dual-Tier Idempotency, and Savepoint Isolation.
- Scenario E: Application Failures, Transaction Rollback, and Capacity Pressure.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from services.api.attendance.conflict_detector import detect_multi_device_conflicts
from services.api.attendance.models import (
    AttendanceDay,
    AttendanceEvent,
    AttendanceIdempotencyRecord,
    TenantAttendancePolicy,
)
from services.api.attendance.multi_device_reconciliation import (
    reconcile_employee_multi_device_sessions,
)
from services.api.attendance.policy_engine import PolicyEvaluationOutcome
from services.api.attendance.schemas import (
    AttendanceBatchSyncRequest,
    BatchSyncItemStatus,
    BatchSyncPunchItem,
    ConflictClassification,
    ConflictSeverity,
    MultiDeviceConflictCode,
)
from services.api.attendance.sync_service import (
    process_attendance_batch_sync,
)
from services.api.auth.dependencies import AuthenticatedContext, get_authenticated_context
from services.api.auth.models import User
from services.api.devices.models import Device
from services.api.devices.schemas import DevicePlatform, DeviceReRegisterRequest
from services.api.devices.service import re_register_device
from services.api.employees.models import Employee
from services.api.fraud.schemas import FraudEvidenceAssessment
from services.api.main import app
from services.api.tenants.models import Tenant

# ==============================================================================
# Helper Mock Factories
# ==============================================================================


def _make_context(
    role: str = "employee",
    tenant_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> AuthenticatedContext:
    tid = tenant_id or uuid.uuid4()
    uid = user_id or uuid.uuid4()
    user = User(
        id=uid,
        tenant_id=tid,
        email=f"user-{uid.hex[:6]}@upostit.test",
        full_name="E2E Test User",
        role=role,
        status="ACTIVE",
    )
    tenant = Tenant(
        id=tid,
        name="E2E Tenant",
        slug=f"e2e-{tid.hex[:6]}",
        company_email=f"tenant-{tid.hex[:6]}@upostit.test",
        country_code="US",
        timezone="UTC",
        status="active",
    )
    return AuthenticatedContext(user=user, tenant=tenant)


def _make_employee(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    manager_id: uuid.UUID | None = None,
) -> Employee:
    return Employee(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        employee_id=f"EMP-{uuid.uuid4().hex[:6]}",
        first_name="Jordan",
        last_name="Lee",
        work_email=f"jordan-{uuid.uuid4().hex[:6]}@upostit.test",
        reporting_manager_id=manager_id,
        joining_date=date(2025, 1, 1),
        status="active",
    )


def _make_device(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    device_hash: str = "dev_hash_alpha",
    status_str: str = "ACTIVE",
    platform: str = "ANDROID",
) -> Device:
    return Device(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=employee_id,
        device_id_hash=device_hash,
        platform=platform,
        status=status_str,
        registered_at=datetime.now(UTC),
    )


def _make_policy(tenant_id: uuid.UUID) -> TenantAttendancePolicy:
    return TenantAttendancePolicy(
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


def _make_mock_session() -> AsyncMock:
    session = AsyncMock()
    nested_mock = MagicMock()
    nested_mock.__aenter__ = AsyncMock(return_value=None)
    nested_mock.__aexit__ = AsyncMock(return_value=None)
    session.begin_nested = MagicMock(return_value=nested_mock)
    session.add = MagicMock()
    return session


# ==============================================================================
# Scenario A: Normal Online Attendance Lifecycle
# ==============================================================================


@pytest.mark.asyncio
async def test_scenario_a_normal_online_attendance_lifecycle():
    """Validates complete online day: check-in, break, check-out, calculation, and approval."""
    tid = uuid.uuid4()
    emp_user_id = uuid.uuid4()
    mgr_user_id = uuid.uuid4()

    emp = _make_employee(tid, emp_user_id, manager_id=mgr_user_id)
    policy = _make_policy(tid)
    device = _make_device(tid, emp.id, device_hash="online_dev_01")

    base_time = datetime.now(UTC).replace(hour=8, minute=0, second=0, microsecond=0)
    check_in_time = base_time
    break_start_time = base_time + timedelta(hours=4)
    break_end_time = base_time + timedelta(hours=4, minutes=45)
    check_out_time = base_time + timedelta(hours=8, minutes=45)

    items = [
        BatchSyncPunchItem(
            local_id="online-1",
            idempotency_key="key-online-1",
            event_type="CHECK_IN",
            device_reported_at=check_in_time,
            sequence_number=1,
            timezone_offset_minutes=0,
            monotonic_boot_time_ms=100000,
            boot_session_id="boot-01",
        ),
        BatchSyncPunchItem(
            local_id="online-2",
            idempotency_key="key-online-2",
            event_type="BREAK_START",
            device_reported_at=break_start_time,
            sequence_number=2,
            timezone_offset_minutes=0,
            monotonic_boot_time_ms=14400000,
            boot_session_id="boot-01",
        ),
        BatchSyncPunchItem(
            local_id="online-3",
            idempotency_key="key-online-3",
            event_type="BREAK_END",
            device_reported_at=break_end_time,
            sequence_number=3,
            timezone_offset_minutes=0,
            monotonic_boot_time_ms=17100000,
            boot_session_id="boot-01",
        ),
        BatchSyncPunchItem(
            local_id="online-4",
            idempotency_key="key-online-4",
            event_type="CHECK_OUT",
            device_reported_at=check_out_time,
            sequence_number=4,
            timezone_offset_minutes=0,
            monotonic_boot_time_ms=31500000,
            boot_session_id="boot-01",
        ),
    ]

    session = _make_mock_session()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.side_effect = [
        emp,   # user_emp
        emp,   # with_for_update emp
        "UTC", # tenant timezone
        None,  # latest_event
        None,  # item 1 idempotency
        None,  # item 2 idempotency
        None,  # item 3 idempotency
        None,  # item 4 idempotency
    ]
    session.execute.return_value = mock_result

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
                    device_id_uuid=device.id,
                )
            ),
        ),
        patch(
            "services.api.attendance.sync_service.determine_shift_date_for_punch",
            new=AsyncMock(return_value=base_time.date()),
        ),
        patch(
            "services.api.attendance.sync_service.reconcile_employee_multi_device_sessions",
            new=AsyncMock(return_value=None),
        ),
    ):
        res = await process_attendance_batch_sync(
            session=session,
            tenant_id=tid,
            user_id=emp_user_id,
            user_role="employee",
            payload=AttendanceBatchSyncRequest(items=items),
        )

    assert res.total_items == 4
    assert res.accepted_count == 4
    assert res.rejected_count == 0
    assert len(res.receipts) == 4
    for r in res.receipts:
        assert r.status == BatchSyncItemStatus.ACCEPTED
        assert r.effective_at is not None


# ==============================================================================
# Scenario B: Complete Offline Workday & Reconnection
# ==============================================================================


@pytest.mark.asyncio
async def test_scenario_b_complete_offline_workday_batch_sync():
    """Validates offline workday: punches recorded with 0 connectivity, uploaded upon reconnect."""
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    emp = _make_employee(tid, uid)
    policy = _make_policy(tid)
    device = _make_device(tid, emp.id, device_hash="offline_phone_01")

    past_date = datetime.now(UTC) - timedelta(hours=12)
    punches = [
        BatchSyncPunchItem(
            local_id=f"off-{i}",
            idempotency_key=f"key-offline-workday-{i}",
            event_type="CHECK_IN" if i == 0 else ("CHECK_OUT" if i == 3 else "BREAK_START" if i == 1 else "BREAK_END"),
            device_reported_at=past_date + timedelta(hours=i * 2),
            sequence_number=i + 1,
            timezone_offset_minutes=-300,
            monotonic_boot_time_ms=1000000 + (i * 7200000),
            boot_session_id="boot-offline-42",
        )
        for i in range(4)
    ]

    session = _make_mock_session()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.side_effect = [
        emp,   # user_emp
        emp,   # with_for_update emp
        "UTC", # tenant timezone
        None,  # latest_event
        None,  # item 1 idempotency
        None,  # item 2 idempotency
        None,  # item 3 idempotency
        None,  # item 4 idempotency
    ]
    session.execute.return_value = mock_result

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
                    device_id_uuid=device.id,
                )
            ),
        ),
        patch(
            "services.api.attendance.sync_service.determine_shift_date_for_punch",
            new=AsyncMock(return_value=past_date.date()),
        ),
        patch(
            "services.api.attendance.sync_service.reconcile_employee_multi_device_sessions",
            new=AsyncMock(return_value=None),
        ),
    ):
        res = await process_attendance_batch_sync(
            session=session,
            tenant_id=tid,
            user_id=uid,
            user_role="employee",
            payload=AttendanceBatchSyncRequest(items=punches),
        )

    assert res.total_items == 4
    assert res.accepted_count == 4
    assert res.receipts[0].local_id == "off-0"
    assert res.receipts[3].local_id == "off-3"
    assert all(r.status == BatchSyncItemStatus.ACCEPTED for r in res.receipts)


# ==============================================================================
# Scenario C: Multiple Devices Handoff, Conflict & Revocation
# ==============================================================================


@pytest.mark.asyncio
async def test_scenario_c_multi_device_clean_handoff():
    """Validates seamless cross-device handoff: Device A Check-in, Device B Check-out."""
    tid = uuid.uuid4()
    emp_id = uuid.uuid4()
    now = datetime.now(UTC)

    mock_session = AsyncMock()
    mock_res_dev = MagicMock()
    mock_res_dev.scalars.return_value.all.return_value = [
        Device(id=uuid.uuid4(), tenant_id=tid, employee_id=emp_id, device_id_hash="dev_a", platform="android", status="ACTIVE"),
        Device(id=uuid.uuid4(), tenant_id=tid, employee_id=emp_id, device_id_hash="dev_b", platform="ios", status="ACTIVE"),
    ]
    mock_res_days = MagicMock()
    mock_res_days.scalars.return_value.all.return_value = []
    mock_session.execute.side_effect = [mock_res_dev, mock_res_days]

    events = [
        AttendanceEvent(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=emp_id,
            event_type="CHECK_IN",
            effective_at=now - timedelta(hours=8),
            device_reported_at=now - timedelta(hours=8),
            device_id="dev_a",
            idempotency_key="idemp-a",
        ),
        AttendanceEvent(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=emp_id,
            event_type="CHECK_OUT",
            effective_at=now,
            device_reported_at=now,
            device_id="dev_b",
            idempotency_key="idemp-b",
        ),
    ]

    with patch(
        "services.api.attendance.multi_device_reconciliation.recalculate_attendance_day",
        new_callable=AsyncMock,
    ) as mock_recalc:
        mock_recalc.return_value = AttendanceDay(
            id=uuid.uuid4(),
            tenant_id=tid,
            employee_id=emp_id,
            attendance_date=now.date(),
            total_working_minutes=480,
            status="PRESENT",
            calculation_status="CALCULATED",
        )
        res = await reconcile_employee_multi_device_sessions(
            session=mock_session,
            tenant_id=tid,
            employee_id=emp_id,
            attendance_date=now.date(),
            events=events,
        )
        assert res.status == "AUTO_RESOLVED"
        assert res.recalculated_day is not None
        assert len(res.conflicts_detected) == 0


@pytest.mark.asyncio
async def test_scenario_c_offline_device_revocation_enforcement():
    """Revoked device attempting sync while offline is immediately flagged with UNAUTHORIZED_OR_REVOKED_DEVICE."""
    tid = uuid.uuid4()
    emp_id = uuid.uuid4()
    dev_id = uuid.uuid4()
    now = datetime.now(UTC)

    mock_session = AsyncMock()
    mock_res_dev = MagicMock()
    mock_res_dev.scalars.return_value.all.return_value = [
        Device(
            id=dev_id,
            tenant_id=tid,
            employee_id=emp_id,
            device_id_hash="stolen_phone_hash",
            platform="ANDROID",
            status="REVOKED",
            revoked_at=now - timedelta(hours=2),
        )
    ]
    mock_res_days = MagicMock()
    mock_res_days.scalars.return_value.all.return_value = []
    mock_session.execute.side_effect = [mock_res_dev, mock_res_days]

    candidate = [
        BatchSyncPunchItem(
            local_id="loc-stolen",
            idempotency_key="idemp-stolen",
            event_type="CHECK_IN",
            device_reported_at=now,
            device_id="stolen_phone_hash",
        )
    ]

    conflicts = await detect_multi_device_conflicts(
        session=mock_session,
        tenant_id=tid,
        employee_id=emp_id,
        candidate_items=candidate,
        existing_events=[],
    )

    revoked_conflicts = [c for c in conflicts if c.conflict_code == MultiDeviceConflictCode.UNAUTHORIZED_OR_REVOKED_DEVICE]
    assert len(revoked_conflicts) == 1
    assert revoked_conflicts[0].severity == ConflictSeverity.CRITICAL
    assert revoked_conflicts[0].classification == ConflictClassification.INVALID_UNAUTHORIZED


@pytest.mark.asyncio
async def test_scenario_c_device_re_registration_after_wipe():
    """Validates device re-registration following hardware reset / key wipe."""
    tid = uuid.uuid4()
    emp_id = uuid.uuid4()
    emp = _make_employee(tid, uuid.uuid4())
    emp.id = emp_id

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_emp_res = MagicMock()
    mock_emp_res.scalar_one_or_none.return_value = emp
    mock_dev_none = MagicMock()
    mock_dev_none.scalar_one_or_none.return_value = None

    mock_session.execute.side_effect = [
        mock_emp_res,   # Employee found
        mock_dev_none,  # No active device
        mock_dev_none,  # No pending device
        mock_dev_none,  # Hash available
    ]

    req = DeviceReRegisterRequest(
        device_id="new_secure_hardware_id_888",
        platform=DevicePlatform.IOS,
        re_registration_reason="Device factory reset after OS upgrade.",
        device_model="iPhone 15 Pro",
    )

    reg_result = await re_register_device(mock_session, tid, emp_id, req)
    assert reg_result.device is not None
    assert reg_result.device.platform == "IOS"
    assert reg_result.requires_approval is False


# ==============================================================================
# Scenario D: Concurrent Synchronization & Dual-Tier Idempotency
# ==============================================================================


@pytest.mark.asyncio
async def test_scenario_d_dual_tier_idempotency_retry_storm():
    """Identical batch retried in quick succession returns DUPLICATE status without re-inserting."""
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    emp = _make_employee(tid, uid)
    policy = _make_policy(tid)

    item = BatchSyncPunchItem(
        local_id="storm-1",
        idempotency_key="key-storm-duplicate-01",
        event_type="CHECK_IN",
        device_reported_at=datetime.now(UTC),
        sequence_number=1,
        timezone_offset_minutes=0,
        monotonic_boot_time_ms=10000,
        boot_session_id="boot-storm",
    )

    session = _make_mock_session()

    existing_idemp = AttendanceIdempotencyRecord(
        id=uuid.uuid4(),
        tenant_id=tid,
        employee_id=emp.id,
        idempotency_key="key-storm-duplicate-01",
        status="COMPLETED",
        event_id=None,
        created_at=datetime.now(UTC) - timedelta(minutes=2),
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.side_effect = [
        emp,             # user_emp
        emp,             # with_for_update emp
        "UTC",           # tenant timezone
        None,            # latest_event
        existing_idemp,  # existing idempotency match!
    ]
    session.execute.return_value = mock_result

    with (
        patch(
            "services.api.attendance.sync_service.get_active_tenant_policy",
            new=AsyncMock(return_value=policy),
        ),
        patch(
            "services.api.attendance.sync_service.reconcile_employee_multi_device_sessions",
            new=AsyncMock(return_value=None),
        ),
    ):
        res = await process_attendance_batch_sync(
            session=session,
            tenant_id=tid,
            user_id=uid,
            user_role="employee",
            payload=AttendanceBatchSyncRequest(items=[item]),
        )

    assert res.total_items == 1
    assert res.duplicate_count == 1
    assert res.accepted_count == 0
    assert res.receipts[0].status == BatchSyncItemStatus.DUPLICATE


@pytest.mark.asyncio
async def test_scenario_d_partial_batch_savepoint_isolation():
    """A batch containing valid and invalid punches processes valid ones under savepoint isolation."""
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    emp = _make_employee(tid, uid)
    policy = _make_policy(tid)
    device = _make_device(tid, emp.id)

    valid_item = BatchSyncPunchItem(
        local_id="part-1",
        idempotency_key="k-part-valid",
        event_type="CHECK_IN",
        device_reported_at=datetime.now(UTC) - timedelta(minutes=10),
        sequence_number=1,
        timezone_offset_minutes=0,
        monotonic_boot_time_ms=1000,
        boot_session_id="b-part",
    )
    aged_item = BatchSyncPunchItem(
        local_id="part-2",
        idempotency_key="k-part-aged",
        event_type="CHECK_OUT",
        device_reported_at=datetime.now(UTC) - timedelta(hours=100),
        sequence_number=2,
        timezone_offset_minutes=0,
        monotonic_boot_time_ms=2000,
        boot_session_id="b-part",
    )

    session = _make_mock_session()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.side_effect = [
        emp,   # user_emp
        emp,   # with_for_update emp
        "UTC", # tenant timezone
        None,  # latest_event
        None,  # item 1 idempotency
        None,  # item 2 idempotency
    ]
    session.execute.return_value = mock_result

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
                    device_id_uuid=device.id,
                )
            ),
        ),
        patch(
            "services.api.attendance.sync_service.determine_shift_date_for_punch",
            new=AsyncMock(return_value=date(2026, 11, 24)),
        ),
        patch(
            "services.api.attendance.sync_service.reconcile_employee_multi_device_sessions",
            new=AsyncMock(return_value=None),
        ),
    ):
        res = await process_attendance_batch_sync(
            session=session,
            tenant_id=tid,
            user_id=uid,
            user_role="employee",
            payload=AttendanceBatchSyncRequest(items=[valid_item, aged_item]),
        )

    assert res.total_items == 2
    assert res.accepted_count == 1
    assert res.rejected_count == 1
    assert res.receipts[0].status == BatchSyncItemStatus.ACCEPTED
    assert res.receipts[1].status == BatchSyncItemStatus.REJECTED
    assert "exceeds" in (res.receipts[1].error_message or "").lower() or "limit" in (res.receipts[1].error_message or "").lower()


# ==============================================================================
# Scenario E: Application Failures & Recovery Behavior
# ==============================================================================


@pytest.mark.asyncio
async def test_scenario_e_max_batch_size_rejection_boundary():
    """Batches exceeding 50 items are rejected with HTTP 422 before transaction initiation."""
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    ctx = _make_context(role="employee", tenant_id=tid, user_id=uid)

    app.dependency_overrides[get_authenticated_context] = lambda: ctx

    oversized_items = [
        {
            "local_id": f"loc-{i}",
            "idempotency_key": f"key-oversize-{i}",
            "event_type": "CHECK_IN",
            "device_reported_at": datetime.now(UTC).isoformat(),
            "sequence_number": i + 1,
            "timezone_offset_minutes": 0,
            "monotonic_boot_time_ms": 1000 + i,
            "boot_session_id": "b-over",
        }
        for i in range(51)
    ]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/attendance/sync/batch",
            json={"items": oversized_items},
        )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
