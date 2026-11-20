"""Centralized tenant-configurable fraud rule engine and deterministic risk scoring."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.fraud.models import FraudFlag, FraudRule
from services.api.fraud.schemas import (
    FraudFlagResponse,
    FraudSignal,
    FraudSignalSeverity,
    FraudSignalType,
    RiskCategory,
    RiskScoreResult,
)

DEFAULT_RULE_DEFINITIONS: list[dict[str, Any]] = [
    {
        "rule_code": FraudSignalType.MOCK_LOCATION_DETECTED.value,
        "rule_name": "Mock Location Detection",
        "description": "Client device reported mock location provider enabled or location spoofing active.",
        "severity": FraudSignalSeverity.HIGH.value,
        "risk_weight": 40,
        "threshold_config": {"allow_mock": False},
        "review_required": True,
    },
    {
        "rule_code": FraudSignalType.SUSPICIOUS_CLOCK_DRIFT.value,
        "rule_name": "Device Clock Skew",
        "description": "Discrepancy between client device timestamp and authoritative server UTC clock.",
        "severity": FraudSignalSeverity.HIGH.value,
        "risk_weight": 35,
        "threshold_config": {"max_drift_seconds": 300.0},
        "review_required": True,
    },
    {
        "rule_code": FraudSignalType.IMPOSSIBLE_TRAVEL_VELOCITY.value,
        "rule_name": "Impossible Travel Velocity",
        "description": "Calculated travel velocity between consecutive punches exceeds plausible physical limits.",
        "severity": FraudSignalSeverity.HIGH.value,
        "risk_weight": 50,
        "threshold_config": {"max_velocity_mps": 250.0},
        "review_required": True,
    },
    {
        "rule_code": FraudSignalType.UNREGISTERED_DEVICE.value,
        "rule_name": "Unregistered Device",
        "description": "Attendance punch attempted from a mobile device not registered to the employee.",
        "severity": FraudSignalSeverity.MEDIUM.value,
        "risk_weight": 30,
        "threshold_config": {},
        "review_required": False,
    },
    {
        "rule_code": FraudSignalType.DEVICE_MISMATCH.value,
        "rule_name": "Device Mismatch",
        "description": "Hardware device signature does not match the active bound device for this employee.",
        "severity": FraudSignalSeverity.HIGH.value,
        "risk_weight": 40,
        "threshold_config": {},
        "review_required": True,
    },
    {
        "rule_code": FraudSignalType.REVOKED_DEVICE.value,
        "rule_name": "Revoked Device Access",
        "description": "Attendance attempted from an explicitly revoked hardware device.",
        "severity": FraudSignalSeverity.CRITICAL.value,
        "risk_weight": 60,
        "threshold_config": {},
        "review_required": True,
    },
    {
        "rule_code": FraudSignalType.POOR_GPS_ACCURACY.value,
        "rule_name": "Poor GPS Accuracy",
        "description": "GPS location horizontal uncertainty radius exceeds allowable threshold.",
        "severity": FraudSignalSeverity.LOW.value,
        "risk_weight": 10,
        "threshold_config": {"max_accuracy_meters": 100.0},
        "review_required": False,
    },
    {
        "rule_code": FraudSignalType.STALE_GPS_LOCATION.value,
        "rule_name": "Stale GPS Fix",
        "description": "Location sensor fix timestamp is older than allowable freshness threshold.",
        "severity": FraudSignalSeverity.LOW.value,
        "risk_weight": 10,
        "threshold_config": {"max_age_seconds": 30.0},
        "review_required": False,
    },
]


def normalize_signal_code(signal_code: str) -> str:
    """Normalizes alias signal codes to canonical rule codes."""
    if signal_code in (
        FraudSignalType.REVOKED_DEVICE_ATTEMPT.value,
        FraudSignalType.REVOKED_DEVICE.value,
    ):
        return FraudSignalType.REVOKED_DEVICE.value
    return signal_code


async def get_tenant_fraud_rules(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    enabled_only: bool = False,
) -> list[FraudRule]:
    """Retrieves fraud rules configured for a specific tenant."""
    stmt = select(FraudRule).where(FraudRule.tenant_id == tenant_id)
    if enabled_only:
        stmt = stmt.where(FraudRule.enabled.is_(True))
    stmt = stmt.order_by(FraudRule.created_at.asc())

    result = await session.execute(stmt)
    rules = list(result.scalars().all())
    return rules


async def seed_default_fraud_rules(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None = None,
) -> list[FraudRule]:
    """Initializes default fraud rules for a tenant if none exist."""
    existing = await get_tenant_fraud_rules(session, tenant_id)
    if existing:
        return existing

    now = datetime.now(UTC)
    created_rules: list[FraudRule] = []
    for defn in DEFAULT_RULE_DEFINITIONS:
        rule = FraudRule(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            rule_code=defn["rule_code"],
            rule_name=defn["rule_name"],
            description=defn["description"],
            enabled=True,
            severity=defn["severity"],
            risk_weight=defn["risk_weight"],
            threshold_config=defn["threshold_config"],
            review_required=defn["review_required"],
            created_at=now,
            updated_at=now,
            created_by=actor_user_id,
            updated_by=actor_user_id,
        )
        session.add(rule)
        created_rules.append(rule)

    await session.flush()
    return created_rules


def calculate_risk_score(
    rules: list[FraudRule],
    signals: list[FraudSignal],
) -> tuple[int, RiskCategory, bool, list[dict[str, Any]]]:
    """Deterministically evaluates fraud signals against configured rules.

    Returns:
        (total_score, risk_category, is_review_required, applied_flag_dicts)
    """
    rule_map: dict[str, FraudRule] = {r.rule_code: r for r in rules}

    # Deduplicate signals by normalized signal code to avoid multi-counting
    seen_codes: set[str] = set()
    unique_signals: list[FraudSignal] = []
    for s in signals:
        norm_code = normalize_signal_code(s.signal_type.value)
        if norm_code not in seen_codes:
            seen_codes.add(norm_code)
            unique_signals.append(s)

    applied_flag_dicts: list[dict[str, Any]] = []
    total_score = 0
    requires_review = False

    for s in unique_signals:
        norm_code = normalize_signal_code(s.signal_type.value)
        matching_rule = rule_map.get(norm_code) or rule_map.get(s.signal_type.value)

        if matching_rule is not None:
            # If tenant explicitly disabled this rule, it contributes 0 score and is not flagged
            if not matching_rule.enabled:
                continue

            rule_id = matching_rule.id
            severity = matching_rule.severity
            weight = matching_rule.risk_weight
            if matching_rule.review_required:
                requires_review = True
            description = matching_rule.description or s.reason
        else:
            # Fallback for system signals not yet customized by tenant
            rule_id = None
            severity = s.severity.value
            weight = 30 if severity in ("HIGH", "CRITICAL") else 10
            if s.severity in (FraudSignalSeverity.HIGH, FraudSignalSeverity.CRITICAL):
                requires_review = True
            description = s.reason

        if severity == FraudSignalSeverity.CRITICAL.value:
            requires_review = True

        total_score += weight

        applied_flag_dicts.append(
            {
                "rule_id": rule_id,
                "signal_code": s.signal_type.value,
                "severity": severity,
                "risk_weight": weight,
                "description": description,
                "evidence_json": {
                    "source": s.source,
                    "details": s.details,
                    "reason": s.reason,
                },
                "detected_at": s.timestamp,
            }
        )

    # Risk score is strictly bounded between 0 and 100
    bounded_score = min(100, max(0, total_score))

    # Review threshold: score >= 80 automatically mandates review
    if bounded_score >= 80:
        requires_review = True

    # Derive RiskCategory
    if requires_review:
        category = RiskCategory.REQUIRES_REVIEW
    elif bounded_score == 0:
        category = RiskCategory.NORMAL
    elif 1 <= bounded_score <= 30:
        category = RiskCategory.LOW_RISK
    elif 31 <= bounded_score <= 60:
        category = RiskCategory.MEDIUM_RISK
    else:  # 61 <= bounded_score <= 79
        category = RiskCategory.HIGH_RISK

    return bounded_score, category, requires_review, applied_flag_dicts


async def persist_fraud_flags(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    attendance_event_id: uuid.UUID,
    employee_id: uuid.UUID,
    device_id: uuid.UUID | None,
    flag_dicts: list[dict[str, Any]],
) -> list[FraudFlag]:
    """Persists immutable fraud flags for an attendance event idempotently."""
    if not flag_dicts:
        return []

    # Check for existing flags on this event to ensure idempotent punch replay
    existing_stmt = select(FraudFlag.signal_code).where(
        FraudFlag.tenant_id == tenant_id,
        FraudFlag.attendance_event_id == attendance_event_id,
    )
    existing_codes = set((await session.execute(existing_stmt)).scalars().all())

    persisted: list[FraudFlag] = []
    now = datetime.now(UTC)

    for fd in flag_dicts:
        if fd["signal_code"] in existing_codes:
            continue

        flag = FraudFlag(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            attendance_event_id=attendance_event_id,
            employee_id=employee_id,
            device_id=device_id,
            rule_id=fd["rule_id"],
            signal_code=fd["signal_code"],
            severity=fd["severity"],
            risk_weight=fd["risk_weight"],
            description=fd["description"],
            evidence_json=fd["evidence_json"],
            detected_at=fd["detected_at"] or now,
            created_at=now,
        )
        session.add(flag)
        persisted.append(flag)

    if persisted:
        await session.flush()

    return persisted


async def evaluate_and_persist_attendance_risk(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    attendance_event_id: uuid.UUID,
    employee_id: uuid.UUID,
    device_id_uuid: uuid.UUID | None,
    signals: list[FraudSignal],
    actor_user_id: uuid.UUID | None = None,
) -> RiskScoreResult:
    """Central entrypoint: loads tenant rules, scores signals, and persists flags."""
    # 1. Load tenant rules
    rules = await get_tenant_fraud_rules(session, tenant_id)
    if not rules:
        # Fall back to standard in-memory default definitions if no custom rules in DB
        rules = [
            FraudRule(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
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

    # 2. Compute deterministic score
    score, category, is_review, flag_dicts = calculate_risk_score(rules, signals)

    # 3. Persist flags idempotently
    persisted_flags = await persist_fraud_flags(
        session=session,
        tenant_id=tenant_id,
        attendance_event_id=attendance_event_id,
        employee_id=employee_id,
        device_id=device_id_uuid,
        flag_dicts=flag_dicts,
    )

    return RiskScoreResult(
        total_score=score,
        risk_category=category,
        is_review_required=is_review,
        applied_flags=[FraudFlagResponse.model_validate(f) for f in persisted_flags],
        triggered_signals_count=len(flag_dicts),
    )
