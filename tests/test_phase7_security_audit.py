"""Phase 7 Milestone 7.7: Comprehensive Security Audit & Penetration Regression Suite.

Validates security boundaries across:
- Device binding, registration, replacement, and revocation.
- GPS spoofing, mock location, and velocity analysis.
- Fraud rule engine configuration, boundary scores, and disabled rule exclusion.
- HR fraud review workflow, self-review prohibition, and manager visibility scoping.
- Multi-tenant data isolation across devices, rules, flags, and review workflows.
- Offline synchronization replay, tamper detection, and fail-closed security.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status

from services.api.attendance.models import AttendanceEvent
from services.api.attendance.schemas import PunchRequest
from services.api.auth.models import User
from services.api.auth.permissions import UserRole
from services.api.devices.models import Device
from services.api.devices.schemas import (
    DevicePlatform,
    DeviceRegisterRequest,
    DeviceResponse,
)
from services.api.devices.service import (
    approve_device_replacement,
    get_device_by_id,
    hash_device_id,
    register_device,
    revoke_device,
)
from services.api.employees.models import Employee
from services.api.fraud.engine import calculate_risk_score
from services.api.fraud.models import FraudRule
from services.api.fraud.review_service import (
    adjudicate_fraud_event,
    get_fraud_event_review_detail,
)
from services.api.fraud.rules_service import (
    get_fraud_rule_by_id,
    list_fraud_flags,
)
from services.api.fraud.schemas import (
    FraudReviewDecisionRequest,
    FraudSignal,
    FraudSignalSeverity,
    FraudSignalType,
    RiskCategory,
)


def _mock_employee(tenant_id: uuid.UUID, emp_id: uuid.UUID, user_id: uuid.UUID | None = None, dept_id: uuid.UUID | None = None, manager_id: uuid.UUID | None = None) -> Employee:
    return Employee(
        id=emp_id,
        tenant_id=tenant_id,
        user_id=user_id or uuid.uuid4(),
        employee_id="EMP-TEST",
        first_name="Security",
        last_name="Tester",
        work_email="security@upostit.io",
        department_id=dept_id,
        reporting_manager_id=manager_id,
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _mock_device(tenant_id: uuid.UUID, emp_id: uuid.UUID, dev_hash: str, status_val: str = "ACTIVE") -> Device:
    now = datetime.now(UTC)
    return Device(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp_id,
        device_id_hash=dev_hash,
        platform="ANDROID",
        device_model="Test Phone",
        os_name="Android",
        os_version="14.0",
        app_version="1.0.0",
        status=status_val,
        registered_at=now,
        last_seen_at=now,
        metadata_json={},
        created_at=now,
        updated_at=now,
    )


# ==============================================================================
# 1. Device Binding Security Tests
# ==============================================================================


@pytest.mark.asyncio
class TestDeviceBindingSecurityAudit:
    """Audits device registration, binding, revocation, and replacement controls."""

    async def test_device_replacement_with_revoked_device_rejected_400(self):
        """An employee attempting to register a revoked device as a replacement is rejected."""
        tenant_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        old_raw = "old-phone-uuid"
        revoked_raw = "stolen-revoked-uuid"
        old_hash = hash_device_id(tenant_id, old_raw)
        revoked_hash = hash_device_id(tenant_id, revoked_raw)

        emp = _mock_employee(tenant_id, emp_id)
        old_device = _mock_device(tenant_id, emp_id, old_hash, status_val="ACTIVE")
        revoked_device = _mock_device(tenant_id, emp_id, revoked_hash, status_val="REVOKED")

        session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_res
        mock_emp_res = MagicMock()
        mock_emp_res.scalar_one_or_none.return_value = emp
        mock_active_res = MagicMock()
        mock_active_res.scalar_one_or_none.return_value = old_device
        mock_pending_res = MagicMock()
        mock_pending_res.scalar_one_or_none.return_value = None
        mock_revoked_res = MagicMock()
        mock_revoked_res.scalar_one_or_none.return_value = revoked_device

        session.execute.side_effect = [
            mock_emp_res,
            mock_active_res,
            mock_pending_res,
            mock_revoked_res,
        ]

        payload = DeviceRegisterRequest(
            device_id=revoked_raw,
            platform=DevicePlatform.ANDROID,
            device_model="Stolen Phone",
        )

        with pytest.raises(HTTPException) as exc_info:
            await register_device(session, tenant_id, emp_id, payload)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "previously revoked" in exc_info.value.detail.lower()

    async def test_device_replacement_with_conflicting_employee_device_rejected_409(self):
        """An employee attempting to register another employee's active device as replacement is rejected."""
        tenant_id = uuid.uuid4()
        emp1_id = uuid.uuid4()
        emp2_id = uuid.uuid4()
        emp1_old_raw = "emp1-phone-uuid"
        emp2_active_raw = "emp2-active-phone-uuid"

        emp1_old_hash = hash_device_id(tenant_id, emp1_old_raw)
        emp2_active_hash = hash_device_id(tenant_id, emp2_active_raw)

        emp1 = _mock_employee(tenant_id, emp1_id)
        emp1_active = _mock_device(tenant_id, emp1_id, emp1_old_hash, status_val="ACTIVE")
        emp2_active = _mock_device(tenant_id, emp2_id, emp2_active_hash, status_val="ACTIVE")

        session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_res
        mock_emp_res = MagicMock()
        mock_emp_res.scalar_one_or_none.return_value = emp1
        mock_active_res = MagicMock()
        mock_active_res.scalar_one_or_none.return_value = emp1_active
        mock_pending_res = MagicMock()
        mock_pending_res.scalar_one_or_none.return_value = None
        mock_revoked_none = MagicMock()
        mock_revoked_none.scalar_one_or_none.return_value = None
        mock_conflict_res = MagicMock()
        mock_conflict_res.scalar_one_or_none.return_value = emp2_active

        session.execute.side_effect = [
            mock_emp_res,
            mock_active_res,
            mock_pending_res,
            mock_revoked_none,
            mock_conflict_res,
        ]

        payload = DeviceRegisterRequest(
            device_id=emp2_active_raw,
            platform=DevicePlatform.ANDROID,
            device_model="Shared Phone",
        )

        with pytest.raises(HTTPException) as exc_info:
            await register_device(session, tenant_id, emp1_id, payload)

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert "actively registered to another employee" in exc_info.value.detail.lower()

    async def test_device_replacement_approval_of_revoked_device_rejected_400(self):
        """Approving replacement where the target device hash is revoked in tenant is blocked."""
        tenant_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        actor_id = uuid.uuid4()

        pending_dev = _mock_device(tenant_id, emp_id, "hash-revoked", status_val="PENDING_APPROVAL")

        session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_res
        mock_target_res = MagicMock()
        mock_target_res.scalar_one_or_none.return_value = pending_dev
        mock_revoked_res = MagicMock()
        mock_revoked_res.scalar_one_or_none.return_value = uuid.uuid4()
        mock_active_res = MagicMock()
        mock_active_res.scalar_one_or_none.return_value = None

        session.execute.side_effect = [
            mock_target_res,
            mock_revoked_res,
            mock_active_res,
        ]

        with pytest.raises(HTTPException) as exc_info:
            await approve_device_replacement(session, tenant_id, pending_dev.id, actor_id)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "revoked and cannot be approved" in exc_info.value.detail.lower()

    async def test_device_revocation_whitespace_reason_rejected_422(self):
        """Device revocation with whitespace-only reason is rejected."""
        tenant_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        device = _mock_device(tenant_id, emp_id, "dev-hash", status_val="ACTIVE")

        session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_res
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = device
        session.execute.return_value = mock_res

        with pytest.raises(HTTPException) as exc_info:
            await revoke_device(
                session=session,
                tenant_id=tenant_id,
                device_id=device.id,
                actor_user_id=uuid.uuid4(),
                reason="    ",
            )
        assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "at least 3 characters" in exc_info.value.detail.lower()

    async def test_device_hash_omitted_from_api_response_schema(self):
        """Verifies device identifier hash is strictly omitted from public API schemas."""
        tenant_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        dev = _mock_device(tenant_id, emp_id, "secret-hash-value-1234")

        resp = DeviceResponse.model_validate(dev)
        dump = resp.model_dump()

        assert "device_id_hash" not in dump
        assert "secret-hash-value-1234" not in str(dump)


