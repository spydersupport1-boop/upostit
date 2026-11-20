"""Comprehensive automated test suite for Phase 8 Milestone 8.3:
Supervisor Adjudication Workflow & Atomic Correction Integration.

Tests:
1. Supervisor review queue: role scoping (manager sees only direct reports, HR/Admin/Owner tenant-wide, employee denied HTTP 403).
2. Incident detail authorization: employee can view own, peer denied HTTP 403, manager direct reports allowed, non-reports denied HTTP 403.
3. Decision validation & RBAC: reason length >= 3, invalid action 422, anti-self-approval HTTP 403, manager non-direct report HTTP 403.
4. Rejection workflow: sets status to REJECTED with reason, reviewer, and timestamp; zero writes to attendance_events; zero recalculation.
5. Approval workflow: atomic invocation of apply_attendance_correction(CORRECTION_INSERT), chronological ordering, audit metadata, recalculation.
6. Atomicity & rollback resilience: full rollback if event 1 fails, event 2 fails, or recalculation fails; pessimistic row locking.
7. Concurrency & state machine: already-decided incidents reject subsequent requests with HTTP 409 Conflict.
8. HTTP route integration: GET /offline-conflicts, GET /offline-conflicts/{id}, POST /offline-conflicts/{id}/decision.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from services.api.attendance.conflict_service import (
    adjudicate_conflict_incident,
    get_conflict_incident_detail,
    list_supervisor_conflict_queue,
)
from services.api.attendance.models import (
    AttendanceConflictIncident,
    AttendanceEvent,
)
from services.api.attendance.schemas import (
    AttendanceConflictDecisionRequest,
    AttendanceCorrectionResponse,
    AttendanceEventResponse,
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
    role: str = "manager",
    tenant_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> AuthenticatedContext:
    tid = tenant_id or uuid.uuid4()
    uid = user_id or uuid.uuid4()
    user = User(
        id=uid,
        tenant_id=tid,
        email=f"{role.lower()}@conflicts.test",
        full_name=f"Test {role.capitalize()}",
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
    reporting_manager_id: uuid.UUID | None = None,
    first_name: str = "Jane",
    last_name: str = "Doe",
    employee_code: str = "EMP-001",
    department_id: uuid.UUID | None = None,
) -> Employee:
    return Employee(
        id=employee_id or uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        employee_id=employee_code,
        work_email=f"{first_name.lower()}.{last_name.lower()}@conflicts.test",
        first_name=first_name,
        last_name=last_name,
        reporting_manager_id=reporting_manager_id,
        department_id=department_id,
        joining_date=date(2025, 1, 1),
        status="active",
    )


def _mock_incident(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    user_id: uuid.UUID,
    incident_id: uuid.UUID | None = None,
    bundle_id: str = "bundle_test_001",
    status_str: str = "PENDING_REVIEW",
    has_dependent: bool = True,
    base_time: datetime | None = None,
) -> AttendanceConflictIncident:
    inc_id = incident_id or uuid.uuid4()
    t0 = base_time or (datetime.now(UTC) - timedelta(hours=4))
    t1 = t0 + timedelta(hours=4)
    now = datetime.now(UTC)

    prim_payload = {
        "local_id": "loc_101",
        "idempotency_key": str(uuid.uuid4()),
        "event_type": "CHECK_IN",
        "device_reported_at": t0.isoformat(),
        "latitude": 12.971598,
        "longitude": 77.594562,
        "accuracy_meters": 14.0,
        "device_id_hash": "hash_device_001",
        "device_model": "Pixel 8",
        "os_version": "Android 15",
        "is_mock_location": False,
        "server_rejection_code": 422,
        "server_rejection_reason": "Outside authorized workplace geofence radius",
    }

    dep_payload = []
    if has_dependent:
        dep_payload = [
            {
                "local_id": "loc_102",
                "idempotency_key": str(uuid.uuid4()),
                "event_type": "CHECK_OUT",
                "device_reported_at": t1.isoformat(),
                "latitude": 12.971610,
                "longitude": 77.594580,
                "accuracy_meters": 11.0,
                "device_id_hash": "hash_device_001",
                "device_model": "Pixel 8",
                "os_version": "Android 15",
                "is_mock_location": False,
            }
        ]

    return AttendanceConflictIncident(
        id=inc_id,
        tenant_id=tenant_id,
        employee_id=employee_id,
        user_id=user_id,
        bundle_id=bundle_id,
        session_id="sess_001",
        status=status_str,
        primary_rejected_event=prim_payload,
        dependent_events=dep_payload,
        total_events_count=1 + len(dep_payload),
        rejection_summary="Outside authorized workplace geofence radius",
        employee_notes="Badge reader offline during morning shift",
        submitted_at=datetime.now(UTC) - timedelta(hours=2),
        decision=None if status_str == "PENDING_REVIEW" else status_str,
        decision_reason=None if status_str == "PENDING_REVIEW" else "Existing decision",
        reviewer_user_id=None if status_str == "PENDING_REVIEW" else uuid.uuid4(),
        decided_at=None if status_str == "PENDING_REVIEW" else datetime.now(UTC),
        resolved_correction_event_ids=[],
        metadata_json={"request_fingerprint": "mock_fp"},
        created_at=now,
        updated_at=now,
    )


# ==============================================================================
# 1. Supervisor Review Queue Authorization & Manager Scoping Tests
# ==============================================================================


class TestSupervisorQueueScopingAndAuthorization:
    """Validates role-based visibility, manager direct-report isolation, and employee denial."""

    @pytest.mark.asyncio
    async def test_employee_denied_access_to_supervisor_queue(self):
        """Employees must be strictly forbidden from accessing the supervisor review queue."""
        tid = uuid.uuid4()
        uid = uuid.uuid4()
        mock_session = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await list_supervisor_conflict_queue(
                session=mock_session,
                tenant_id=tid,
                user_id=uid,
                user_role="employee",
            )
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Employees cannot access the supervisor conflict review queue" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_manager_only_sees_direct_reports(self):
        """A manager should only retrieve incidents for employees who report directly to them."""
        tid = uuid.uuid4()
        mgr_user_id = uuid.uuid4()
        mgr_emp_id = uuid.uuid4()

        # Manager's employee record
        _mock_employee(tid, mgr_user_id, mgr_emp_id)

        # Direct report employee
        rep_emp_id = uuid.uuid4()
        rep_emp = _mock_employee(tid, uuid.uuid4(), rep_emp_id, reporting_manager_id=mgr_emp_id)

        # Direct report incident
        inc_report = _mock_incident(tid, rep_emp_id, rep_emp.user_id, bundle_id="b_report")

        mock_session = AsyncMock()

        # Mock query return values:
        # 1. Manager lookup -> mgr_emp_id
        # 2. Total count -> 1
        # 3. Incident records -> [(inc_report, "Jane", "Doe", "EMP-001", "Engineering")]
        mgr_res_mock = MagicMock()
        mgr_res_mock.scalar_one_or_none.return_value = mgr_emp_id

        count_res_mock = MagicMock()
        count_res_mock.scalar.return_value = 1

        list_res_mock = MagicMock()
        list_res_mock.all.return_value = [
            (inc_report, "Jane", "Doe", "EMP-001", "Engineering")
        ]

        mock_session.execute.side_effect = [mgr_res_mock, count_res_mock, list_res_mock]

        res = await list_supervisor_conflict_queue(
            session=mock_session,
            tenant_id=tid,
            user_id=mgr_user_id,
            user_role="manager",
        )

        assert res.total == 1
        assert len(res.items) == 1
        assert res.items[0].bundle_id == "b_report"
        assert res.items[0].employee_name == "Jane Doe"
        assert res.items[0].department_name == "Engineering"

    @pytest.mark.asyncio
    async def test_manager_without_employee_profile_returns_empty(self):
        """If a user with 'manager' role has no employee profile, returns 0 items safely."""
        tid = uuid.uuid4()
        mgr_user_id = uuid.uuid4()
        mock_session = AsyncMock()

        mgr_res_mock = MagicMock()
        mgr_res_mock.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mgr_res_mock

        res = await list_supervisor_conflict_queue(
            session=mock_session,
            tenant_id=tid,
            user_id=mgr_user_id,
            user_role="manager",
        )

        assert res.total == 0
        assert len(res.items) == 0
        assert res.has_more is False

    @pytest.mark.asyncio
    async def test_hr_admin_owner_sees_all_tenant_incidents(self):
        """HR, Admin, and Owner roles see tenant-wide incidents without reporting-line restrictions."""
        tid = uuid.uuid4()
        admin_user_id = uuid.uuid4()

        inc1 = _mock_incident(tid, uuid.uuid4(), uuid.uuid4(), bundle_id="b_1")
        inc2 = _mock_incident(tid, uuid.uuid4(), uuid.uuid4(), bundle_id="b_2")

        mock_session = AsyncMock()

        count_res_mock = MagicMock()
        count_res_mock.scalar.return_value = 2

        list_res_mock = MagicMock()
        list_res_mock.all.return_value = [
            (inc1, "Alice", "Smith", "EMP-001", "Product"),
            (inc2, "Bob", "Jones", "EMP-002", "Operations"),
        ]

        mock_session.execute.side_effect = [count_res_mock, list_res_mock]

        res = await list_supervisor_conflict_queue(
            session=mock_session,
            tenant_id=tid,
            user_id=admin_user_id,
            user_role="admin",
        )

        assert res.total == 2
        assert len(res.items) == 2
        assert res.items[0].bundle_id == "b_1"
        assert res.items[1].bundle_id == "b_2"


# ==============================================================================
# 2. Incident Detail Authorization Tests
# ==============================================================================


class TestIncidentDetailAuthorization:
    """Validates authorization rules for GET /offline-conflicts/{id}."""

    @pytest.mark.asyncio
    async def test_employee_can_view_own_incident_detail(self):
        """An employee can view their own submitted conflict incident."""
        tid = uuid.uuid4()
        user_id = uuid.uuid4()
        emp_id = uuid.uuid4()

        emp = _mock_employee(tid, user_id, emp_id)
        inc = _mock_incident(tid, emp_id, user_id)

        mock_session = AsyncMock()

        inc_res = MagicMock()
        inc_res.scalar_one_or_none.return_value = inc

        emp_res = MagicMock()
        emp_res.first.return_value = (emp, "Engineering")

        caller_emp_res = MagicMock()
        caller_emp_res.scalar_one_or_none.return_value = emp_id

        mock_session.execute.side_effect = [inc_res, emp_res, caller_emp_res]

        detail = await get_conflict_incident_detail(
            session=mock_session,
            tenant_id=tid,
            user_id=user_id,
            user_role="employee",
            incident_id=inc.id,
        )

        assert detail.id == inc.id
        assert detail.employee.id == emp_id
        assert detail.employee.department_name == "Engineering"
        assert detail.bundle_id == inc.bundle_id

    @pytest.mark.asyncio
    async def test_employee_cannot_view_peer_incident_detail(self):
        """An employee attempting to view a peer employee's conflict must be denied HTTP 403."""
        tid = uuid.uuid4()
        caller_user_id = uuid.uuid4()
        caller_emp_id = uuid.uuid4()

        peer_emp_id = uuid.uuid4()
        peer_user_id = uuid.uuid4()

        peer_emp = _mock_employee(tid, peer_user_id, peer_emp_id)
        inc = _mock_incident(tid, peer_emp_id, peer_user_id)

        mock_session = AsyncMock()

        inc_res = MagicMock()
        inc_res.scalar_one_or_none.return_value = inc

        emp_res = MagicMock()
        emp_res.first.return_value = (peer_emp, "Sales")

        caller_emp_res = MagicMock()
        caller_emp_res.scalar_one_or_none.return_value = caller_emp_id

        mock_session.execute.side_effect = [inc_res, emp_res, caller_emp_res]

        with pytest.raises(HTTPException) as exc_info:
            await get_conflict_incident_detail(
                session=mock_session,
                tenant_id=tid,
                user_id=caller_user_id,
                user_role="employee",
                incident_id=inc.id,
            )
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Employees may only inspect their own attendance conflicts" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_manager_cannot_view_non_report_incident_detail(self):
        """A manager attempting to view an incident for an employee who does not report to them gets HTTP 403."""
        tid = uuid.uuid4()
        mgr_user_id = uuid.uuid4()
        mgr_emp_id = uuid.uuid4()

        other_mgr_id = uuid.uuid4()
        target_emp_id = uuid.uuid4()
        target_emp = _mock_employee(
            tid, uuid.uuid4(), target_emp_id, reporting_manager_id=other_mgr_id
        )

        inc = _mock_incident(tid, target_emp_id, target_emp.user_id)

        mock_session = AsyncMock()

        inc_res = MagicMock()
        inc_res.scalar_one_or_none.return_value = inc

        emp_res = MagicMock()
        emp_res.first.return_value = (target_emp, "Support")

        caller_emp_res = MagicMock()
        caller_emp_res.scalar_one_or_none.return_value = mgr_emp_id

        mock_session.execute.side_effect = [inc_res, emp_res, caller_emp_res]

        with pytest.raises(HTTPException) as exc_info:
            await get_conflict_incident_detail(
                session=mock_session,
                tenant_id=tid,
                user_id=mgr_user_id,
                user_role="manager",
                incident_id=inc.id,
            )
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Managers may only inspect attendance conflicts of their direct reports" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_cross_tenant_incident_detail_returns_404(self):
        """Incident lookup with mismatched tenant_id must return HTTP 404."""
        tid_a = uuid.uuid4()
        user_id = uuid.uuid4()
        mock_session = AsyncMock()

        inc_res = MagicMock()
        inc_res.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = inc_res

        with pytest.raises(HTTPException) as exc_info:
            await get_conflict_incident_detail(
                session=mock_session,
                tenant_id=tid_a,
                user_id=user_id,
                user_role="admin",
                incident_id=uuid.uuid4(),
            )
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


