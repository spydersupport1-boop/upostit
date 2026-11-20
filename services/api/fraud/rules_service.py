"""Business logic service for tenant fraud rules management and flag retrieval."""

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.attendance.models import AttendanceEvent
from services.api.employees.models import Employee
from services.api.fraud.engine import seed_default_fraud_rules
from services.api.fraud.models import FraudFlag, FraudRule
from services.api.fraud.schemas import (
    FraudRuleCreateRequest,
    FraudRuleUpdateRequest,
)


async def list_fraud_rules(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    enabled_filter: bool | None = None,
) -> tuple[list[FraudRule], int]:
    """Lists fraud rules configured for a tenant, seeding defaults if empty."""
    stmt = select(FraudRule).where(FraudRule.tenant_id == tenant_id)
    if enabled_filter is not None:
        stmt = stmt.where(FraudRule.enabled == enabled_filter)
    stmt = stmt.order_by(FraudRule.created_at.asc())

    res = await session.execute(stmt)
    rules = list(res.scalars().all())

    # Seed defaults if tenant has no rules configured yet
    if not rules and enabled_filter is None:
        rules = await seed_default_fraud_rules(session, tenant_id)

    return rules, len(rules)


async def get_fraud_rule_by_id(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    rule_id: uuid.UUID,
) -> FraudRule:
    """Retrieves a single fraud rule scoped strictly by tenant."""
    stmt = select(FraudRule).where(
        FraudRule.tenant_id == tenant_id,
        FraudRule.id == rule_id,
    )
    rule = (await session.execute(stmt)).scalar_one_or_none()
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fraud rule not found.",
        )
    return rule


async def create_fraud_rule(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    payload: FraudRuleCreateRequest,
    actor_user_id: uuid.UUID | None = None,
) -> FraudRule:
    """Creates a custom or override fraud rule for a tenant."""
    # Enforce unique rule_code per tenant
    check_stmt = select(FraudRule.id).where(
        FraudRule.tenant_id == tenant_id,
        FraudRule.rule_code == payload.rule_code.strip(),
    )
    existing_id = (await session.execute(check_stmt)).scalar_one_or_none()
    if existing_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Fraud rule with code '{payload.rule_code.strip()}' already exists for this tenant.",
        )

    now = datetime.now(UTC)
    new_rule = FraudRule(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        rule_code=payload.rule_code.strip(),
        rule_name=payload.rule_name.strip(),
        description=payload.description,
        enabled=payload.enabled,
        severity=payload.severity.value,
        risk_weight=payload.risk_weight,
        threshold_config=payload.threshold_config,
        review_required=payload.review_required,
        created_at=now,
        updated_at=now,
        created_by=actor_user_id,
        updated_by=actor_user_id,
    )
    session.add(new_rule)
    await session.flush()
    return new_rule


async def update_fraud_rule(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    rule_id: uuid.UUID,
    payload: FraudRuleUpdateRequest,
    actor_user_id: uuid.UUID | None = None,
) -> FraudRule:
    """Updates an existing tenant fraud rule with audit tracking."""
    rule = await get_fraud_rule_by_id(session, tenant_id, rule_id)

    if payload.rule_name is not None:
        rule.rule_name = payload.rule_name.strip()
    if payload.description is not None:
        rule.description = payload.description
    if payload.enabled is not None:
        rule.enabled = payload.enabled
    if payload.severity is not None:
        rule.severity = payload.severity.value
    if payload.risk_weight is not None:
        rule.risk_weight = payload.risk_weight
    if payload.threshold_config is not None:
        rule.threshold_config = payload.threshold_config
    if payload.review_required is not None:
        rule.review_required = payload.review_required

    rule.updated_at = datetime.now(UTC)
    rule.updated_by = actor_user_id

    await session.flush()
    return rule


async def set_fraud_rule_status(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    rule_id: uuid.UUID,
    enabled: bool,
    actor_user_id: uuid.UUID | None = None,
) -> FraudRule:
    """Enables or disables a fraud rule for the tenant."""
    rule = await get_fraud_rule_by_id(session, tenant_id, rule_id)
    rule.enabled = enabled
    rule.updated_at = datetime.now(UTC)
    rule.updated_by = actor_user_id
    await session.flush()
    return rule


async def list_fraud_flags(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID | None = None,
    attendance_event_id: uuid.UUID | None = None,
    severity: str | None = None,
    signal_code: str | None = None,
    review_status: str | None = None,
    risk_category: str | None = None,
    min_risk_score: int | None = None,
    max_risk_score: int | None = None,
    department_id: uuid.UUID | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[FraudFlag], int]:
    """Retrieves immutable forensic fraud flags with tenant isolation and filtering."""
    stmt = select(FraudFlag).where(FraudFlag.tenant_id == tenant_id)

    if employee_id is not None:
        stmt = stmt.where(FraudFlag.employee_id == employee_id)
    if attendance_event_id is not None:
        stmt = stmt.where(FraudFlag.attendance_event_id == attendance_event_id)
    if severity is not None:
        stmt = stmt.where(FraudFlag.severity == severity.upper())
    if signal_code is not None:
        stmt = stmt.where(FraudFlag.signal_code == signal_code.strip())

    if (
        review_status is not None
        or risk_category is not None
        or min_risk_score is not None
        or max_risk_score is not None
    ):
        stmt = stmt.join(
            AttendanceEvent,
            (AttendanceEvent.tenant_id == FraudFlag.tenant_id)
            & (AttendanceEvent.id == FraudFlag.attendance_event_id),
        )
        if review_status is not None:
            stmt = stmt.where(AttendanceEvent.review_status == review_status.upper())
        if risk_category is not None:
            stmt = stmt.where(
                AttendanceEvent.metadata_json["risk_category"].as_string() == risk_category.upper()  # type: ignore[attr-defined]
            )
        if min_risk_score is not None:
            stmt = stmt.where(
                func.cast(AttendanceEvent.metadata_json["risk_score"].astext, sa.Integer) >= min_risk_score  # type: ignore[attr-defined]
            )
        if max_risk_score is not None:
            stmt = stmt.where(
                func.cast(AttendanceEvent.metadata_json["risk_score"].astext, sa.Integer) <= max_risk_score  # type: ignore[attr-defined]
            )

    if department_id is not None:
        stmt = stmt.join(
            Employee,
            (Employee.tenant_id == FraudFlag.tenant_id)
            & (Employee.id == FraudFlag.employee_id),
        ).where(Employee.department_id == department_id)

    if start_date is not None:
        t_start = start_date if start_date.tzinfo else start_date.replace(tzinfo=UTC)
        stmt = stmt.where(FraudFlag.detected_at >= t_start)
    if end_date is not None:
        t_end = end_date if end_date.tzinfo else end_date.replace(tzinfo=UTC)
        stmt = stmt.where(FraudFlag.detected_at <= t_end)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(FraudFlag.detected_at.desc(), FraudFlag.created_at.desc())
    stmt = stmt.limit(limit).offset(offset)

    flags = list((await session.execute(stmt)).scalars().all())
    return flags, total