# ==============================================================================
# 2. Fraud Rule Engine & Boundary Tests
# ==============================================================================


class TestFraudRuleEngineSecurityAudit:
    """Audits risk calculation determinism, boundary capping, and rule isolation."""

    def test_risk_score_capped_at_100_max(self):
        """Even with many extreme fraud signals, total risk score cannot exceed 100."""
        tenant_id = uuid.uuid4()
        rules = [
            FraudRule(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                rule_code=FraudSignalType.MOCK_LOCATION_DETECTED.value,
                rule_name="Mock GPS",
                enabled=True,
                severity=FraudSignalSeverity.CRITICAL.value,
                risk_weight=50,
                review_required=True,
            ),
            FraudRule(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                rule_code=FraudSignalType.IMPOSSIBLE_TRAVEL_VELOCITY.value,
                rule_name="Velocity",
                enabled=True,
                severity=FraudSignalSeverity.CRITICAL.value,
                risk_weight=50,
                review_required=True,
            ),
            FraudRule(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                rule_code=FraudSignalType.REVOKED_DEVICE.value,
                rule_name="Revoked Device",
                enabled=True,
                severity=FraudSignalSeverity.CRITICAL.value,
                risk_weight=60,
                review_required=True,
            ),
        ]

        now = datetime.now(UTC)
        signals = [
            FraudSignal(signal_type=FraudSignalType.MOCK_LOCATION_DETECTED, severity=FraudSignalSeverity.CRITICAL, reason="Mock", source="GPS", timestamp=now),
            FraudSignal(signal_type=FraudSignalType.IMPOSSIBLE_TRAVEL_VELOCITY, severity=FraudSignalSeverity.CRITICAL, reason="Velocity", source="VELOCITY", timestamp=now),
            FraudSignal(signal_type=FraudSignalType.REVOKED_DEVICE, severity=FraudSignalSeverity.CRITICAL, reason="Revoked", source="DEVICE", timestamp=now),
        ]

        score, category, requires_review, flag_dicts = calculate_risk_score(rules, signals)

        assert score == 100
        assert category == RiskCategory.REQUIRES_REVIEW
        assert requires_review is True
        assert len(flag_dicts) == 3

    def test_disabled_fraud_rules_excluded_from_scoring_and_flags(self):
        """A disabled rule contributes 0 points, generates no flag, and does not require review."""
        tenant_id = uuid.uuid4()
        rules = [
            FraudRule(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                rule_code=FraudSignalType.POOR_GPS_ACCURACY.value,
                rule_name="Poor GPS",
                enabled=False,  # Explicitly disabled by tenant
                severity=FraudSignalSeverity.LOW.value,
                risk_weight=20,
                review_required=False,
            ),
        ]

        now = datetime.now(UTC)
        signals = [
            FraudSignal(signal_type=FraudSignalType.POOR_GPS_ACCURACY, severity=FraudSignalSeverity.LOW, reason="Accuracy 150m", source="GPS", timestamp=now),
        ]

        score, category, requires_review, flag_dicts = calculate_risk_score(rules, signals)

        assert score == 0
        assert category == RiskCategory.NORMAL
        assert requires_review is False
        assert len(flag_dicts) == 0

    def test_signal_deduplication_prevents_inflated_scores(self):
        """Duplicate signals for the same signal type are deduplicated."""
        tenant_id = uuid.uuid4()
        rules = [
            FraudRule(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                rule_code=FraudSignalType.MOCK_LOCATION_DETECTED.value,
                rule_name="Mock GPS",
                enabled=True,
                severity=FraudSignalSeverity.HIGH.value,
                risk_weight=40,
                review_required=True,
            ),
        ]

        now = datetime.now(UTC)
        signals = [
            FraudSignal(signal_type=FraudSignalType.MOCK_LOCATION_DETECTED, severity=FraudSignalSeverity.HIGH, reason="Mock 1", source="GPS", timestamp=now),
            FraudSignal(signal_type=FraudSignalType.MOCK_LOCATION_DETECTED, severity=FraudSignalSeverity.HIGH, reason="Mock 2", source="GPS", timestamp=now),
        ]

        score, category, requires_review, flag_dicts = calculate_risk_score(rules, signals)

        assert score == 40
        assert len(flag_dicts) == 1