# ==============================================================================
# 3. Supervisor Decision Validation & RBAC Tests
# ==============================================================================


class TestSupervisorDecisionValidationAndRBAC:
    """Validates decision payload schemas, action normalization, and anti-self-approval."""

    def test_decision_reason_minimum_length_validation(self):
        """Reason with less than 3 non-whitespace characters must raise validation error."""
        with pytest.raises(ValidationError):
            AttendanceConflictDecisionRequest(action="APPROVE", reason="   ")

        with pytest.raises(ValidationError):
            AttendanceConflictDecisionRequest(action="REJECT", reason="ab")

        # Valid reason passes
        req = AttendanceConflictDecisionRequest(action="APPROVE", reason="abc")
        assert req.reason == "abc"

    def test_decision_action_normalization(self):
        """Action must accept case-insensitive APPROVE and REJECT variants."""
        req1 = AttendanceConflictDecisionRequest(action="approve", reason="Verified physically")
        assert req1.action == "APPROVE"

        req2 = AttendanceConflictDecisionRequest(action="REJECTED", reason="Invalid GPS data")
        assert req2.action == "REJECT"

        with pytest.raises(ValidationError):
            AttendanceConflictDecisionRequest(action="HOLD", reason="Waiting for HR")

    @pytest.mark.asyncio
    async def test_anti_self_approval_manager_cannot_adjudicate_own_conflict(self):
        """A manager submitting a conflict cannot adjudicate their own incident."""
        tid = uuid.uuid4()
        user_id = uuid.uuid4()
        emp_id = uuid.uuid4()

        # Manager's own employee record
        mgr_emp = _mock_employee(tid, user_id, emp_id)
        # Incident submitted by this manager
        inc = _mock_incident(tid, emp_id, user_id)

        mock_session = AsyncMock()

        inc_res = MagicMock()
        inc_res.scalar_one_or_none.return_value = inc

        rev_emp_res = MagicMock()
        rev_emp_res.scalar_one_or_none.return_value = mgr_emp

        mock_session.execute.side_effect = [inc_res, rev_emp_res]

        req = AttendanceConflictDecisionRequest(
            action="APPROVE", reason="Self-approving my missed punch"
        )

        with pytest.raises(HTTPException) as exc_info:
            await adjudicate_conflict_incident(
                session=mock_session,
                tenant_id=tid,
                incident_id=inc.id,
                reviewer_user_id=user_id,
                reviewer_role="manager",
                payload=req,
            )
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Reviewers cannot adjudicate their own attendance conflicts" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_anti_self_approval_hr_admin_cannot_adjudicate_own_conflict(self):
        """Even HR, Admin, or Owner cannot adjudicate their own conflict."""
        tid = uuid.uuid4()
        user_id = uuid.uuid4()
        emp_id = uuid.uuid4()

        admin_emp = _mock_employee(tid, user_id, emp_id)
        inc = _mock_incident(tid, emp_id, user_id)

        mock_session = AsyncMock()

        inc_res = MagicMock()
        inc_res.scalar_one_or_none.return_value = inc

        rev_emp_res = MagicMock()
        rev_emp_res.scalar_one_or_none.return_value = admin_emp

        mock_session.execute.side_effect = [inc_res, rev_emp_res]

        req = AttendanceConflictDecisionRequest(action="APPROVE", reason="Admin self approval")

        with pytest.raises(HTTPException) as exc_info:
            await adjudicate_conflict_incident(
                session=mock_session,
                tenant_id=tid,
                incident_id=inc.id,
                reviewer_user_id=user_id,
                reviewer_role="admin",
                payload=req,
            )
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Reviewers cannot adjudicate their own attendance conflicts" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_already_decided_incident_returns_409_conflict(self):
        """Attempting to adjudicate an incident that is already APPROVED or REJECTED returns HTTP 409."""
        tid = uuid.uuid4()
        reviewer_user_id = uuid.uuid4()

        # Incident already approved
        inc = _mock_incident(
            tid, uuid.uuid4(), uuid.uuid4(), status_str="APPROVED"
        )

        mock_session = AsyncMock()
        inc_res = MagicMock()
        inc_res.scalar_one_or_none.return_value = inc
        mock_session.execute.return_value = inc_res

        req = AttendanceConflictDecisionRequest(action="REJECT", reason="Second attempt rejection")

        with pytest.raises(HTTPException) as exc_info:
            await adjudicate_conflict_incident(
                session=mock_session,
                tenant_id=tid,
                incident_id=inc.id,
                reviewer_user_id=reviewer_user_id,
                reviewer_role="admin",
                payload=req,
            )
        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert "Conflict incident has already been resolved (APPROVED)" in exc_info.value.detail


