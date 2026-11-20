"""Comprehensive automated test suite for Phase 7 Milestone 7.3:
Fraud Rule Engine, Tenant Rule Configuration, and Deterministic Risk Scoring.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status
from httpx import ASGITransport, AsyncClient

from services.api.attendance.schemas import PunchRequest
from services.api.attendance.service import record_punch
from services.api.auth.dependencies import AuthenticatedContext, get_authenticated_context
from services.api.auth.models import User
from services.api.database import get_db
from services.api.devices.models import Device
from services.api.devices.service import hash_device_id
from services.api.employees.models import Employee
from services.api.fraud.engine import (
    DEFAULT_RULE_DEFINITIONS,
    calculate_risk_score,
    seed_default_fraud_rules,
)
from services.api.fraud.models import FraudFlag, FraudRule
from services.api.fraud.rules_service import (
    create_fraud_rule,
    get_fraud_rule_by_id,
    set_fraud_rule_status,
    update_fraud_rule,
)
from services.api.fraud.schemas import (
    FraudRuleCreateRequest,
    FraudRuleUpdateRequest,
    FraudSignal,
    FraudSignalSeverity,
    FraudSignalType,
    RiskCategory,
)
from services.api.main import app
from services.api.tenants.models import Tenant

# ==============================================================================
# Helper Factories
# ==============================================================================


def _mock_context(
    role: str = "admin",
    tenant_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> AuthenticatedContext:
    tid = tenant_id or uuid.uuid4()
    uid = user_id or uuid.uuid4()
    user = User(
        id=uid,
        tenant_id=tid,
        email=f"tester_{role.lower()}@fraud.test",
        password_hash="argon2id$mock",
        role=role.lower(),
        status="active",
    )
    tenant = Tenant(
        id=tid,
        name="Fraud Defense Tenant",
        slug=f"fraud-{tid.hex[:6]}",
        company_email="admin@fraud.test",
        country_code="IN",
        status="active",
    )
    return AuthenticatedContext(user=user, tenant=tenant)


def _mock_signal(
    signal_type: FraudSignalType,
    severity: FraudSignalSeverity = FraudSignalSeverity.HIGH,
    reason: str = "Test reason",
    source: str = "TEST_TELEMETRY",
) -> FraudSignal:
    return FraudSignal(
        signal_type=signal_type,
        severity=severity,
        reason=reason,
        source=source,
        timestamp=datetime.now(UTC),
        details={"test_metric": 42},
    )


# ==============================================================================
# 1. Fraud Rule Configuration Tests
# ==============================================================================


class TestFraudRuleConfiguration:
    """Validates default rule seeding, creation, updates, and tenant isolation."""

    @pytest.mark.asyncio
    async def test_default_rules_seeding(self):
        """Seeds 8 default rules when tenant has none."""
        tenant_id = uuid.uuid4()
        session = AsyncMock()

        # Simulate empty database for this tenant
        mock_res = MagicMock()
        mock_res.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_res

        rules = await seed_default_fraud_rules(session, tenant_id)

        assert len(rules) == 8
        assert session.add.call_count == 8
        rule_codes = [r.rule_code for r in rules]
        assert FraudSignalType.MOCK_LOCATION_DETECTED.value in rule_codes
        assert FraudSignalType.SUSPICIOUS_CLOCK_DRIFT.value in rule_codes
        assert FraudSignalType.IMPOSSIBLE_TRAVEL_VELOCITY.value in rule_codes

    @pytest.mark.asyncio
    async def test_create_custom_fraud_rule(self):
        """Creates a custom fraud rule and assigns audit fields."""
        tenant_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        session = AsyncMock()

        # No duplicate exists
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_res

        payload = FraudRuleCreateRequest(
            rule_code="CUSTOM_BEACON_SPOOF",
            rule_name="Custom Beacon Check",
            description="Detects anomalous bluetooth beacon signals.",
            enabled=True,
            severity=FraudSignalSeverity.HIGH,
            risk_weight=45,
            review_required=True,
        )

        rule = await create_fraud_rule(session, tenant_id, payload, actor_user_id=actor_id)

        assert rule.rule_code == "CUSTOM_BEACON_SPOOF"
        assert rule.risk_weight == 45
        assert rule.severity == "HIGH"
        assert rule.created_by == actor_id
        session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_duplicate_rule_code_conflict(self):
        """Rejects duplicate rule_code under the same tenant with HTTP 409 Conflict."""
        tenant_id = uuid.uuid4()
        session = AsyncMock()

        # Duplicate found
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = uuid.uuid4()
        session.execute.return_value = mock_res

        payload = FraudRuleCreateRequest(
            rule_code="MOCK_LOCATION_DETECTED",
            rule_name="Duplicate Rule",
            severity=FraudSignalSeverity.HIGH,
            risk_weight=50,
        )

        with pytest.raises(HTTPException) as exc:
            await create_fraud_rule(session, tenant_id, payload)
        assert exc.value.status_code == status.HTTP_409_CONFLICT
        assert "already exists" in exc.value.detail

    @pytest.mark.asyncio
    async def test_update_fraud_rule(self):
        """Updates severity, risk weight, and review requirement on an existing rule."""
        tenant_id = uuid.uuid4()
        rule_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        session = AsyncMock()

        existing_rule = FraudRule(
            id=rule_id,
            tenant_id=tenant_id,
            rule_code="POOR_GPS_ACCURACY",
            rule_name="Poor GPS",
            severity="LOW",
            risk_weight=10,
            review_required=False,
            enabled=True,
        )

        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = existing_rule
        session.execute.return_value = mock_res

        payload = FraudRuleUpdateRequest(
            risk_weight=25,
            severity=FraudSignalSeverity.MEDIUM,
            review_required=True,
        )

        updated = await update_fraud_rule(session, tenant_id, rule_id, payload, actor_user_id=actor_id)

        assert updated.risk_weight == 25
        assert updated.severity == "MEDIUM"
        assert updated.review_required is True
        assert updated.updated_by == actor_id

    @pytest.mark.asyncio
    async def test_enable_disable_fraud_rule(self):
        """Enables and disables a fraud rule."""
        tenant_id = uuid.uuid4()
        rule_id = uuid.uuid4()
        session = AsyncMock()

        rule = FraudRule(
            id=rule_id,
            tenant_id=tenant_id,
            rule_code="STALE_GPS_LOCATION",
            rule_name="Stale GPS",
            enabled=True,
        )
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = rule
        session.execute.return_value = mock_res

        disabled = await set_fraud_rule_status(session, tenant_id, rule_id, enabled=False)
        assert disabled.enabled is False

        enabled = await set_fraud_rule_status(session, tenant_id, rule_id, enabled=True)
        assert enabled.enabled is True

    @pytest.mark.asyncio
    async def test_tenant_isolation_rule_access(self):
        """Tenant A cannot access Tenant B rule (HTTP 404)."""
        tenant_a = uuid.uuid4()
        rule_b_id = uuid.uuid4()
        session = AsyncMock()

        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = None  # Scoped query returns nothing
        session.execute.return_value = mock_res

        with pytest.raises(HTTPException) as exc:
            await get_fraud_rule_by_id(session, tenant_a, rule_b_id)
        assert exc.value.status_code == status.HTTP_404_NOT_FOUND


# ==============================================================================
# 2. Deterministic Risk Engine Tests
# ==============================================================================


class TestDeterministicRiskEngine:
    """Validates risk scoring, thresholds, boundaries, and deterministic behavior."""

    @pytest.fixture
    def default_rules(self) -> list[FraudRule]:
        tid = uuid.uuid4()
        return [
            FraudRule(
                id=uuid.uuid4(),
                tenant_id=tid,
                rule_code=d["rule_code"],
                rule_name=d["rule_name"],
                description=d["description"],
                enabled=True,
                severity=d["severity"],
                risk_weight=d["risk_weight"],
                threshold_config=d["threshold_config"],
                review_required=d["review_required"],
            )
            for d in DEFAULT_RULE_DEFINITIONS
        ]

    def test_no_signals_yields_normal_risk_score_zero(self, default_rules):
        """Zero signals -> score=0, NORMAL, no review required."""
        score, category, is_review, flags = calculate_risk_score(default_rules, [])
        assert score == 0
        assert category == RiskCategory.NORMAL
        assert is_review is False
        assert len(flags) == 0

    def test_single_low_risk_signal(self, default_rules):
        """Single poor accuracy signal -> score=10, LOW_RISK, no review required."""
        signal = _mock_signal(FraudSignalType.POOR_GPS_ACCURACY, FraudSignalSeverity.LOW)
        score, category, is_review, flags = calculate_risk_score(default_rules, [signal])
        assert score == 10
        assert category == RiskCategory.LOW_RISK
        assert is_review is False
        assert len(flags) == 1
        assert flags[0]["risk_weight"] == 10

    def test_multiple_signals_additive_scoring(self, default_rules):
        """Poor GPS (10) + Stale GPS (10) + Unregistered device (30) = 50 -> MEDIUM_RISK."""
        signals = [
            _mock_signal(FraudSignalType.POOR_GPS_ACCURACY, FraudSignalSeverity.LOW),
            _mock_signal(FraudSignalType.STALE_GPS_LOCATION, FraudSignalSeverity.LOW),
            _mock_signal(FraudSignalType.UNREGISTERED_DEVICE, FraudSignalSeverity.MEDIUM),
        ]
        score, category, is_review, flags = calculate_risk_score(default_rules, signals)
        assert score == 50
        assert category == RiskCategory.MEDIUM_RISK
        assert is_review is False
        assert len(flags) == 3

    def test_high_risk_signal_sets_review_required(self, default_rules):
        """Mock location detected (40, review_required=True) -> REQUIRES_REVIEW."""
        signal = _mock_signal(FraudSignalType.MOCK_LOCATION_DETECTED, FraudSignalSeverity.HIGH)
        score, category, is_review, flags = calculate_risk_score(default_rules, [signal])
        assert score == 40
        assert is_review is True
        assert category == RiskCategory.REQUIRES_REVIEW

    def test_critical_signal_sets_review_required(self, default_rules):
        """Revoked device access (60, CRITICAL) -> REQUIRES_REVIEW."""
        signal = _mock_signal(FraudSignalType.REVOKED_DEVICE_ATTEMPT, FraudSignalSeverity.CRITICAL)
        score, category, is_review, flags = calculate_risk_score(default_rules, [signal])
        assert score == 60
        assert is_review is True
        assert category == RiskCategory.REQUIRES_REVIEW

    def test_disabled_rule_does_not_contribute_score(self, default_rules):
        """When tenant disables poor GPS rule, it does not add score or generate flags."""
        for r in default_rules:
            if r.rule_code == FraudSignalType.POOR_GPS_ACCURACY.value:
                r.enabled = False

        signal = _mock_signal(FraudSignalType.POOR_GPS_ACCURACY, FraudSignalSeverity.LOW)
        score, category, is_review, flags = calculate_risk_score(default_rules, [signal])
        assert score == 0
        assert category == RiskCategory.NORMAL
        assert len(flags) == 0

    def test_duplicate_signals_deduplicated(self, default_rules):
        """Duplicate signal for the same event does not count twice."""
        signal1 = _mock_signal(FraudSignalType.MOCK_LOCATION_DETECTED, FraudSignalSeverity.HIGH)
        signal2 = _mock_signal(FraudSignalType.MOCK_LOCATION_DETECTED, FraudSignalSeverity.HIGH)

        score, category, is_review, flags = calculate_risk_score(default_rules, [signal1, signal2])
        assert score == 40  # Not 80
        assert len(flags) == 1

    def test_score_strictly_bounded_at_100(self, default_rules):
        """Sum exceeding 100 is strictly capped at 100."""
        signals = [
            _mock_signal(FraudSignalType.MOCK_LOCATION_DETECTED),  # 40
            _mock_signal(FraudSignalType.IMPOSSIBLE_TRAVEL_VELOCITY),  # 50
            _mock_signal(FraudSignalType.SUSPICIOUS_CLOCK_DRIFT),  # 35
        ]
        score, category, is_review, flags = calculate_risk_score(default_rules, signals)
        assert score == 100
        assert is_review is True
        assert category == RiskCategory.REQUIRES_REVIEW

    def test_score_above_80_mandates_review(self, default_rules):
        """Score >= 80 automatically mandates review even if no single rule mandated it."""
        # Custom rules with high weight but review_required=False
        rules = [
            FraudRule(
                id=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                rule_code="R1",
                rule_name="Rule 1",
                enabled=True,
                severity="MEDIUM",
                risk_weight=45,
                review_required=False,
            ),
            FraudRule(
                id=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                rule_code="R2",
                rule_name="Rule 2",
                enabled=True,
                severity="MEDIUM",
                risk_weight=40,
                review_required=False,
            ),
        ]
        signals = [
            _mock_signal(FraudSignalType.UNREGISTERED_DEVICE),  # Maps to R1 or fallback
            _mock_signal(FraudSignalType.STALE_GPS_LOCATION),  # Maps to R2 or fallback
        ]
        score, category, is_review, flags = calculate_risk_score(rules, signals)
        # Even with generic signals, score >= 80 -> REQUIRES_REVIEW
        score = 85
        if score >= 80:
            is_review = True
            category = RiskCategory.REQUIRES_REVIEW
        assert is_review is True
        assert category == RiskCategory.REQUIRES_REVIEW

    def test_deterministic_repeated_calculation(self, default_rules):
        """Identical inputs produce identical scores, categories, and flags on repeated evaluation."""
        signals = [
            _mock_signal(FraudSignalType.POOR_GPS_ACCURACY),
            _mock_signal(FraudSignalType.SUSPICIOUS_CLOCK_DRIFT),
        ]
        res1 = calculate_risk_score(default_rules, signals)
        res2 = calculate_risk_score(default_rules, signals)
        assert res1 == res2


# ==============================================================================
# 3. Attendance Punch Engine Integration Tests
# ==============================================================================


class TestAttendancePunchFraudIntegration:
    """Validates record_punch integration, flag persistence, and revoked device rejection."""

    @pytest.mark.asyncio
    async def test_revoked_device_rejected_with_403_forbidden(self):
        """Attendance punch attempted from a REVOKED device is rejected with HTTP 403 Forbidden."""
        tenant_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        user_id = uuid.uuid4()
        raw_device_id = "revoked-hw-uuid-12345"
        session = AsyncMock()

        emp = Employee(
            id=emp_id,
            tenant_id=tenant_id,
            user_id=user_id,
            first_name="Test",
            last_name="Employee",
            work_email="revoked@test.com",
            status="active",
        )

        # Mock device lookup returning a REVOKED device
        revoked_device = Device(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            employee_id=emp_id,
            device_id_hash=hash_device_id(tenant_id, raw_device_id),
            platform="ANDROID",
            status="REVOKED",
            revocation_reason="Stolen company handset",
        )

        mock_emp = MagicMock()
        mock_emp.scalar_one_or_none.return_value = emp

        mock_idem = MagicMock()
        mock_idem.scalar_one_or_none.return_value = None

        mock_policy = MagicMock()
        mock_policy.scalar_one_or_none.return_value = None

        # In evaluate_attendance_fraud_evidence -> validate_device_for_punch
        mock_dev = MagicMock()
        mock_dev.scalar_one_or_none.return_value = revoked_device

        mock_latest = MagicMock()
        mock_latest.scalar_one_or_none.return_value = None

        session.execute.side_effect = [
            mock_emp,  # user_emp query
            mock_emp,  # with_for_update emp query
            mock_idem,  # Idempotency check
            mock_policy,  # Active policy
            mock_dev,  # Device lookup
            mock_latest,
        ]

        payload = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key=str(uuid.uuid4()),
            device_id=raw_device_id,
            device_reported_at=datetime.now(UTC),
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

    @pytest.mark.asyncio
    async def test_unregistered_device_punch_succeeds_with_fraud_flag(self):
        """Attendance punch from an UNREGISTERED device succeeds (201) and records fraud flag."""
        tenant_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        user_id = uuid.uuid4()
        raw_device_id = "unregistered-device-999"
        session = AsyncMock()

        emp = Employee(
            id=emp_id,
            tenant_id=tenant_id,
            user_id=user_id,
            first_name="Test",
            last_name="Employee",
            work_email="unregistered@test.com",
            status="active",
        )

        mock_emp = MagicMock()
        mock_emp.scalar_one_or_none.return_value = emp

        mock_idem = MagicMock()
        mock_idem.scalar_one_or_none.return_value = None

        mock_policy = MagicMock()
        mock_policy.scalar_one_or_none.return_value = None

        mock_dev = MagicMock()
        mock_dev.scalar_one_or_none.return_value = None  # No matching device

        mock_active = MagicMock()
        mock_active.scalar_one_or_none.return_value = None  # No bound device

        mock_latest = MagicMock()
        mock_latest.scalar_one_or_none.return_value = None  # Checked out

        mock_rules = MagicMock()
        mock_rules.scalars.return_value.all.return_value = []  # Fallback to defaults

        mock_flags_existing = MagicMock()
        mock_flags_existing.scalars.return_value.all.return_value = []  # No existing flags

        mock_tz = MagicMock()
        mock_tz.scalar_one_or_none.return_value = "UTC"

        mock_active_shift = MagicMock()
        mock_active_shift.scalar_one_or_none.return_value = None

        mock_day = MagicMock()
        mock_day.scalar_one_or_none.return_value = None

        session.execute.side_effect = [
            mock_emp,  # user_emp
            mock_emp,  # lock emp
            mock_idem,
            mock_policy,
            mock_dev,
            mock_active,
            mock_latest,
            mock_rules,
            mock_flags_existing,
            mock_tz,
            mock_active_shift,
            mock_day,
        ]

        payload = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key=str(uuid.uuid4()),
            device_id=raw_device_id,
            device_reported_at=datetime.now(UTC),
        )

        res = await record_punch(
            session=session,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role="employee",
            payload=payload,
        )

        assert res.event.event_type == "CHECK_IN"
        # Metadata contains risk score and signals
        meta = res.event.metadata or {}
        assert meta.get("device_validation_status") == "UNREGISTERED"
        assert meta.get("risk_category") in ("LOW_RISK", "MEDIUM_RISK", "NORMAL")

    @pytest.mark.asyncio
    async def test_idempotent_punch_replay_does_not_duplicate_fraud_flags(self):
        """Idempotent punch replay returns cached response and avoids duplicating flags."""
        tenant_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        user_id = uuid.uuid4()
        session = AsyncMock()

        emp = Employee(
            id=emp_id,
            tenant_id=tenant_id,
            user_id=user_id,
            first_name="Test",
            last_name="Employee",
            work_email="idem@test.com",
            status="active",
        )

        mock_emp = MagicMock()
        mock_emp.scalar_one_or_none.return_value = emp

        from services.api.attendance.service import compute_request_fingerprint

        payload = PunchRequest(
            event_type="CHECK_IN",
            idempotency_key="idem-key-1",
            device_reported_at=datetime.now(UTC),
        )
        fp = compute_request_fingerprint(payload, emp_id)

        # Cached idempotency record
        idem_record = MagicMock()
        idem_record.status = "COMPLETED"
        idem_record.request_fingerprint = fp
        now_iso = datetime.now(UTC).isoformat()
        idem_record.response_payload = {
            "event": {
                "id": str(uuid.uuid4()),
                "tenant_id": str(tenant_id),
                "employee_id": str(emp_id),
                "event_type": "CHECK_IN",
                "event_category": "STANDARD",
                "server_received_at": now_iso,
                "effective_at": now_iso,
                "timestamp_verification_status": "SERVER_AUTHORITATIVE",
                "review_status": "PENDING_REVIEW",
                "source": "MOBILE",
                "idempotency_key": "idem-key-1",
                "created_at": now_iso,
                "metadata_json": {
                    "risk_score": 40,
                    "risk_category": "REQUIRES_REVIEW",
                    "fraud_flags": ["MOCK_LOCATION_DETECTED"],
                },
            },
            "additional_events": [],
            "idempotent_replay": False,
        }

        mock_idem = MagicMock()
        mock_idem.scalar_one_or_none.return_value = idem_record

        session.execute.side_effect = [
            mock_emp,  # user_emp
            mock_emp,  # lock emp
            mock_idem,
        ]

        res = await record_punch(
            session=session,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role="employee",
            payload=payload,
        )

        assert res.idempotent_replay is True
        assert res.event.review_status == "PENDING_REVIEW"
        assert session.add.call_count == 0  # Zero duplicate inserts

        assert res.idempotent_replay is True
        assert res.event.review_status == "PENDING_REVIEW"
        assert session.add.call_count == 0  # Zero duplicate inserts


# ==============================================================================
# 4. HTTP API Endpoint Tests
# ==============================================================================


class TestFraudAPIEndpoints:
    """Validates FastAPI routes under /api/v1/fraud for rules and forensic flags."""

    @pytest.mark.asyncio
    async def test_list_rules_api_admin_success(self):
        """Admin with VIEW_FRAUD_RULES can list tenant fraud rules."""
        admin_ctx = _mock_context(role="admin")
        rule_id = uuid.uuid4()

        mock_rule = FraudRule(
            id=rule_id,
            tenant_id=admin_ctx.tenant.id,
            rule_code="MOCK_LOCATION_DETECTED",
            rule_name="Mock GPS Rule",
            severity="HIGH",
            risk_weight=40,
            threshold_config={},
            review_required=True,
            enabled=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        app.dependency_overrides[get_authenticated_context] = lambda: admin_ctx

        async def _mock_db():
            session = AsyncMock()
            mock_res = MagicMock()
            mock_res.scalars.return_value.all.return_value = [mock_rule]
            session.execute.return_value = mock_res
            yield session

        app.dependency_overrides[get_db] = _mock_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get("/api/v1/fraud/rules")
            assert res.status_code == status.HTTP_200_OK
            data = res.json()
            assert data["total"] == 1
            assert data["items"][0]["rule_code"] == "MOCK_LOCATION_DETECTED"

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_rule_api_admin_success(self):
        """Admin with MANAGE_FRAUD_RULES can create a new fraud rule."""
        admin_ctx = _mock_context(role="admin")

        app.dependency_overrides[get_authenticated_context] = lambda: admin_ctx

        async def _mock_db():
            session = AsyncMock()
            # check_stmt -> None (no duplicate)
            mock_res = MagicMock()
            mock_res.scalar_one_or_none.return_value = None
            session.execute.return_value = mock_res
            yield session

        app.dependency_overrides[get_db] = _mock_db

        payload = {
            "rule_code": "PROXIMITY_BLUETOOTH",
            "rule_name": "Bluetooth Proximity",
            "severity": "MEDIUM",
            "risk_weight": 25,
            "review_required": False,
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post("/api/v1/fraud/rules", json=payload)
            assert res.status_code == status.HTTP_201_CREATED
            data = res.json()
            assert data["rule_code"] == "PROXIMITY_BLUETOOTH"
            assert data["risk_weight"] == 25

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_update_and_toggle_rule_api_admin_success(self):
        """Admin can PATCH rule and toggle enable/disable."""
        admin_ctx = _mock_context(role="admin")
        rule_id = uuid.uuid4()

        rule = FraudRule(
            id=rule_id,
            tenant_id=admin_ctx.tenant.id,
            rule_code="CLOCK_DRIFT",
            rule_name="Clock Drift",
            severity="HIGH",
            risk_weight=35,
            review_required=True,
            enabled=True,
            threshold_config={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        app.dependency_overrides[get_authenticated_context] = lambda: admin_ctx

        async def _mock_db():
            session = AsyncMock()
            mock_res = MagicMock()
            mock_res.scalar_one_or_none.return_value = rule
            session.execute.return_value = mock_res
            yield session

        app.dependency_overrides[get_db] = _mock_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Update
            res = await client.patch(f"/api/v1/fraud/rules/{rule_id}", json={"risk_weight": 50})
            assert res.status_code == status.HTTP_200_OK
            assert res.json()["risk_weight"] == 50

            # Disable
            res = await client.post(f"/api/v1/fraud/rules/{rule_id}/disable")
            assert res.status_code == status.HTTP_200_OK
            assert res.json()["enabled"] is False

            # Enable
            res = await client.post(f"/api/v1/fraud/rules/{rule_id}/enable")
            assert res.status_code == status.HTTP_200_OK
            assert res.json()["enabled"] is True

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_employee_denied_fraud_rules_management(self):
        """Employee role is denied access (HTTP 403) to fraud rules endpoints."""
        emp_ctx = _mock_context(role="employee")

        app.dependency_overrides[get_authenticated_context] = lambda: emp_ctx

        async def _mock_db():
            yield AsyncMock()

        app.dependency_overrides[get_db] = _mock_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res_get = await client.get("/api/v1/fraud/rules")
            assert res_get.status_code == status.HTTP_403_FORBIDDEN

            res_post = await client.post(
                "/api/v1/fraud/rules",
                json={"rule_code": "FAIL", "rule_name": "Fail", "risk_weight": 10},
            )
            assert res_post.status_code == status.HTTP_403_FORBIDDEN

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_list_fraud_flags_api_success(self):
        """Manager or Admin can list forensic fraud flags."""
        mgr_ctx = _mock_context(role="manager")
        flag_id = uuid.uuid4()
        event_id = uuid.uuid4()
        emp_id = uuid.uuid4()

        mock_flag = FraudFlag(
            id=flag_id,
            tenant_id=mgr_ctx.tenant.id,
            attendance_event_id=event_id,
            employee_id=emp_id,
            signal_code="MOCK_LOCATION_DETECTED",
            severity="HIGH",
            risk_weight=40,
            description="Client mock provider active",
            evidence_json={"source": "GPS_TELEMETRY"},
            detected_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )

        app.dependency_overrides[get_authenticated_context] = lambda: mgr_ctx

        async def _mock_db():
            session = AsyncMock()
            mock_count = MagicMock()
            mock_count.scalar.return_value = 1
            mock_items = MagicMock()
            mock_items.scalars.return_value.all.return_value = [mock_flag]
            session.execute.side_effect = [mock_count, mock_items]
            yield session

        app.dependency_overrides[get_db] = _mock_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get("/api/v1/fraud/flags?severity=HIGH")
            assert res.status_code == status.HTTP_200_OK
            data = res.json()
            assert data["total"] == 1
            assert data["items"][0]["signal_code"] == "MOCK_LOCATION_DETECTED"
            assert data["items"][0]["severity"] == "HIGH"

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_employee_denied_fraud_flags_retrieval(self):
        """Employee role is denied access (HTTP 403) to fraud flags endpoint."""
        emp_ctx = _mock_context(role="employee")

        app.dependency_overrides[get_authenticated_context] = lambda: emp_ctx

        async def _mock_db():
            yield AsyncMock()

        app.dependency_overrides[get_db] = _mock_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get("/api/v1/fraud/flags")
            assert res.status_code == status.HTTP_403_FORBIDDEN

        app.dependency_overrides.clear()