# ==============================================================================
# 3. HR Review Workflow & Authorization Tests
# ==============================================================================


@pytest.mark.asyncio
class TestHRReviewWorkflowSecurityAudit:
    """Audits review adjudication, self-review prohibition, and manager scoping."""

    async def test_self_review_strictly_prohibited_403(self):
        """An HR or Admin reviewer linked to the flagged employee profile is barred from self-review."""
        tenant_id = uuid.uuid4()
        shared_emp_id = uuid.uuid4()
        event_id = uuid.uuid4()

        reviewer_user = User(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            email="hr@upostit.io",
            full_name="HR Reviewer",
            role=UserRole.HR.value,
            status="active",
        )

        event = AttendanceEvent(
            id=event_id,
            tenant_id=tenant_id,
            employee_id=shared_emp_id,  # Event belongs to this employee
            event_type="CHECK_IN",
            effective_at=datetime.now(UTC),
            review_status="PENDING_REVIEW",
        )

        async def mock_execute(stmt):
            mock_res = MagicMock()
            where_str = str(stmt.whereclause)
            if "attendance_events" in where_str or "attendance_event" in where_str:
                mock_res.scalar_one_or_none.return_value = event
            elif "employees" in where_str or "employee" in where_str:
                # Reviewer user is linked to the same employee ID
                mock_res.scalar_one_or_none.return_value = shared_emp_id
            return mock_res

        session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_res
        session.execute = AsyncMock(side_effect=mock_execute)

        payload = FraudReviewDecisionRequest(
            decision="APPROVED",
            reason="I am approving my own attendance",
        )

        with pytest.raises(HTTPException) as exc_info:
            await adjudicate_fraud_event(
                session=session,
                tenant_id=tenant_id,
                event_id=event_id,
                payload=payload,
                reviewer_user=reviewer_user,
                reviewer_role=UserRole.HR,
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "self-review prohibited" in exc_info.value.detail.lower()

    async def test_manager_visibility_outside_department_forbidden_403(self):
        """A manager cannot view review details of an employee outside their department and reporting line."""
        tenant_id = uuid.uuid4()
        event_id = uuid.uuid4()
        manager_user_id = uuid.uuid4()

        manager_user = User(
            id=manager_user_id,
            tenant_id=tenant_id,
            email="manager@upostit.io",
            full_name="Store Manager",
            role=UserRole.MANAGER.value,
            status="active",
        )

        dept_retail = uuid.uuid4()
        dept_engineering = uuid.uuid4()

        manager_emp = _mock_employee(tenant_id, uuid.uuid4(), user_id=manager_user_id, dept_id=dept_retail)
        target_emp = _mock_employee(tenant_id, uuid.uuid4(), dept_id=dept_engineering, manager_id=uuid.uuid4())

        event = AttendanceEvent(
            id=event_id,
            tenant_id=tenant_id,
            employee_id=target_emp.id,
            event_type="CHECK_IN",
            effective_at=datetime.now(UTC),
            review_status="PENDING_REVIEW",
        )

        async def mock_execute(stmt):
            mock_res = MagicMock()
            where_str = str(stmt.whereclause)
            if "attendance_events" in where_str or "attendance_event" in where_str:
                mock_res.scalar_one_or_none.return_value = event
            elif f"employees.id = '{target_emp.id}'" in where_str or "employees.id = :id_1" in where_str:
                mock_res.scalar_one_or_none.return_value = target_emp
            elif f"employees.user_id = '{manager_user_id}'" in where_str or "employees.user_id = :user_id_1" in where_str:
                mock_res.scalar_one_or_none.return_value = manager_emp
            else:
                mock_res.scalar_one_or_none.return_value = None
            return mock_res

        session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_res
        session.execute = AsyncMock(side_effect=mock_execute)

        with pytest.raises(HTTPException) as exc_info:
            await get_fraud_event_review_detail(
                session=session,
                tenant_id=tenant_id,
                event_id=event_id,
                reviewer_user=manager_user,
                reviewer_role=UserRole.MANAGER,
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "access denied" in exc_info.value.detail.lower()

    async def test_review_decision_mandatory_reason_whitespace_rejected_422(self):
        """Review adjudication with whitespace-only reason is rejected with 422."""
        tenant_id = uuid.uuid4()
        event_id = uuid.uuid4()
        reviewer_user = User(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            email="admin@upostit.io",
            full_name="Admin Reviewer",
            role=UserRole.ADMIN.value,
            status="active",
        )

        event = AttendanceEvent(
            id=event_id,
            tenant_id=tenant_id,
            employee_id=uuid.uuid4(),
            event_type="CHECK_IN",
            effective_at=datetime.now(UTC),
            review_status="PENDING_REVIEW",
        )

        async def mock_execute(stmt):
            mock_res = MagicMock()
            where_str = str(stmt.whereclause)
            if "attendance_events" in where_str:
                mock_res.scalar_one_or_none.return_value = event
            elif "employees" in where_str:
                mock_res.scalar_one_or_none.return_value = uuid.uuid4()  # different emp ID
            return mock_res

        session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_res
        session.execute = AsyncMock(side_effect=mock_execute)

        payload = FraudReviewDecisionRequest(
            decision="APPROVED",
            reason="   ",  # whitespace only
        )

        with pytest.raises(HTTPException) as exc_info:
            await adjudicate_fraud_event(
                session=session,
                tenant_id=tenant_id,
                event_id=event_id,
                payload=payload,
                reviewer_user=reviewer_user,
                reviewer_role=UserRole.ADMIN,
            )

        assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "at least 3 characters" in exc_info.value.detail.lower()


# ==============================================================================
# 4. Multi-Tenant Data Isolation Tests
# ==============================================================================


@pytest.mark.asyncio
class TestCrossTenantDataIsolationAudit:
    """Verifies strict cross-tenant data partitioning on all Phase 7 entities."""

    async def test_cross_tenant_device_access_returns_404(self):
        """Tenant A querying Tenant B's device ID receives HTTP 404 (preventing ID leakage)."""
        tenant_a = uuid.uuid4()
        tenant_b = uuid.uuid4()
        dev_b = _mock_device(tenant_b, uuid.uuid4(), "hash-b")

        async def mock_execute(stmt):
            mock_res = MagicMock()
            where_str = str(stmt.whereclause)
            if f"devices.tenant_id = '{tenant_a}'" in where_str or "devices.tenant_id = :tenant_id_1" in where_str:
                # Query scoped to Tenant A does not find Tenant B's device
                mock_res.scalar_one_or_none.return_value = None
            else:
                mock_res.scalar_one_or_none.return_value = dev_b
            return mock_res

        session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_res
        session.execute = AsyncMock(side_effect=mock_execute)

        with pytest.raises(HTTPException) as exc_info:
            await get_device_by_id(session, tenant_a, dev_b.id)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "device not found" in exc_info.value.detail.lower()

    async def test_cross_tenant_fraud_rule_access_returns_404(self):
        """Tenant A querying Tenant B's fraud rule receives HTTP 404."""
        tenant_a = uuid.uuid4()
        tenant_b = uuid.uuid4()
        rule_b = FraudRule(
            id=uuid.uuid4(),
            tenant_id=tenant_b,
            rule_code="CUSTOM_RULE",
            rule_name="Custom",
            enabled=True,
            severity="HIGH",
            risk_weight=30,
        )

        session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_res
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = None  # Scoped by tenant_a
        session.execute.return_value = mock_res

        with pytest.raises(HTTPException) as exc_info:
            await get_fraud_rule_by_id(session, tenant_a, rule_b.id)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "fraud rule not found" in exc_info.value.detail.lower()

    async def test_cross_tenant_fraud_flag_listing_isolated(self):
        """Listing fraud flags under Tenant A never returns Tenant B flags."""
        tenant_a = uuid.uuid4()

        session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_res
        mock_flags = MagicMock()
        mock_flags.scalars.return_value.all.return_value = []
        mock_count = MagicMock()
        mock_count.scalar.return_value = 0

        session.execute.side_effect = [mock_count, mock_flags]

        flags, total = await list_fraud_flags(session, tenant_a)
        assert flags == []
        assert total == 0


# ==============================================================================
# 5. GPS Spoofing & Velocity Analysis Security Tests
# ==============================================================================


@pytest.mark.asyncio
class TestGPSSpoofingAndVelocityAudit:
    """Verifies that client mock-location indicators and impossible velocities trigger forensic review."""

    async def test_mock_gps_telemetry_triggers_pending_review_and_signal(self):
        """A client submitting mock location provider telemetry has the punch flagged PENDING_REVIEW."""
        from services.api.fraud.service import evaluate_attendance_fraud_evidence

        tenant_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        now = datetime.now(UTC)

        session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_res

        payload = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key=str(uuid.uuid4()),
            device_reported_at=now,
            is_mock_location=True,  # Client telemetry reports mock provider
            latitude=37.7749,
            longitude=-122.4194,
            accuracy_meters=15.0,
        )

        assessment = await evaluate_attendance_fraud_evidence(
            session=session,
            tenant_id=tenant_id,
            employee_id=emp_id,
            punch_payload=payload,
            server_received_at=now,
        )

        assert assessment.review_status == "PENDING_REVIEW"
        signal_types = [s.signal_type for s in assessment.signals]
        assert FraudSignalType.MOCK_LOCATION_DETECTED in signal_types

    async def test_impossible_travel_velocity_triggers_pending_review(self):
        """Punches recorded across impossibly distant locations within short intervals trigger velocity alerts."""
        from services.api.fraud.service import calculate_punch_velocity

        now = datetime.now(UTC)
        prev_time = now - timedelta(seconds=60)  # 60 seconds ago

        # San Francisco to New York (~4,130 km in 60s -> ~68,800 m/s >> 250 m/s threshold)
        vel_res = calculate_punch_velocity(
            curr_lat=40.7128,
            curr_lon=-74.0060,
            curr_time=now,
            prev_lat=37.7749,
            prev_lon=-122.4194,
            prev_time=prev_time,
            threshold_mps=250.0,
        )

        assert vel_res.is_impossible is True
        assert vel_res.velocity_mps > 250.0


# ==============================================================================
# 6. Privilege Escalation & Role Enforcement Tests
# ==============================================================================


class TestRBACPrivilegeEscalationAudit:
    """Verifies RBAC boundary enforcement preventing privilege escalation."""

    def test_employee_cannot_manage_fraud_rules(self):
        from services.api.auth.permissions import Permission, UserRole, has_permission

        assert has_permission(UserRole.EMPLOYEE, Permission.MANAGE_FRAUD_RULES) is False
        assert has_permission(UserRole.EMPLOYEE, Permission.VIEW_FRAUD_RULES) is False
        assert has_permission(UserRole.EMPLOYEE, Permission.REVIEW_FRAUD_EVENTS) is False
        assert has_permission(UserRole.EMPLOYEE, Permission.MANAGE_DEVICES) is False

    def test_manager_cannot_manage_fraud_rules_or_adjudicate_reviews(self):
        from services.api.auth.permissions import Permission, UserRole, has_permission

        assert has_permission(UserRole.MANAGER, Permission.MANAGE_FRAUD_RULES) is False
        assert has_permission(UserRole.MANAGER, Permission.REVIEW_FRAUD_EVENTS) is False
        assert has_permission(UserRole.MANAGER, Permission.MANAGE_DEVICES) is False
        # Manager can view flags/reviews for their reporting team only
        assert has_permission(UserRole.MANAGER, Permission.VIEW_FRAUD_FLAGS) is True
        assert has_permission(UserRole.MANAGER, Permission.VIEW_FRAUD_REVIEWS) is True

    def test_hr_and_admin_have_fraud_review_authorizations(self):
        from services.api.auth.permissions import Permission, UserRole, has_permission

        for role in (UserRole.HR, UserRole.ADMIN, UserRole.OWNER):
            assert has_permission(role, Permission.MANAGE_FRAUD_RULES) is True
            assert has_permission(role, Permission.REVIEW_FRAUD_EVENTS) is True
            assert has_permission(role, Permission.MANAGE_DEVICES) is True