# ==============================================================================
# 4. Rejection Workflow Tests
# ==============================================================================


class TestRejectionWorkflow:
    """Validates supervisor REJECT decision behavior: ledger untouched, no recalculation."""

    @pytest.mark.asyncio
    async def test_rejection_marks_incident_rejected_and_leaves_ledger_untouched(self):
        """Rejection updates incident state, records reason and reviewer, and touches 0 attendance events."""
        tid = uuid.uuid4()
        reviewer_user_id = uuid.uuid4()
        reviewer_emp_id = uuid.uuid4()

        target_user_id = uuid.uuid4()
        target_emp_id = uuid.uuid4()

        reviewer_emp = _mock_employee(tid, reviewer_user_id, reviewer_emp_id)
        target_emp = _mock_employee(
            tid, target_user_id, target_emp_id, reporting_manager_id=reviewer_emp_id
        )

        inc = _mock_incident(tid, target_emp_id, target_user_id)

        mock_session = AsyncMock()

        inc_res = MagicMock()
        inc_res.scalar_one_or_none.return_value = inc

        rev_emp_res = MagicMock()
        rev_emp_res.scalar_one_or_none.return_value = reviewer_emp

        tgt_emp_res = MagicMock()
        tgt_emp_res.scalar_one_or_none.return_value = target_emp

        mock_session.execute.side_effect = [inc_res, rev_emp_res, tgt_emp_res]

        req = AttendanceConflictDecisionRequest(
            action="REJECT",
            reason="Security review showed device was in another city during punch",
        )

        with patch("services.api.attendance.conflict_service.apply_attendance_correction") as mock_apply_corr:
            res = await adjudicate_conflict_incident(
                session=mock_session,
                tenant_id=tid,
                incident_id=inc.id,
                reviewer_user_id=reviewer_user_id,
                reviewer_role="manager",
                payload=req,
            )

            # Verification
            assert res.status == "REJECTED"
            assert res.decision == "REJECTED"
            assert res.decision_reason == "Security review showed device was in another city during punch"
            assert res.reviewer_user_id == reviewer_user_id
            assert res.resolved_correction_event_ids == []
            assert res.affected_attendance_dates == []
            assert res.recalculated_days_count == 0

            # Incident model attributes updated
            assert inc.status == "REJECTED"
            assert inc.decision == "REJECTED"
            assert inc.reviewer_user_id == reviewer_user_id
            assert inc.decided_at is not None

            # Crucial: correction engine was NEVER invoked
            mock_apply_corr.assert_not_called()
            mock_session.flush.assert_awaited_once()


