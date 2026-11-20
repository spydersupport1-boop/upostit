"""FastAPI router for tenant fraud rules and audit flags under /api/v1/fraud."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.auth.dependencies import (
    AuthenticatedContext,
    get_authenticated_context,
    require_permission,
)
from services.api.auth.permissions import Permission
from services.api.database import get_db
from services.api.fraud.review_service import (
    adjudicate_fraud_event,
    get_fraud_event_review_detail,
)
from services.api.fraud.rules_service import (
    create_fraud_rule,
    get_fraud_rule_by_id,
    list_fraud_flags,
    list_fraud_rules,
    set_fraud_rule_status,
    update_fraud_rule,
)
from services.api.fraud.schemas import (
    FraudEventReviewDetailResponse,
    FraudFlagListResponse,
    FraudFlagResponse,
    FraudReviewDecisionRequest,
    FraudReviewDecisionResponse,
    FraudRuleCreateRequest,
    FraudRuleListResponse,
    FraudRuleResponse,
    FraudRuleUpdateRequest,
)

router = APIRouter(prefix="/fraud", tags=["Fraud Defense"])


@router.get(
    "/rules",
    response_model=FraudRuleListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Tenant Fraud Rules",
    description="Retrieves all configured fraud rules for the tenant. Requires VIEW_FRAUD_RULES permission.",
    dependencies=[Depends(require_permission(Permission.VIEW_FRAUD_RULES))],
)
async def list_fraud_rules_endpoint(
    ctx: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    enabled: bool | None = Query(default=None, description="Filter rules by enabled status."),
) -> FraudRuleListResponse:
    """Lists fraud rules configured for the tenant."""
    rules, total = await list_fraud_rules(
        session=db,
        tenant_id=ctx.tenant.id,
        enabled_filter=enabled,
    )
    return FraudRuleListResponse(
        items=[FraudRuleResponse.model_validate(r) for r in rules],
        total=total,
    )


@router.get(
    "/rules/{rule_id}",
    response_model=FraudRuleResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Fraud Rule Details",
    description="Retrieves a single tenant fraud rule by ID. Requires VIEW_FRAUD_RULES permission.",
    dependencies=[Depends(require_permission(Permission.VIEW_FRAUD_RULES))],
)
async def get_fraud_rule_endpoint(
    rule_id: uuid.UUID,
    ctx: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FraudRuleResponse:
    """Gets a specific fraud rule by ID."""
    rule = await get_fraud_rule_by_id(
        session=db,
        tenant_id=ctx.tenant.id,
        rule_id=rule_id,
    )
    return FraudRuleResponse.model_validate(rule)


@router.post(
    "/rules",
    response_model=FraudRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Tenant Fraud Rule",
    description="Registers a new custom or override fraud rule for the tenant. Requires MANAGE_FRAUD_RULES permission.",
    dependencies=[Depends(require_permission(Permission.MANAGE_FRAUD_RULES))],
)
async def create_fraud_rule_endpoint(
    payload: FraudRuleCreateRequest,
    ctx: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FraudRuleResponse:
    """Registers a new tenant fraud rule."""
    rule = await create_fraud_rule(
        session=db,
        tenant_id=ctx.tenant.id,
        payload=payload,
        actor_user_id=ctx.user.id,
    )
    return FraudRuleResponse.model_validate(rule)


@router.patch(
    "/rules/{rule_id}",
    response_model=FraudRuleResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Tenant Fraud Rule",
    description="Updates severity, risk weight, thresholds, or review requirement for a rule. Requires MANAGE_FRAUD_RULES permission.",
    dependencies=[Depends(require_permission(Permission.MANAGE_FRAUD_RULES))],
)
async def update_fraud_rule_endpoint(
    rule_id: uuid.UUID,
    payload: FraudRuleUpdateRequest,
    ctx: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FraudRuleResponse:
    """Updates an existing tenant fraud rule."""
    rule = await update_fraud_rule(
        session=db,
        tenant_id=ctx.tenant.id,
        rule_id=rule_id,
        payload=payload,
        actor_user_id=ctx.user.id,
    )
    return FraudRuleResponse.model_validate(rule)


@router.post(
    "/rules/{rule_id}/enable",
    response_model=FraudRuleResponse,
    status_code=status.HTTP_200_OK,
    summary="Enable Tenant Fraud Rule",
    description="Enables a previously disabled fraud rule. Requires MANAGE_FRAUD_RULES permission.",
    dependencies=[Depends(require_permission(Permission.MANAGE_FRAUD_RULES))],
)
async def enable_fraud_rule_endpoint(
    rule_id: uuid.UUID,
    ctx: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FraudRuleResponse:
    """Enables a tenant fraud rule."""
    rule = await set_fraud_rule_status(
        session=db,
        tenant_id=ctx.tenant.id,
        rule_id=rule_id,
        enabled=True,
        actor_user_id=ctx.user.id,
    )
    return FraudRuleResponse.model_validate(rule)


@router.post(
    "/rules/{rule_id}/disable",
    response_model=FraudRuleResponse,
    status_code=status.HTTP_200_OK,
    summary="Disable Tenant Fraud Rule",
    description="Disables a fraud rule so it no longer contributes to risk scores. Requires MANAGE_FRAUD_RULES permission.",
    dependencies=[Depends(require_permission(Permission.MANAGE_FRAUD_RULES))],
)
async def disable_fraud_rule_endpoint(
    rule_id: uuid.UUID,
    ctx: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FraudRuleResponse:
    """Disables a tenant fraud rule."""
    rule = await set_fraud_rule_status(
        session=db,
        tenant_id=ctx.tenant.id,
        rule_id=rule_id,
        enabled=False,
        actor_user_id=ctx.user.id,
    )
    return FraudRuleResponse.model_validate(rule)


@router.get(
    "/flags",
    response_model=FraudFlagListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Forensic Fraud Flags",
    description="Lists immutable forensic fraud flags matching filters. Requires VIEW_FRAUD_FLAGS permission.",
    dependencies=[Depends(require_permission(Permission.VIEW_FRAUD_FLAGS))],
)
async def list_fraud_flags_endpoint(
    ctx: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    employee_id: uuid.UUID | None = Query(default=None, description="Filter by employee ID."),
    attendance_event_id: uuid.UUID | None = Query(default=None, description="Filter by attendance event ID."),
    severity: str | None = Query(default=None, description="Filter by severity (LOW, MEDIUM, HIGH, CRITICAL)."),
    signal_code: str | None = Query(default=None, description="Filter by signal code."),
    review_status: str | None = Query(default=None, description="Filter by review status (e.g. PENDING_REVIEW, APPROVED, REJECTED)."),
    risk_category: str | None = Query(default=None, description="Filter by risk category (e.g. HIGH_RISK, REQUIRES_REVIEW)."),
    min_risk_score: int | None = Query(default=None, ge=0, le=100, description="Filter flags where event risk score >= min_risk_score."),
    max_risk_score: int | None = Query(default=None, ge=0, le=100, description="Filter flags where event risk score <= max_risk_score."),
    department_id: uuid.UUID | None = Query(default=None, description="Filter by employee department ID."),
    start_date: datetime | None = Query(default=None, description="Filter flags detected after this UTC timestamp."),
    end_date: datetime | None = Query(default=None, description="Filter flags detected before this UTC timestamp."),
    limit: int = Query(default=50, ge=1, le=100, description="Items per page."),
    offset: int = Query(default=0, ge=0, description="Page offset."),
) -> FraudFlagListResponse:
    """Lists forensic fraud flags with tenant isolation and filtering."""
    flags, total = await list_fraud_flags(
        session=db,
        tenant_id=ctx.tenant.id,
        employee_id=employee_id,
        attendance_event_id=attendance_event_id,
        severity=severity,
        signal_code=signal_code,
        review_status=review_status,
        risk_category=risk_category,
        min_risk_score=min_risk_score,
        max_risk_score=max_risk_score,
        department_id=department_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
    return FraudFlagListResponse(
        items=[FraudFlagResponse.model_validate(f) for f in flags],
        total=total,
    )


@router.get(
    "/events/{event_id}/review",
    response_model=FraudEventReviewDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Attendance Fraud Review Detail",
    description="Retrieves comprehensive forensic detail for an attendance event pending review. Requires VIEW_FRAUD_REVIEWS permission.",
    dependencies=[Depends(require_permission(Permission.VIEW_FRAUD_REVIEWS))],
)
async def get_fraud_event_review_detail_endpoint(
    event_id: uuid.UUID,
    ctx: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FraudEventReviewDetailResponse:
    """Returns forensic detail, employee info, telemetry, signals, and audit review history."""
    return await get_fraud_event_review_detail(
        session=db,
        tenant_id=ctx.tenant.id,
        event_id=event_id,
        reviewer_user=ctx.user,
        reviewer_role=ctx.user.role,
    )


@router.post(
    "/events/{event_id}/decision",
    response_model=FraudReviewDecisionResponse,
    status_code=status.HTTP_200_OK,
    summary="Adjudicate Attendance Fraud Review",
    description="Approves or rejects a flagged attendance event with mandatory reason. Requires REVIEW_FRAUD_EVENTS permission.",
    dependencies=[Depends(require_permission(Permission.REVIEW_FRAUD_EVENTS))],
)
async def adjudicate_fraud_event_endpoint(
    event_id: uuid.UUID,
    payload: FraudReviewDecisionRequest,
    ctx: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FraudReviewDecisionResponse:
    """Performs atomic review decision, logs audit trail, and recalculates attendance day."""
    return await adjudicate_fraud_event(
        session=db,
        tenant_id=ctx.tenant.id,
        event_id=event_id,
        payload=payload,
        reviewer_user=ctx.user,
        reviewer_role=ctx.user.role,
    )


