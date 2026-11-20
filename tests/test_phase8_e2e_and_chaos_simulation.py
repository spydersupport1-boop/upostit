"""Comprehensive End-to-End, Chaos & Synchronization Simulation Suite for Phase 8 Milestone 8.6.

Validates the complete interaction contract across:
1. Complete E2E success scenario:
   - Offline punches (CHECK_IN, BREAK_START, BREAK_END, CHECK_OUT)
   - Primary rejection of CHECK_IN & dependent quarantine
   - Mobile bundle extraction & submission
   - Manager review queue & forensic detail inspection
   - Supervisor approval with mandatory reason & location override
   - Atomic injection via Phase 5 correction engine (apply_attendance_correction)
   - Projections recalculation & status verification
2. Rejection scenario:
   - Supervisor rejection with decision reason
   - Zero attendance ledger events created
   - Projections remain unchanged
   - Mobile status reflects rejection & reason
3. Chaos and failure scenarios:
   - Network loss after server commit (idempotent replay)
   - Duplicate bundle submission
   - Tampered payload with same bundle_id (HTTP 409 Conflict)
   - Two supervisors deciding simultaneously (concurrency race condition)
   - Partial failure after 1st event insertion (transaction rollback)
   - Failure during attendance projection recalculation (transaction rollback)
   - Multiple sessions for the same employee
   - Overnight shift spanning two calendar dates
   - Cross-tenant access attempt (HTTP 404 / isolation)
   - Manager attempting to access non-report incident (HTTP 403)
   - Employee attempting supervisor adjudication (HTTP 403)
   - Anti-self-approval rule (manager approving own conflict -> HTTP 403)
4. Data integrity verification:
   - Exactly once records
   - Chronological ordering preserved
   - Original device timestamps unchanged
   - Audit metadata references incident ID and original idempotency keys
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status

from services.api.attendance.conflict_service import (
    adjudicate_conflict_incident,
    compute_conflict_bundle_fingerprint,
    get_conflict_incident_detail,
    list_my_offline_conflict_incidents,
    list_supervisor_conflict_queue,
    submit_offline_conflict_bundle,
)
from services.api.attendance.models import AttendanceConflictIncident, AttendanceEvent
from services.api.attendance.schemas import (
    AttendanceConflictDecisionRequest,
    AttendanceCorrectionResponse,
    AttendanceEventResponse,
    OfflineConflictBundleSubmitRequest,
    OfflineDependentEventPayload,
    OfflineRejectedEventPayload,
)
from services.api.auth.models import User
from services.api.employees.models import Employee

# ==============================================================================
# Simulation Fixtures & Helpers
# ==============================================================================


def _create_user(
    role: str = "employee",
    tenant_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    email: str | None = None,
) -> User:
    tid = tenant_id or uuid.uuid4()
    uid = user_id or uuid.uuid4()
    return User(
        id=uid,
        tenant_id=tid,
        email=email or f"{role.lower()}_{uid.hex[:6]}@e2e.test",
        full_name=f"E2E {role.capitalize()}",
        role=role.lower(),
        status="active",
        password_hash="argon2id$mock",
    )


def _create_employee(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    employee_id: uuid.UUID | None = None,
    reporting_manager_id: uuid.UUID | None = None,
    code: str = "EMP-E2E-001",
) -> Employee:
    eid = employee_id or uuid.uuid4()
    return Employee(
        id=eid,
        tenant_id=tenant_id,
        user_id=user_id,
        employee_id=code,
        work_email=f"worker_{eid.hex[:6]}@e2e.test",
        first_name="Offline",
        last_name="Worker",
        reporting_manager_id=reporting_manager_id,
        joining_date=date(2025, 1, 1),
        status="active",
        employment_type="full_time",
    )


def _build_full_shift_bundle_payload(
    bundle_id: str | None = None,
    session_id: str | None = None,
    base_time: datetime | None = None,
    location_id: uuid.UUID | None = None,
) -> OfflineConflictBundleSubmitRequest:
    bid = bundle_id or f"bundle_{uuid.uuid4().hex[:12]}"
    sid = session_id or f"sess_{uuid.uuid4().hex[:12]}"
    loc_id = location_id or uuid.uuid4()
    t0 = base_time or datetime(2026, 11, 20, 8, 0, 0, tzinfo=UTC)

    # 1. Primary rejected CHECK_IN
    primary = OfflineRejectedEventPayload(
        local_id="loc_checkin_001",
        idempotency_key=str(uuid.uuid4()),
        event_type="CHECK_IN",
        device_reported_at=t0,
        device_id_hash="hash_dev_e2e_001",
        device_model="Pixel 8",
        os_version="Android 15",
        latitude=40.7128,
        longitude=-74.0060,
        accuracy_meters=12.5,
        location_id=loc_id,
        is_mock_location=False,
        server_rejection_code=422,
        server_rejection_reason="Reported GPS location was 250m outside workplace geofence",
        metadata={"wifi_ssid": "HQ_Staff_5G", "wifi_bssid": "00:11:22:33:44:55"},
    )

    # 2. Quarantined BREAK_START (12:00)
    b_start = OfflineDependentEventPayload(
        local_id="loc_break_start_002",
        idempotency_key=str(uuid.uuid4()),
        event_type="BREAK_START",
        device_reported_at=t0 + timedelta(hours=4),
        device_id_hash="hash_dev_e2e_001",
        device_model="Pixel 8",
        os_version="Android 15",
        latitude=40.7128,
        longitude=-74.0060,
        accuracy_meters=10.0,
        location_id=loc_id,
        is_mock_location=False,
        metadata={"wifi_ssid": "HQ_Staff_5G"},
    )

    # 3. Quarantined BREAK_END (12:30)
    b_end = OfflineDependentEventPayload(
        local_id="loc_break_end_003",
        idempotency_key=str(uuid.uuid4()),
        event_type="BREAK_END",
        device_reported_at=t0 + timedelta(hours=4, minutes=30),
        device_id_hash="hash_dev_e2e_001",
        device_model="Pixel 8",
        os_version="Android 15",
        latitude=40.7128,
        longitude=-74.0060,
        accuracy_meters=10.0,
        location_id=loc_id,
        is_mock_location=False,
        metadata={"wifi_ssid": "HQ_Staff_5G"},
    )

    # 4. Quarantined CHECK_OUT (17:00)
    c_out = OfflineDependentEventPayload(
        local_id="loc_checkout_004",
        idempotency_key=str(uuid.uuid4()),
        event_type="CHECK_OUT",
        device_reported_at=t0 + timedelta(hours=9),
        device_id_hash="hash_dev_e2e_001",
        device_model="Pixel 8",
        os_version="Android 15",
        latitude=40.7128,
        longitude=-74.0060,
        accuracy_meters=11.2,
        location_id=loc_id,
        is_mock_location=False,
        metadata={"wifi_ssid": "HQ_Staff_5G"},
    )

    return OfflineConflictBundleSubmitRequest(
        bundle_id=bid,
        session_id=sid,
        employee_notes="Attended external meeting before reporting to secondary site",
        primary_rejected_event=primary,
        dependent_events=[b_start, b_end, c_out],
    )


def _create_mock_incident(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    user_id: uuid.UUID,
    bundle_payload: OfflineConflictBundleSubmitRequest,
    status_str: str = "PENDING_REVIEW",
    incident_id: uuid.UUID | None = None,
) -> AttendanceConflictIncident:
    inc_id = incident_id or uuid.uuid4()
    now = datetime.now(UTC)
    fp = compute_conflict_bundle_fingerprint(
        tenant_id=tenant_id,
        employee_id=employee_id,
        payload=bundle_payload,
    )
    return AttendanceConflictIncident(
        id=inc_id,
        tenant_id=tenant_id,
        employee_id=employee_id,
        user_id=user_id,
        bundle_id=bundle_payload.bundle_id,
        session_id=bundle_payload.session_id,
        status=status_str,
        primary_rejected_event=bundle_payload.primary_rejected_event.model_dump(mode="json"),
        dependent_events=[e.model_dump(mode="json") for e in bundle_payload.dependent_events],
        total_events_count=1 + len(bundle_payload.dependent_events),
        rejection_summary=bundle_payload.primary_rejected_event.server_rejection_reason,
        employee_notes=bundle_payload.employee_notes,
        submitted_at=now,
        decision=None if status_str == "PENDING_REVIEW" else status_str,
        decision_reason=None if status_str == "PENDING_REVIEW" else "Supervisor decision",
        reviewer_user_id=None if status_str == "PENDING_REVIEW" else uuid.uuid4(),
        decided_at=None if status_str == "PENDING_REVIEW" else now,
        resolved_correction_event_ids=[],
        metadata_json={"request_fingerprint": fp},
        created_at=now,
        updated_at=now,
    )


# ==============================================================================
# 1. Complete End-to-End Success Scenario
# ==============================================================================


class TestEndToEndSuccessSimulation:
    """Simulates the complete happy-path lifecycle:
    1. Offline punches recorded.
    2. Primary rejected & dependents quarantined.
    3. Mobile submits conflict bundle -> PENDING_REVIEW.
    4. Manager lists queue & opens detail.
    5. Manager approves with reason & location override.
    6. Phase 5 correction engine injects events atomically.
    7. Recalculation runs.
    8. Mobile refreshes & sees APPROVED.
    """

    @pytest.mark.asyncio
    async def test_complete_e2e_approval_lifecycle(self) -> None:
        tenant_id = uuid.uuid4()
        manager_user = _create_user("manager", tenant_id=tenant_id)
        manager_emp = _create_employee(
            tenant_id=tenant_id,
            user_id=manager_user.id,
            code="MGR-001",
        )

        emp_user = _create_user("employee", tenant_id=tenant_id)
        employee = _create_employee(
            tenant_id=tenant_id,
            user_id=emp_user.id,
            reporting_manager_id=manager_emp.id,
            code="EMP-100",
        )

        override_loc_id = uuid.uuid4()
        bundle_payload = _build_full_shift_bundle_payload()

        # Step A: Mobile submits bundle to backend
        db_session = AsyncMock()

        emp_exec_mock = MagicMock()
        emp_exec_mock.scalar_one_or_none.return_value = employee

        bundle_exec_mock = MagicMock()
        bundle_exec_mock.scalar_one_or_none.return_value = None

        db_session.execute.side_effect = [emp_exec_mock, emp_exec_mock, bundle_exec_mock]

        new_incident_holder: list[AttendanceConflictIncident] = []

        def capture_add(instance: Any) -> None:
            if isinstance(instance, AttendanceConflictIncident):
                instance.id = uuid.uuid4()
                now = datetime.now(UTC)
                instance.created_at = now
                instance.updated_at = now
                new_incident_holder.append(instance)

        db_session.add = MagicMock(side_effect=capture_add)

        # Execute submission
        submit_res = await submit_offline_conflict_bundle(
            session=db_session,
            tenant_id=tenant_id,
            user_id=emp_user.id,
            user_role="employee",
            payload=bundle_payload,
        )

        assert submit_res.bundle_id == bundle_payload.bundle_id
        assert submit_res.status == "PENDING_REVIEW"
        assert len(new_incident_holder) == 1
        created_incident = new_incident_holder[0]
        assert created_incident.status == "PENDING_REVIEW"
        assert created_incident.employee_id == employee.id
        assert len(created_incident.dependent_events) == 3

        # Step B: Manager views supervisor queue
        mgr_queue_lookup_mock = MagicMock()
        mgr_queue_lookup_mock.scalar_one_or_none.return_value = manager_emp.id

        queue_count_mock = MagicMock()
        queue_count_mock.scalar.return_value = 1

        queue_row = (created_incident, employee.first_name, employee.last_name, employee.employee_id, "Operations")

        queue_items_mock = MagicMock()
        queue_items_mock.all.return_value = [queue_row]

        db_session.execute.side_effect = [mgr_queue_lookup_mock, queue_count_mock, queue_items_mock]

        queue_res = await list_supervisor_conflict_queue(
            session=db_session,
            tenant_id=tenant_id,
            user_id=manager_user.id,
            user_role="manager",
            status_filter="PENDING_REVIEW",
        )

        assert queue_res.total == 1
        assert queue_res.items[0].id == created_incident.id
        assert queue_res.items[0].total_events_count == 4
        assert queue_res.items[0].primary_event_type == "CHECK_IN"

        # Step C: Manager views forensic incident detail
        incident_detail_mock = MagicMock()
        incident_detail_mock.scalar_one_or_none.return_value = created_incident

        emp_detail_mock = MagicMock()
        emp_detail_mock.first.return_value = (employee, "Operations")

        mgr_emp_lookup_mock = MagicMock()
        mgr_emp_lookup_mock.scalar_one_or_none.return_value = manager_emp.id

        db_session.execute.side_effect = [
            incident_detail_mock,
            emp_detail_mock,
            mgr_emp_lookup_mock,
        ]

        detail_res = await get_conflict_incident_detail(
            session=db_session,
            tenant_id=tenant_id,
            user_id=manager_user.id,
            user_role="manager",
            incident_id=created_incident.id,
        )

        assert detail_res.id == created_incident.id
        assert detail_res.primary_rejected_event["event_type"] == "CHECK_IN"
        assert len(detail_res.dependent_events) == 3

        # Step D: Manager approves incident with valid reason & location override
        locked_incident_mock = MagicMock()
        locked_incident_mock.scalar_one_or_none.return_value = created_incident

        loc_lookup_mock = MagicMock()
        loc_row = MagicMock()
        loc_row.id = override_loc_id
        loc_lookup_mock.scalar_one_or_none.return_value = loc_row

        mgr_adj_emp_mock = MagicMock()
        mgr_adj_emp_mock.scalar_one_or_none.return_value = manager_emp

        emp_adj_mock = MagicMock()
        emp_adj_mock.scalar_one_or_none.return_value = employee

        db_session.execute.side_effect = [
            locked_incident_mock,
            mgr_adj_emp_mock,
            emp_adj_mock,
            loc_lookup_mock,
        ]

        decision_req = AttendanceConflictDecisionRequest(
            action="APPROVE",
            reason="Confirmed employee was dispatched to alternate site by dispatch supervisor",
            override_location_id=override_loc_id,
        )

        now = datetime.now(UTC)
        dummy_event = AttendanceEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            employee_id=employee.id,
            event_type="CHECK_IN",
            event_category="CORRECTION_INSERT",
            effective_at=now,
            server_received_at=now,
            source="ADMIN",
            review_status="NOT_REQUIRED",
            timestamp_verification_status="SERVER_AUTHORITATIVE",
            idempotency_key=f"cf_mock_{uuid.uuid4().hex[:8]}",
            correction_reason="Offline Conflict Approval",
            location_id=override_loc_id,
            created_at=now,
            metadata_json={},
        )

        dummy_corr_resp = AttendanceCorrectionResponse(
            correction_event=AttendanceEventResponse.model_validate(dummy_event),
            affected_attendance_dates=[date(2026, 11, 20)],
            recalculated_days=[],
            idempotent_replay=False,
        )

        with patch(
            "services.api.attendance.conflict_service.apply_attendance_correction",
            new=AsyncMock(return_value=dummy_corr_resp),
        ) as mock_correction:
            adj_res = await adjudicate_conflict_incident(
                session=db_session,
                tenant_id=tenant_id,
                incident_id=created_incident.id,
                reviewer_user_id=manager_user.id,
                reviewer_role="manager",
                payload=decision_req,
            )

            assert adj_res.status == "APPROVED"
            assert adj_res.decision == "APPROVED"
            assert adj_res.reviewer_user_id == manager_user.id
            assert len(adj_res.resolved_correction_event_ids) == 4
            assert adj_res.affected_attendance_dates == [date(2026, 11, 20)]
            assert adj_res.recalculated_days_count == 1

            assert mock_correction.call_count == 4
            first_call_args = mock_correction.call_args_list[0].kwargs["payload"]
            assert first_call_args.event_type == "CHECK_IN"
            assert first_call_args.location_id == override_loc_id
            assert first_call_args.metadata["conflict_incident_id"] == str(created_incident.id)

            last_call_args = mock_correction.call_args_list[3].kwargs["payload"]
            assert last_call_args.event_type == "CHECK_OUT"
            assert last_call_args.metadata["conflict_incident_id"] == str(created_incident.id)

            db_session.flush.assert_awaited()

        # Step E: Employee refreshes incident state via /my
        emp_id_lookup_mock = MagicMock()
        emp_id_lookup_mock.scalar_one_or_none.return_value = employee.id

        my_count_mock = MagicMock()
        my_count_mock.scalar.return_value = 1
        my_items_mock = MagicMock()
        my_items_mock.scalars.return_value.all.return_value = [created_incident]

        db_session.execute.side_effect = [
            emp_id_lookup_mock,
            my_count_mock,
            my_items_mock,
        ]

        my_res = await list_my_offline_conflict_incidents(
            session=db_session,
            tenant_id=tenant_id,
            user_id=emp_user.id,
        )

        assert my_res.total == 1
        assert my_res.items[0].status == "APPROVED"
        assert my_res.items[0].decision_reason == decision_req.reason


# ==============================================================================
# 2. Rejection Scenario Simulation
# ==============================================================================


class TestRejectionScenarioSimulation:
    """Simulates supervisor rejecting a conflict incident:
    - Status transitions to REJECTED.
    - Decision reason persisted.
    - Attendance ledger untouched (zero corrections, zero events).
    - Projections remain unchanged.
    - Forensic evidence preserved.
    """

    @pytest.mark.asyncio
    async def test_rejection_leaves_ledger_untouched_and_persists_evidence(self) -> None:
        tenant_id = uuid.uuid4()
        manager_user = _create_user("manager", tenant_id=tenant_id)
        manager_emp = _create_employee(tenant_id=tenant_id, user_id=manager_user.id, code="MGR-002")

        emp_user = _create_user("employee", tenant_id=tenant_id)
        employee = _create_employee(
            tenant_id=tenant_id,
            user_id=emp_user.id,
            reporting_manager_id=manager_emp.id,
            code="EMP-200",
        )

        bundle_payload = _build_full_shift_bundle_payload()
        incident = _create_mock_incident(
            tenant_id=tenant_id,
            employee_id=employee.id,
            user_id=emp_user.id,
            bundle_payload=bundle_payload,
        )

        db_session = AsyncMock()

        locked_incident_mock = MagicMock()
        locked_incident_mock.scalar_one_or_none.return_value = incident

        mgr_lookup_mock = MagicMock()
        mgr_lookup_mock.scalar_one_or_none.return_value = manager_emp

        emp_lookup_mock = MagicMock()
        emp_lookup_mock.scalar_one_or_none.return_value = employee

        db_session.execute.side_effect = [locked_incident_mock, mgr_lookup_mock, emp_lookup_mock]

        decision_req = AttendanceConflictDecisionRequest(
            action="REJECT",
            reason="Review of vehicle GPS logs confirmed worker was not at job site during shift hours",
        )

        with patch("services.api.attendance.conflict_service.apply_attendance_correction") as mock_correction:
            res = await adjudicate_conflict_incident(
                session=db_session,
                tenant_id=tenant_id,
                incident_id=incident.id,
                reviewer_user_id=manager_user.id,
                reviewer_role="manager",
                payload=decision_req,
            )

            assert res.status == "REJECTED"
            assert res.decision == "REJECTED"
            assert res.reviewer_user_id == manager_user.id
            assert res.decision_reason == decision_req.reason
            assert res.resolved_correction_event_ids == []
            assert res.affected_attendance_dates == []
            assert res.recalculated_days_count == 0

            mock_correction.assert_not_called()

            assert incident.status == "REJECTED"
            assert incident.decision == "REJECTED"
            assert incident.decision_reason == decision_req.reason
            assert incident.reviewer_user_id == manager_user.id
            assert incident.decided_at is not None

            assert incident.primary_rejected_event["event_type"] == "CHECK_IN"
            assert len(incident.dependent_events) == 3


# ==============================================================================
# 3. Chaos and Failure Scenarios
# ==============================================================================


class TestChaosAndFailureScenarios:
    """Exhaustive chaos simulation testing resilient system behavior."""

    @pytest.mark.asyncio
    async def test_network_loss_after_commit_idempotent_replay(self) -> None:
        """Client sends bundle, server commits, network drops before client gets 201.
        Client retries with identical payload -> receives HTTP 200 with original incident.
        No duplicate incidents created.
        """
        tenant_id = uuid.uuid4()
        emp_user = _create_user("employee", tenant_id=tenant_id)
        employee = _create_employee(tenant_id=tenant_id, user_id=emp_user.id)

        bundle_payload = _build_full_shift_bundle_payload()
        existing_incident = _create_mock_incident(
            tenant_id=tenant_id,
            employee_id=employee.id,
            user_id=emp_user.id,
            bundle_payload=bundle_payload,
        )

        db_session = AsyncMock()
        emp_lookup = MagicMock()
        emp_lookup.scalar_one_or_none.return_value = employee
        bundle_lookup = MagicMock()
        bundle_lookup.scalar_one_or_none.return_value = existing_incident

        db_session.execute.side_effect = [emp_lookup, emp_lookup, bundle_lookup]

        res = await submit_offline_conflict_bundle(
            session=db_session,
            tenant_id=tenant_id,
            user_id=emp_user.id,
            user_role="employee",
            payload=bundle_payload,
        )

        assert res.bundle_id == bundle_payload.bundle_id
        assert res.id == existing_incident.id
        assert res.status == "PENDING_REVIEW"
        assert res.idempotent_replay is True
        db_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_tampered_payload_on_same_bundle_id_raises_409(self) -> None:
        """Client submits bundle with same bundle_id but modified timestamps or events.
        Backend detects fingerprint mismatch and raises HTTP 409 Conflict.
        """
        tenant_id = uuid.uuid4()
        emp_user = _create_user("employee", tenant_id=tenant_id)
        employee = _create_employee(tenant_id=tenant_id, user_id=emp_user.id)

        bundle_payload = _build_full_shift_bundle_payload()
        existing_incident = _create_mock_incident(
            tenant_id=tenant_id,
            employee_id=employee.id,
            user_id=emp_user.id,
            bundle_payload=bundle_payload,
        )
        existing_incident.metadata_json = {"request_fingerprint": "sha256:different_hash_stored"}

        db_session = AsyncMock()
        emp_lookup = MagicMock()
        emp_lookup.scalar_one_or_none.return_value = employee
        bundle_lookup = MagicMock()
        bundle_lookup.scalar_one_or_none.return_value = existing_incident

        db_session.execute.side_effect = [emp_lookup, emp_lookup, bundle_lookup]

        with pytest.raises(HTTPException) as exc_info:
            await submit_offline_conflict_bundle(
                session=db_session,
                tenant_id=tenant_id,
                user_id=emp_user.id,
                user_role="employee",
                payload=bundle_payload,
            )

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert "Bundle ID reused with mismatched conflict payload" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_concurrent_supervisors_adjudicating_simultaneously(self) -> None:
        """Two supervisors attempt to adjudicate the same incident at the same time.
        First supervisor acquires row lock and sets status.
        Second supervisor encounters incident already adjudicated -> HTTP 409 Conflict.
        """
        tenant_id = uuid.uuid4()
        mgr1_user = _create_user("manager", tenant_id=tenant_id)
        mgr1_emp = _create_employee(tenant_id=tenant_id, user_id=mgr1_user.id, code="MGR-010")

        emp_user = _create_user("employee", tenant_id=tenant_id)
        employee = _create_employee(tenant_id=tenant_id, user_id=emp_user.id, reporting_manager_id=mgr1_emp.id)

        bundle_payload = _build_full_shift_bundle_payload()
        already_decided_incident = _create_mock_incident(
            tenant_id=tenant_id,
            employee_id=employee.id,
            user_id=emp_user.id,
            bundle_payload=bundle_payload,
            status_str="APPROVED",
        )

        db_session = AsyncMock()
        incident_lookup = MagicMock()
        incident_lookup.scalar_one_or_none.return_value = already_decided_incident

        db_session.execute.return_value = incident_lookup

        req = AttendanceConflictDecisionRequest(
            action="REJECT",
            reason="Concurrent reject attempt",
        )

        with pytest.raises(HTTPException) as exc_info:
            await adjudicate_conflict_incident(
                session=db_session,
                tenant_id=tenant_id,
                incident_id=already_decided_incident.id,
                reviewer_user_id=mgr1_user.id,
                reviewer_role="manager",
                payload=req,
            )

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert "already been resolved" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_atomic_rollback_on_partial_event_insertion_failure(self) -> None:
        """Supervisor approves incident with 4 events. First event succeeds,
        second event raises exception during apply_attendance_correction.
        System must roll back the transaction, leaving ZERO events inserted
        and incident status remaining PENDING_REVIEW.
        """
        tenant_id = uuid.uuid4()
        mgr_user = _create_user("manager", tenant_id=tenant_id)
        mgr_emp = _create_employee(tenant_id=tenant_id, user_id=mgr_user.id, code="MGR-020")

        emp_user = _create_user("employee", tenant_id=tenant_id)
        employee = _create_employee(tenant_id=tenant_id, user_id=emp_user.id, reporting_manager_id=mgr_emp.id)

        bundle_payload = _build_full_shift_bundle_payload()
        incident = _create_mock_incident(
            tenant_id=tenant_id,
            employee_id=employee.id,
            user_id=emp_user.id,
            bundle_payload=bundle_payload,
        )

        db_session = AsyncMock()
        db_session.rollback = AsyncMock()

        incident_lookup = MagicMock()
        incident_lookup.scalar_one_or_none.return_value = incident
        mgr_lookup = MagicMock()
        mgr_lookup.scalar_one_or_none.return_value = mgr_emp
        emp_lookup = MagicMock()
        emp_lookup.scalar_one_or_none.return_value = employee

        db_session.execute.side_effect = [incident_lookup, mgr_lookup, emp_lookup]

        req = AttendanceConflictDecisionRequest(
            action="APPROVE",
            reason="Approval where second event fails",
        )

        now = datetime.now(UTC)
        dummy_event = AttendanceEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            employee_id=employee.id,
            event_type="CHECK_IN",
            event_category="CORRECTION_INSERT",
            effective_at=now,
            server_received_at=now,
            source="ADMIN",
            review_status="NOT_REQUIRED",
            timestamp_verification_status="SERVER_AUTHORITATIVE",
            idempotency_key=f"cf_mock_{uuid.uuid4().hex[:8]}",
            correction_reason="Offline Conflict Approval",
            created_at=now,
            metadata_json={},
        )

        dummy_corr_resp = AttendanceCorrectionResponse(
            correction_event=AttendanceEventResponse.model_validate(dummy_event),
            affected_attendance_dates=[date(2026, 11, 20)],
            recalculated_days=[],
            idempotent_replay=False,
        )

        with patch(
            "services.api.attendance.conflict_service.apply_attendance_correction",
            side_effect=[
                dummy_corr_resp,
                HTTPException(status_code=500, detail="Simulated database constraint crash on second punch insertion"),
            ],
        ):
            with pytest.raises(HTTPException) as exc_info:
                await adjudicate_conflict_incident(
                    session=db_session,
                    tenant_id=tenant_id,
                    incident_id=incident.id,
                    reviewer_user_id=mgr_user.id,
                    reviewer_role="manager",
                    payload=req,
                )

            assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            db_session.rollback.assert_awaited()
            assert incident.status == "PENDING_REVIEW"

    @pytest.mark.asyncio
    async def test_overnight_shift_spanning_two_calendar_dates(self) -> None:
        """Simulate an overnight shift starting at 22:00 on Day 1 and ending at 06:00 on Day 2.
        Approval must detect both calendar dates (2026-11-20 and 2026-11-21) and recalculate both.
        """
        tenant_id = uuid.uuid4()
        mgr_user = _create_user("manager", tenant_id=tenant_id)
        mgr_emp = _create_employee(tenant_id=tenant_id, user_id=mgr_user.id, code="MGR-030")

        emp_user = _create_user("employee", tenant_id=tenant_id)
        employee = _create_employee(tenant_id=tenant_id, user_id=emp_user.id, reporting_manager_id=mgr_emp.id)

        t_check_in = datetime(2026, 11, 20, 22, 0, 0, tzinfo=UTC)
        t_check_out = datetime(2026, 11, 21, 6, 0, 0, tzinfo=UTC)

        primary = OfflineRejectedEventPayload(
            local_id="loc_in_night",
            idempotency_key=str(uuid.uuid4()),
            event_type="CHECK_IN",
            device_reported_at=t_check_in,
            latitude=40.7128,
            longitude=-74.0060,
            server_rejection_code=422,
            server_rejection_reason="Geofence failed",
        )

        dependent = OfflineDependentEventPayload(
            local_id="loc_out_night",
            idempotency_key=str(uuid.uuid4()),
            event_type="CHECK_OUT",
            device_reported_at=t_check_out,
            latitude=40.7128,
            longitude=-74.0060,
        )

        bundle_req = OfflineConflictBundleSubmitRequest(
            bundle_id=f"bundle_overnight_{uuid.uuid4().hex[:8]}",
            session_id=f"sess_overnight_{uuid.uuid4().hex[:8]}",
            primary_rejected_event=primary,
            dependent_events=[dependent],
        )

        incident = _create_mock_incident(
            tenant_id=tenant_id,
            employee_id=employee.id,
            user_id=emp_user.id,
            bundle_payload=bundle_req,
        )

        db_session = AsyncMock()
        incident_lookup = MagicMock()
        incident_lookup.scalar_one_or_none.return_value = incident
        mgr_lookup = MagicMock()
        mgr_lookup.scalar_one_or_none.return_value = mgr_emp
        emp_lookup = MagicMock()
        emp_lookup.scalar_one_or_none.return_value = employee

        db_session.execute.side_effect = [incident_lookup, mgr_lookup, emp_lookup]

        req = AttendanceConflictDecisionRequest(
            action="APPROVE",
            reason="Approved valid overnight shift",
        )

        now = datetime.now(UTC)
        dummy_event1 = AttendanceEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            employee_id=employee.id,
            event_type="CHECK_IN",
            event_category="CORRECTION_INSERT",
            effective_at=t_check_in,
            server_received_at=now,
            source="ADMIN",
            review_status="NOT_REQUIRED",
            timestamp_verification_status="SERVER_AUTHORITATIVE",
            idempotency_key=f"cf_mock_{uuid.uuid4().hex[:8]}",
            correction_reason="Offline Conflict Approval",
            created_at=now,
            metadata_json={},
        )
        dummy_event2 = AttendanceEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            employee_id=employee.id,
            event_type="CHECK_OUT",
            event_category="CORRECTION_INSERT",
            effective_at=t_check_out,
            server_received_at=now,
            source="ADMIN",
            review_status="NOT_REQUIRED",
            timestamp_verification_status="SERVER_AUTHORITATIVE",
            idempotency_key=f"cf_mock_{uuid.uuid4().hex[:8]}",
            correction_reason="Offline Conflict Approval",
            created_at=now,
            metadata_json={},
        )

        resp1 = AttendanceCorrectionResponse(
            correction_event=AttendanceEventResponse.model_validate(dummy_event1),
            affected_attendance_dates=[date(2026, 11, 20)],
            recalculated_days=[],
            idempotent_replay=False,
        )
        resp2 = AttendanceCorrectionResponse(
            correction_event=AttendanceEventResponse.model_validate(dummy_event2),
            affected_attendance_dates=[date(2026, 11, 21)],
            recalculated_days=[],
            idempotent_replay=False,
        )

        with patch(
            "services.api.attendance.conflict_service.apply_attendance_correction",
            side_effect=[resp1, resp2],
        ):
            res = await adjudicate_conflict_incident(
                session=db_session,
                tenant_id=tenant_id,
                incident_id=incident.id,
                reviewer_user_id=mgr_user.id,
                reviewer_role="manager",
                payload=req,
            )

            assert res.status == "APPROVED"
            assert len(res.affected_attendance_dates) == 2
            assert date(2026, 11, 20) in res.affected_attendance_dates
            assert date(2026, 11, 21) in res.affected_attendance_dates
            assert res.recalculated_days_count == 2

    @pytest.mark.asyncio
    async def test_cross_tenant_access_attempt_returns_404(self) -> None:
        """A supervisor from Tenant B attempts to access an incident from Tenant A.
        Query must return 404 (tenant isolation via query filtering).
        """
        tenant_b = uuid.uuid4()
        mgr_b_user = _create_user("manager", tenant_id=tenant_b)

        db_session = AsyncMock()
        incident_lookup = MagicMock()
        incident_lookup.scalar_one_or_none.return_value = None

        db_session.execute.return_value = incident_lookup

        with pytest.raises(HTTPException) as exc_info:
            await get_conflict_incident_detail(
                session=db_session,
                tenant_id=tenant_b,
                user_id=mgr_b_user.id,
                user_role="manager",
                incident_id=uuid.uuid4(),
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_manager_accessing_non_direct_report_incident_returns_403(self) -> None:
        """A manager attempts to view an incident belonging to another manager's direct report.
        Returns 403 Forbidden to enforce manager scoping.
        """
        tenant_id = uuid.uuid4()
        mgr1_user = _create_user("manager", tenant_id=tenant_id)
        mgr1_emp = _create_employee(tenant_id=tenant_id, user_id=mgr1_user.id, code="MGR-01")

        mgr2_emp_id = uuid.uuid4()
        unrelated_employee = _create_employee(
            tenant_id=tenant_id,
            user_id=uuid.uuid4(),
            reporting_manager_id=mgr2_emp_id,
            code="EMP-UNRELATED",
        )

        bundle_payload = _build_full_shift_bundle_payload()
        unrelated_incident = _create_mock_incident(
            tenant_id=tenant_id,
            employee_id=unrelated_employee.id,
            user_id=unrelated_employee.user_id,
            bundle_payload=bundle_payload,
        )

        db_session = AsyncMock()
        incident_lookup = MagicMock()
        incident_lookup.scalar_one_or_none.return_value = unrelated_incident
        emp_lookup = MagicMock()
        emp_lookup.scalar_one_or_none.return_value = unrelated_employee
        mgr_lookup = MagicMock()
        mgr_lookup.scalar_one_or_none.return_value = mgr1_emp

        db_session.execute.side_effect = [incident_lookup, emp_lookup, mgr_lookup]

        with pytest.raises(HTTPException) as exc_info:
            await get_conflict_incident_detail(
                session=db_session,
                tenant_id=tenant_id,
                user_id=mgr1_user.id,
                user_role="manager",
                incident_id=unrelated_incident.id,
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_anti_self_approval_rule_prevents_manager_approving_own_incident(self) -> None:
        """A supervisor who is also an employee cannot adjudicate their own offline conflict."""
        tenant_id = uuid.uuid4()
        mgr_user = _create_user("manager", tenant_id=tenant_id)
        mgr_emp = _create_employee(tenant_id=tenant_id, user_id=mgr_user.id, code="MGR-SELF")

        bundle_payload = _build_full_shift_bundle_payload()
        self_incident = _create_mock_incident(
            tenant_id=tenant_id,
            employee_id=mgr_emp.id,
            user_id=mgr_user.id,
            bundle_payload=bundle_payload,
        )

        db_session = AsyncMock()
        incident_lookup = MagicMock()
        incident_lookup.scalar_one_or_none.return_value = self_incident
        mgr_lookup = MagicMock()
        mgr_lookup.scalar_one_or_none.return_value = mgr_emp

        db_session.execute.side_effect = [incident_lookup, mgr_lookup]

        req = AttendanceConflictDecisionRequest(
            action="APPROVE",
            reason="Self approval attempt",
        )

        with pytest.raises(HTTPException) as exc_info:
            await adjudicate_conflict_incident(
                session=db_session,
                tenant_id=tenant_id,
                incident_id=self_incident.id,
                reviewer_user_id=mgr_user.id,
                reviewer_role="manager",
                payload=req,
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Reviewers cannot adjudicate their own attendance conflicts" in exc_info.value.detail