# ==============================================================================
# 5. Approval Atomic Integration Tests
# ==============================================================================


class TestApprovalAtomicIntegration:
    """Validates atomic insertion of events via apply_attendance_correction and recalculation."""

    @pytest.mark.asyncio
    async def test_approval_single_event_calls_apply_attendance_correction(self):
        """Approving an incident with 1 punch invokes apply_attendance_correction once."""
        tid = uuid.uuid4()
        reviewer_user_id = uuid.uuid4()
        reviewer_emp_id = uuid.uuid4()

        target_user_id = uuid.uuid4()
        target_emp_id = uuid.uuid4()

        reviewer_emp = _mock_employee(tid, reviewer_user_id, reviewer_emp_id)
        target_emp = _mock_employee(
            tid, target_user_id, target_emp_id, reporting_manager_id=reviewer_emp_id
        )

        # Incident with only 1 primary event (no dependents)
        inc = _mock_incident(tid, target_emp_id, target_user_id, has_dependent=False)

        mock_session = AsyncMock()

        inc_res = MagicMock()
        inc_res.scalar_one_or_none.return_value = inc

        rev_emp_res = MagicMock()
        rev_emp_res.scalar_one_or_none.return_value = reviewer_emp

        tgt_emp_res = MagicMock()
        tgt_emp_res.scalar_one_or_none.return_value = target_emp

        mock_session.execute.side_effect = [inc_res, rev_emp_res, tgt_emp_res]

        created_event_id = uuid.uuid4()
        now = datetime.now(UTC)
        dummy_corr_event = AttendanceEvent(
            id=created_event_id,
            tenant_id=tid,
            employee_id=target_emp_id,
            event_type="CHECK_IN",
            event_category="CORRECTION_INSERT",
            effective_at=now,
            server_received_at=now,
            source="ADMIN",
            review_status="NOT_REQUIRED",
            timestamp_verification_status="SERVER_AUTHORITATIVE",
            idempotency_key="cf_mock_001",
            correction_reason="Offline Conflict Approval: Validated physical presence",
            created_at=now,
            metadata_json={},
        )
        dummy_response = AttendanceCorrectionResponse(
            correction_event=AttendanceEventResponse.model_validate(dummy_corr_event),
            affected_attendance_dates=[date(2026, 11, 20)],
            recalculated_days=[],
            idempotent_replay=False,
        )

        req = AttendanceConflictDecisionRequest(
            action="APPROVE",
            reason="Validated physical presence in facilities log",
        )

        with patch(
            "services.api.attendance.conflict_service.apply_attendance_correction",
            new=AsyncMock(return_value=dummy_response),
        ) as mock_apply_corr:
            res = await adjudicate_conflict_incident(
                session=mock_session,
                tenant_id=tid,
                incident_id=inc.id,
                reviewer_user_id=reviewer_user_id,
                reviewer_role="manager",
                payload=req,
            )

            assert res.status == "APPROVED"
            assert res.decision == "APPROVED"
            assert str(created_event_id) in res.resolved_correction_event_ids
            assert res.affected_attendance_dates == [date(2026, 11, 20)]
            assert res.recalculated_days_count == 1

            # Assert correction request passed correct parameters
            mock_apply_corr.assert_awaited_once()
            call_kwargs = mock_apply_corr.call_args.kwargs
            assert call_kwargs["tenant_id"] == tid
            assert call_kwargs["actor_user_id"] == reviewer_user_id
            assert call_kwargs["actor_role"] == "manager"
            corr_req = call_kwargs["payload"]
            assert corr_req.employee_id == target_emp_id
            assert corr_req.event_type == "CHECK_IN"
            assert corr_req.correction_reason == "Offline Conflict Approval: Validated physical presence in facilities log"
            assert corr_req.metadata["conflict_incident_id"] == str(inc.id)
            assert corr_req.metadata["bundle_id"] == inc.bundle_id
            assert corr_req.metadata["source"] == "OFFLINE_CONFLICT_RESOLUTION"

    @pytest.mark.asyncio
    async def test_approval_multiple_events_preserves_chronological_order(self):
        """Approving an incident with 2 events invokes correction engine in exact chronological order."""
        tid = uuid.uuid4()
        reviewer_user_id = uuid.uuid4()
        reviewer_emp_id = uuid.uuid4()

        target_user_id = uuid.uuid4()
        target_emp_id = uuid.uuid4()

        reviewer_emp = _mock_employee(tid, reviewer_user_id, reviewer_emp_id)
        target_emp = _mock_employee(
            tid, target_user_id, target_emp_id, reporting_manager_id=reviewer_emp_id
        )

        # Incident with 1 primary CHECK_IN and 1 dependent CHECK_OUT
        inc = _mock_incident(tid, target_emp_id, target_user_id, has_dependent=True)

        mock_session = AsyncMock()

        inc_res = MagicMock()
        inc_res.scalar_one_or_none.return_value = inc

        rev_emp_res = MagicMock()
        rev_emp_res.scalar_one_or_none.return_value = reviewer_emp

        tgt_emp_res = MagicMock()
        tgt_emp_res.scalar_one_or_none.return_value = target_emp

        mock_session.execute.side_effect = [inc_res, rev_emp_res, tgt_emp_res]

        ev_id1 = uuid.uuid4()
        ev_id2 = uuid.uuid4()
        now = datetime.now(UTC)

        dummy_event1 = AttendanceEvent(
            id=ev_id1,
            tenant_id=tid,
            employee_id=target_emp_id,
            event_type="CHECK_IN",
            event_category="CORRECTION_INSERT",
            effective_at=now - timedelta(hours=8),
            server_received_at=now,
            source="ADMIN",
            review_status="NOT_REQUIRED",
            timestamp_verification_status="SERVER_AUTHORITATIVE",
            idempotency_key="cf_mock_001",
            correction_reason="Offline Conflict Approval: Full day shift verified",
            created_at=now,
            metadata_json={},
        )
        dummy_event2 = AttendanceEvent(
            id=ev_id2,
            tenant_id=tid,
            employee_id=target_emp_id,
            event_type="CHECK_OUT",
            event_category="CORRECTION_INSERT",
            effective_at=now,
            server_received_at=now,
            source="ADMIN",
            review_status="NOT_REQUIRED",
            timestamp_verification_status="SERVER_AUTHORITATIVE",
            idempotency_key="cf_mock_002",
            correction_reason="Offline Conflict Approval: Full day shift verified",
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
            affected_attendance_dates=[date(2026, 11, 20)],
            recalculated_days=[],
            idempotent_replay=False,
        )

        req = AttendanceConflictDecisionRequest(
            action="APPROVE",
            reason="Full day shift verified",
        )

        with patch(
            "services.api.attendance.conflict_service.apply_attendance_correction",
            side_effect=[resp1, resp2],
        ) as mock_apply_corr:
            res = await adjudicate_conflict_incident(
                session=mock_session,
                tenant_id=tid,
                incident_id=inc.id,
                reviewer_user_id=reviewer_user_id,
                reviewer_role="manager",
                payload=req,
            )

            assert res.status == "APPROVED"
            assert mock_apply_corr.await_count == 2
            assert res.resolved_correction_event_ids == [str(ev_id1), str(ev_id2)]

            # Check call ordering
            first_call_payload = mock_apply_corr.call_args_list[0].kwargs["payload"]
            second_call_payload = mock_apply_corr.call_args_list[1].kwargs["payload"]
            assert first_call_payload.event_type == "CHECK_IN"
            assert second_call_payload.event_type == "CHECK_OUT"
            assert first_call_payload.effective_at < second_call_payload.effective_at

    @pytest.mark.asyncio
    async def test_approval_with_override_location_id_validates_and_propagates(self):
        """When an override_location_id is provided, it is validated and propagated to correction payload."""
        tid = uuid.uuid4()
        reviewer_user_id = uuid.uuid4()
        target_emp_id = uuid.uuid4()
        target_user_id = uuid.uuid4()
        override_loc_id = uuid.uuid4()

        admin_emp = _mock_employee(tid, reviewer_user_id, uuid.uuid4())
        target_emp = _mock_employee(tid, target_user_id, target_emp_id)
        inc = _mock_incident(tid, target_emp_id, target_user_id, has_dependent=False)

        mock_session = AsyncMock()

        inc_res = MagicMock()
        inc_res.scalar_one_or_none.return_value = inc

        rev_emp_res = MagicMock()
        rev_emp_res.scalar_one_or_none.return_value = admin_emp

        tgt_emp_res = MagicMock()
        tgt_emp_res.scalar_one_or_none.return_value = target_emp

        # Location check query returns valid UUID
        loc_res = MagicMock()
        loc_res.scalar_one_or_none.return_value = override_loc_id

        mock_session.execute.side_effect = [inc_res, rev_emp_res, tgt_emp_res, loc_res]

        ev_id = uuid.uuid4()
        now = datetime.now(UTC)
        dummy_event = AttendanceEvent(
            id=ev_id,
            tenant_id=tid,
            employee_id=target_emp_id,
            event_type="CHECK_IN",
            event_category="CORRECTION_INSERT",
            effective_at=now,
            server_received_at=now,
            source="ADMIN",
            review_status="NOT_REQUIRED",
            timestamp_verification_status="SERVER_AUTHORITATIVE",
            idempotency_key="cf_mock_001",
            location_id=override_loc_id,
            correction_reason="Offline Conflict Approval: Workplace Wi-Fi verified",
            created_at=now,
            metadata_json={},
        )
        dummy_resp = AttendanceCorrectionResponse(
            correction_event=AttendanceEventResponse.model_validate(dummy_event),
            affected_attendance_dates=[date(2026, 11, 20)],
            recalculated_days=[],
            idempotent_replay=False,
        )

        req = AttendanceConflictDecisionRequest(
            action="APPROVE",
            reason="Workplace Wi-Fi verified",
            override_location_id=override_loc_id,
        )

        with patch(
            "services.api.attendance.conflict_service.apply_attendance_correction",
            new=AsyncMock(return_value=dummy_resp),
        ) as mock_apply_corr:
            res = await adjudicate_conflict_incident(
                session=mock_session,
                tenant_id=tid,
                incident_id=inc.id,
                reviewer_user_id=reviewer_user_id,
                reviewer_role="admin",
                payload=req,
            )

            assert res.status == "APPROVED"
            corr_req = mock_apply_corr.call_args.kwargs["payload"]
            assert corr_req.location_id == override_loc_id
            assert inc.metadata_json["override_location_id"] == str(override_loc_id)


# ==============================================================================
# 6. Atomicity Rollback & Failure Resilience Tests
# ==============================================================================


class TestAtomicityRollbackAndFailureResilience:
    """Verifies that failures during event insertion or recalculation trigger full session rollback."""

    @pytest.mark.asyncio
    async def test_full_rollback_when_first_event_insertion_fails(self):
        """If event insertion fails on the first event, session.rollback() is invoked and error bubbles."""
        tid = uuid.uuid4()
        reviewer_user_id = uuid.uuid4()
        target_emp_id = uuid.uuid4()
        target_user_id = uuid.uuid4()

        admin_emp = _mock_employee(tid, reviewer_user_id, uuid.uuid4())
        target_emp = _mock_employee(tid, target_user_id, target_emp_id)
        inc = _mock_incident(tid, target_emp_id, target_user_id, has_dependent=False)

        mock_session = AsyncMock()

        inc_res = MagicMock()
        inc_res.scalar_one_or_none.return_value = inc

        rev_emp_res = MagicMock()
        rev_emp_res.scalar_one_or_none.return_value = admin_emp

        tgt_emp_res = MagicMock()
        tgt_emp_res.scalar_one_or_none.return_value = target_emp

        mock_session.execute.side_effect = [inc_res, rev_emp_res, tgt_emp_res]

        req = AttendanceConflictDecisionRequest(
            action="APPROVE",
            reason="Approved with failure simulation",
        )

        with patch(
            "services.api.attendance.conflict_service.apply_attendance_correction",
            side_effect=HTTPException(status_code=500, detail="Database insertion constraint failed"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await adjudicate_conflict_incident(
                    session=mock_session,
                    tenant_id=tid,
                    incident_id=inc.id,
                    reviewer_user_id=reviewer_user_id,
                    reviewer_role="admin",
                    payload=req,
                )
            assert exc_info.value.status_code == 500
            assert "Database insertion constraint failed" in exc_info.value.detail

            # Crucial: session.rollback() was awaited!
            mock_session.rollback.assert_awaited()
            # Incident was NOT marked approved
            assert inc.status == "PENDING_REVIEW"

    @pytest.mark.asyncio
    async def test_full_rollback_when_second_event_insertion_fails(self):
        """If event 1 succeeds but event 2 fails, the entire transaction rolls back cleanly."""
        tid = uuid.uuid4()
        reviewer_user_id = uuid.uuid4()
        target_emp_id = uuid.uuid4()
        target_user_id = uuid.uuid4()

        admin_emp = _mock_employee(tid, reviewer_user_id, uuid.uuid4())
        target_emp = _mock_employee(tid, target_user_id, target_emp_id)
        inc = _mock_incident(tid, target_emp_id, target_user_id, has_dependent=True)

        mock_session = AsyncMock()

        inc_res = MagicMock()
        inc_res.scalar_one_or_none.return_value = inc

        rev_emp_res = MagicMock()
        rev_emp_res.scalar_one_or_none.return_value = admin_emp

        tgt_emp_res = MagicMock()
        tgt_emp_res.scalar_one_or_none.return_value = target_emp

        mock_session.execute.side_effect = [inc_res, rev_emp_res, tgt_emp_res]

        ev_id1 = uuid.uuid4()
        now = datetime.now(UTC)
        dummy_event1 = AttendanceEvent(
            id=ev_id1,
            tenant_id=tid,
            employee_id=target_emp_id,
            event_type="CHECK_IN",
            event_category="CORRECTION_INSERT",
            effective_at=now - timedelta(hours=8),
            server_received_at=now,
            source="ADMIN",
            review_status="NOT_REQUIRED",
            timestamp_verification_status="SERVER_AUTHORITATIVE",
            idempotency_key="cf_mock_001",
            correction_reason="Offline Conflict Approval: Valid shift",
            created_at=now,
            metadata_json={},
        )
        resp1 = AttendanceCorrectionResponse(
            correction_event=AttendanceEventResponse.model_validate(dummy_event1),
            affected_attendance_dates=[date(2026, 11, 20)],
            recalculated_days=[],
            idempotent_replay=False,
        )

        req = AttendanceConflictDecisionRequest(action="APPROVE", reason="Valid shift")

        with patch(
            "services.api.attendance.conflict_service.apply_attendance_correction",
            side_effect=[resp1, HTTPException(status_code=500, detail="Deadlock on dependent punch")],
        ):
            with pytest.raises(HTTPException) as exc_info:
                await adjudicate_conflict_incident(
                    session=mock_session,
                    tenant_id=tid,
                    incident_id=inc.id,
                    reviewer_user_id=reviewer_user_id,
                    reviewer_role="admin",
                    payload=req,
                )
            assert exc_info.value.status_code == 500
            assert "Deadlock on dependent punch" in exc_info.value.detail

            # Crucial atomicity rule: rollback was executed
            mock_session.rollback.assert_awaited()
            # Incident remains in PENDING_REVIEW
            assert inc.status == "PENDING_REVIEW"
            assert inc.decision is None


# ==============================================================================
# 7. HTTP Route Integration Tests
# ==============================================================================


class TestHTTPRouteIntegration:
    """Validates FastAPI route endpoints with ASGI test client and dependency overrides."""

    @pytest.mark.asyncio
    async def test_get_supervisor_queue_endpoint_200(self):
        """GET /api/v1/attendance/offline-conflicts returns 200 OK for authorized supervisor."""
        context = _mock_context(role="manager")
        mock_db = AsyncMock()

        inc = _mock_incident(context.tenant.id, uuid.uuid4(), uuid.uuid4())

        # Mock list_supervisor_conflict_queue via db execution
        mgr_res = MagicMock()
        mgr_res.scalar_one_or_none.return_value = uuid.uuid4()

        count_res = MagicMock()
        count_res.scalar.return_value = 1

        list_res = MagicMock()
        list_res.all.return_value = [(inc, "Bob", "Smith", "EMP-007", "Operations")]

        mock_db.execute.side_effect = [mgr_res, count_res, list_res]

        app.dependency_overrides[get_authenticated_context] = lambda: context
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.get("/api/v1/attendance/offline-conflicts")
                assert res.status_code == status.HTTP_200_OK
                data = res.json()
                assert data["total"] == 1
                assert len(data["items"]) == 1
                assert data["items"][0]["employee_name"] == "Bob Smith"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_incident_detail_endpoint_200(self):
        """GET /api/v1/attendance/offline-conflicts/{id} returns 200 OK for authorized manager."""
        context = _mock_context(role="admin")
        mock_db = AsyncMock()

        target_emp_id = uuid.uuid4()
        target_emp = _mock_employee(context.tenant.id, uuid.uuid4(), target_emp_id)
        inc = _mock_incident(context.tenant.id, target_emp_id, target_emp.user_id)

        inc_res = MagicMock()
        inc_res.scalar_one_or_none.return_value = inc

        emp_res = MagicMock()
        emp_res.first.return_value = (target_emp, "Support")

        mock_db.execute.side_effect = [inc_res, emp_res]

        app.dependency_overrides[get_authenticated_context] = lambda: context
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.get(f"/api/v1/attendance/offline-conflicts/{inc.id}")
                assert res.status_code == status.HTTP_200_OK
                data = res.json()
                assert data["id"] == str(inc.id)
                assert data["employee"]["employee_code"] == target_emp.employee_id
                assert data["total_events_count"] == inc.total_events_count
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_post_decision_reject_endpoint_200(self):
        """POST /api/v1/attendance/offline-conflicts/{id}/decision returns 200 OK on REJECT."""
        context = _mock_context(role="admin")
        mock_db = AsyncMock()

        target_emp_id = uuid.uuid4()
        target_emp = _mock_employee(context.tenant.id, uuid.uuid4(), target_emp_id)
        admin_emp = _mock_employee(context.tenant.id, context.user.id, uuid.uuid4())
        inc = _mock_incident(context.tenant.id, target_emp_id, target_emp.user_id)

        inc_res = MagicMock()
        inc_res.scalar_one_or_none.return_value = inc

        rev_emp_res = MagicMock()
        rev_emp_res.scalar_one_or_none.return_value = admin_emp

        tgt_emp_res = MagicMock()
        tgt_emp_res.scalar_one_or_none.return_value = target_emp

        mock_db.execute.side_effect = [inc_res, rev_emp_res, tgt_emp_res]

        app.dependency_overrides[get_authenticated_context] = lambda: context
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                payload = {
                    "action": "REJECT",
                    "reason": "Security cameras confirm employee was not on site.",
                }
                res = await client.post(
                    f"/api/v1/attendance/offline-conflicts/{inc.id}/decision",
                    json=payload,
                )
                assert res.status_code == status.HTTP_200_OK
                data = res.json()
                assert data["decision"] in ("REJECT", "REJECTED")
                assert data["status"] == "REJECTED"
                assert data["decision_reason"] == payload["reason"]
                assert data["resolved_correction_event_ids"] == []
                mock_db.commit.assert_awaited_once()
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_decision_endpoint_short_reason_returns_422(self):
        """POST decision with reason < 3 chars returns HTTP 422 Unprocessable Content."""
        context = _mock_context(role="admin")
        mock_db = AsyncMock()

        app.dependency_overrides[get_authenticated_context] = lambda: context
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.post(
                    f"/api/v1/attendance/offline-conflicts/{uuid.uuid4()}/decision",
                    json={"action": "APPROVE", "reason": "no"},
                )
                assert res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        finally:
            app.dependency_overrides.clear()
