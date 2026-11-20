"""Service implementing Overtime Rules configuration, calculation, and supervisor adjudication.

All operations enforce tenant isolation, RBAC permissions, and concurrency-safe transactions.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.employees.models import Employee
from services.api.leave.models import OvertimeRecord, OvertimeRule
from services.api.leave.schemas import (
    OvertimeDecisionRequest,
    OvertimeRecordResponse,
    OvertimeRuleCreateRequest,
    OvertimeRuleResponse,
    OvertimeRuleUpdateRequest,
)


def map_overtime_rule_to_response(rule: OvertimeRule) -> OvertimeRuleResponse:
    """Maps SQLAlchemy OvertimeRule to Pydantic response."""
    now = datetime.now(UTC)
    return OvertimeRuleResponse(
        id=rule.id or uuid.uuid4(),
        tenant_id=rule.tenant_id,
        name=rule.name,
        min_overtime_threshold_minutes=rule.min_overtime_threshold_minutes,
        max_daily_overtime_minutes=rule.max_daily_overtime_minutes,
        max_weekly_overtime_minutes=rule.max_weekly_overtime_minutes,
        workday_multiplier=rule.workday_multiplier,
        weekend_multiplier=rule.weekend_multiplier,
        holiday_multiplier=rule.holiday_multiplier,
        requires_manager_approval=rule.requires_manager_approval,
        requires_pre_approval=rule.requires_pre_approval,
        is_default=rule.is_default,
        is_active=rule.is_active,
        created_at=rule.created_at or now,
        updated_at=rule.updated_at or now,
    )


def map_overtime_record_to_response(
    rec: OvertimeRecord,
    emp: Employee | None = None,
) -> OvertimeRecordResponse:
    """Maps SQLAlchemy OvertimeRecord to Pydantic response."""
    now = datetime.now(UTC)
    emp_name = f"{emp.first_name} {emp.last_name}" if emp else None
    return OvertimeRecordResponse(
        id=rec.id or uuid.uuid4(),
        tenant_id=rec.tenant_id,
        employee_id=rec.employee_id,
        employee_name=emp_name,
        attendance_day_id=rec.attendance_day_id,
        attendance_date=rec.attendance_date,
        overtime_rule_id=rec.overtime_rule_id,
        raw_overtime_minutes=rec.raw_overtime_minutes,
        approved_overtime_minutes=rec.approved_overtime_minutes,
        multiplier=rec.multiplier,
        payable_overtime_minutes=rec.payable_overtime_minutes,
        overtime_type=rec.overtime_type,
        status=rec.status,
        reviewer_user_id=rec.reviewer_user_id,
        reviewer_notes=rec.reviewer_notes,
        decided_at=rec.decided_at,
        created_at=rec.created_at or now,
        updated_at=rec.updated_at or now,
    )


# ==============================================================================
# Overtime Rule Management
# ==============================================================================


async def create_overtime_rule(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    payload: OvertimeRuleCreateRequest,
) -> OvertimeRule:
    """Creates a new overtime policy rule for the tenant."""
    if (
        payload.max_daily_overtime_minutes is not None
        and payload.max_daily_overtime_minutes < payload.min_overtime_threshold_minutes
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"max_daily_overtime_minutes ({payload.max_daily_overtime_minutes}) cannot be less than "
                f"min_overtime_threshold_minutes ({payload.min_overtime_threshold_minutes})."
            ),
        )

    if (
        payload.workday_multiplier < Decimal("1.00")
        or payload.weekend_multiplier < Decimal("1.00")
        or payload.holiday_multiplier < Decimal("1.00")
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Overtime multipliers cannot be less than 1.00.",
        )

    # Demote existing default rules if setting is_default=True
    if payload.is_default:
        existing_defaults = (
            (
                await session.execute(
                    select(OvertimeRule).where(
                        OvertimeRule.tenant_id == tenant_id,
                        OvertimeRule.is_default.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        for ed in existing_defaults:
            ed.is_default = False

    now = datetime.now(UTC)
    new_rule = OvertimeRule(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name=payload.name,
        min_overtime_threshold_minutes=payload.min_overtime_threshold_minutes,
        max_daily_overtime_minutes=payload.max_daily_overtime_minutes,
        max_weekly_overtime_minutes=payload.max_weekly_overtime_minutes,
        workday_multiplier=payload.workday_multiplier,
        weekend_multiplier=payload.weekend_multiplier,
        holiday_multiplier=payload.holiday_multiplier,
        requires_manager_approval=payload.requires_manager_approval,
        requires_pre_approval=payload.requires_pre_approval,
        is_default=payload.is_default,
        is_active=payload.is_active,
        created_at=now,
        updated_at=now,
    )
    session.add(new_rule)
    await session.flush()
    return new_rule


async def get_overtime_rule(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    rule_id: uuid.UUID,
) -> OvertimeRule:
    """Retrieves an overtime rule by ID within tenant."""
    stmt = select(OvertimeRule).where(
        OvertimeRule.tenant_id == tenant_id,
        OvertimeRule.id == rule_id,
    )
    rule = (await session.execute(stmt)).scalar_one_or_none()
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Overtime rule '{rule_id}' not found.",
        )
    return rule


async def list_overtime_rules(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    is_active: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[OvertimeRule], int]:
    """Lists paginated overtime rules for tenant."""
    query = select(OvertimeRule).where(OvertimeRule.tenant_id == tenant_id)
    count_query = select(func.count(OvertimeRule.id)).where(OvertimeRule.tenant_id == tenant_id)

    if is_active is not None:
        query = query.where(OvertimeRule.is_active == is_active)
        count_query = count_query.where(OvertimeRule.is_active == is_active)

    total = (await session.execute(count_query)).scalar() or 0
    query = (
        query.order_by(OvertimeRule.is_default.desc(), OvertimeRule.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = list((await session.execute(query)).scalars().all())
    return items, total


async def update_overtime_rule(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    rule_id: uuid.UUID,
    payload: OvertimeRuleUpdateRequest,
) -> OvertimeRule:
    """Updates an existing overtime rule."""
    rule = await get_overtime_rule(session, tenant_id, rule_id)

    min_thresh = (
        payload.min_overtime_threshold_minutes
        if payload.min_overtime_threshold_minutes is not None
        else rule.min_overtime_threshold_minutes
    )
    max_daily = (
        payload.max_daily_overtime_minutes
        if payload.max_daily_overtime_minutes is not None
        else rule.max_daily_overtime_minutes
    )

    if max_daily is not None and max_daily < min_thresh:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"max_daily_overtime_minutes ({max_daily}) cannot be less than min_overtime_threshold_minutes ({min_thresh}).",
        )

    for field, val in (
        ("workday_multiplier", payload.workday_multiplier),
        ("weekend_multiplier", payload.weekend_multiplier),
        ("holiday_multiplier", payload.holiday_multiplier),
    ):
        if val is not None and val < Decimal("1.00"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{field} cannot be less than 1.00.",
            )

    if payload.is_default:
        existing_defaults = (
            (
                await session.execute(
                    select(OvertimeRule).where(
                        OvertimeRule.tenant_id == tenant_id,
                        OvertimeRule.id != rule.id,
                        OvertimeRule.is_default.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        for ed in existing_defaults:
            ed.is_default = False

    if payload.name is not None:
        rule.name = payload.name
    if payload.min_overtime_threshold_minutes is not None:
        rule.min_overtime_threshold_minutes = payload.min_overtime_threshold_minutes
    if payload.max_daily_overtime_minutes is not None:
        rule.max_daily_overtime_minutes = payload.max_daily_overtime_minutes
    if payload.max_weekly_overtime_minutes is not None:
        rule.max_weekly_overtime_minutes = payload.max_weekly_overtime_minutes
    if payload.workday_multiplier is not None:
        rule.workday_multiplier = payload.workday_multiplier
    if payload.weekend_multiplier is not None:
        rule.weekend_multiplier = payload.weekend_multiplier
    if payload.holiday_multiplier is not None:
        rule.holiday_multiplier = payload.holiday_multiplier
    if payload.requires_manager_approval is not None:
        rule.requires_manager_approval = payload.requires_manager_approval
    if payload.requires_pre_approval is not None:
        rule.requires_pre_approval = payload.requires_pre_approval
    if payload.is_default is not None:
        rule.is_default = payload.is_default
    if payload.is_active is not None:
        rule.is_active = payload.is_active

    rule.updated_at = datetime.now(UTC)
    await session.flush()
    return rule


async def delete_overtime_rule(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    rule_id: uuid.UUID,
) -> None:
    """Deletes an overtime rule if unreferenced by overtime records."""
    rule = await get_overtime_rule(session, tenant_id, rule_id)
    ref_check = await session.execute(
        select(OvertimeRecord.id)
        .where(
            OvertimeRecord.tenant_id == tenant_id,
            OvertimeRecord.overtime_rule_id == rule.id,
        )
        .limit(1)
    )
    if ref_check.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot delete overtime rule '{rule.name}' because overtime records reference it. Deactivate the rule instead.",
        )
    await session.delete(rule)
    await session.flush()


async def resolve_applicable_overtime_rule(
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> OvertimeRule | None:
    """Resolves the active default overtime rule for the tenant."""
    # 1. Query default active rule
    default_stmt = select(OvertimeRule).where(
        OvertimeRule.tenant_id == tenant_id,
        OvertimeRule.is_default.is_(True),
        OvertimeRule.is_active.is_(True),
    )
    default_rule = (await session.execute(default_stmt)).scalar_one_or_none()
    if default_rule:
        return default_rule

    # 2. Fallback to any active rule
    fallback_stmt = (
        select(OvertimeRule)
        .where(
            OvertimeRule.tenant_id == tenant_id,
            OvertimeRule.is_active.is_(True),
        )
        .order_by(OvertimeRule.created_at.asc())
        .limit(1)
    )
    return (await session.execute(fallback_stmt)).scalar_one_or_none()


# ==============================================================================
# Overtime Records & Adjudication
# ==============================================================================


async def list_overtime_records(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    user_role: str,
    employee_id: uuid.UUID | None = None,
    status_filter: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    overtime_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[tuple[OvertimeRecord, Employee]], int]:
    """Queries paginated overtime records respecting RBAC and reporting hierarchy scoping."""
    role_lower = user_role.lower()

    query = (
        select(OvertimeRecord, Employee)
        .join(Employee, OvertimeRecord.employee_id == Employee.id)
        .where(OvertimeRecord.tenant_id == tenant_id)
    )
    count_query = (
        select(func.count(OvertimeRecord.id))
        .join(Employee, OvertimeRecord.employee_id == Employee.id)
        .where(OvertimeRecord.tenant_id == tenant_id)
    )

    if role_lower == "employee":
        user_emp = (
            await session.execute(
                select(Employee).where(
                    Employee.tenant_id == tenant_id,
                    Employee.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if not user_emp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Employee profile not found.",
            )
        if employee_id is not None and employee_id != user_emp.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Employees may only query their own overtime records.",
            )
        query = query.where(OvertimeRecord.employee_id == user_emp.id)
        count_query = count_query.where(OvertimeRecord.employee_id == user_emp.id)

    elif role_lower == "manager":
        mgr_emp = (
            await session.execute(
                select(Employee).where(
                    Employee.tenant_id == tenant_id,
                    Employee.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if not mgr_emp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Manager employee profile not found.",
            )
        # Managers can review only direct reports (excluding their own records)
        query = query.where(
            Employee.reporting_manager_id == mgr_emp.id,
            OvertimeRecord.employee_id != mgr_emp.id,
        )
        count_query = count_query.where(
            Employee.reporting_manager_id == mgr_emp.id,
            OvertimeRecord.employee_id != mgr_emp.id,
        )
        if employee_id is not None:
            query = query.where(OvertimeRecord.employee_id == employee_id)
            count_query = count_query.where(OvertimeRecord.employee_id == employee_id)

    else:
        # HR / Admin / Owner: tenant-wide
        if employee_id is not None:
            query = query.where(OvertimeRecord.employee_id == employee_id)
            count_query = count_query.where(OvertimeRecord.employee_id == employee_id)

    if status_filter:
        query = query.where(OvertimeRecord.status == status_filter)
        count_query = count_query.where(OvertimeRecord.status == status_filter)
    if start_date:
        query = query.where(OvertimeRecord.attendance_date >= start_date)
        count_query = count_query.where(OvertimeRecord.attendance_date >= start_date)
    if end_date:
        query = query.where(OvertimeRecord.attendance_date <= end_date)
        count_query = count_query.where(OvertimeRecord.attendance_date <= end_date)
    if overtime_type:
        query = query.where(OvertimeRecord.overtime_type == overtime_type)
        count_query = count_query.where(OvertimeRecord.overtime_type == overtime_type)

    total = (await session.execute(count_query)).scalar() or 0
    query = (
        query.order_by(OvertimeRecord.attendance_date.desc(), OvertimeRecord.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = list((await session.execute(query)).all())
    return [(row[0], row[1]) for row in items], total


async def get_overtime_record_detail(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    record_id: uuid.UUID,
    user_id: uuid.UUID,
    user_role: str,
) -> tuple[OvertimeRecord, Employee]:
    """Retrieves an individual overtime record with scoping validation."""
    role_lower = user_role.lower()

    stmt = (
        select(OvertimeRecord, Employee)
        .join(Employee, OvertimeRecord.employee_id == Employee.id)
        .where(
            OvertimeRecord.tenant_id == tenant_id,
            OvertimeRecord.id == record_id,
        )
    )
    result = (await session.execute(stmt)).first()
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Overtime record '{record_id}' not found.",
        )
    rec, emp = result[0], result[1]

    if role_lower == "employee":
        user_emp = (
            await session.execute(
                select(Employee.id).where(
                    Employee.tenant_id == tenant_id,
                    Employee.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if user_emp is None or rec.employee_id != user_emp:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Employees may only view their own overtime records.",
            )

    elif role_lower == "manager":
        mgr_emp = (
            await session.execute(
                select(Employee.id).where(
                    Employee.tenant_id == tenant_id,
                    Employee.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if mgr_emp is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Manager profile not found.",
            )
        # Allow viewing own records or direct reports
        if rec.employee_id != mgr_emp and emp.reporting_manager_id != mgr_emp:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Managers may only view overtime records for their direct reports.",
            )

    return rec, emp


async def adjudicate_overtime_record(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    record_id: uuid.UUID,
    reviewer_user_id: uuid.UUID,
    reviewer_role: str,
    payload: OvertimeDecisionRequest,
) -> OvertimeRecord:
    """Adjudicates an overtime record (APPROVE or REJECT) with strict anti-self-approval and manager hierarchy."""
    role_lower = reviewer_role.lower()
    if role_lower == "employee":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employees do not have permission to adjudicate overtime records.",
        )

    # Lock record
    stmt = (
        select(OvertimeRecord)
        .where(
            OvertimeRecord.tenant_id == tenant_id,
            OvertimeRecord.id == record_id,
        )
        .with_for_update()
    )
    record = (await session.execute(stmt)).scalar_one_or_none()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Overtime record '{record_id}' not found.",
        )

    # Fetch target employee
    target_emp = (
        await session.execute(
            select(Employee).where(
                Employee.tenant_id == tenant_id,
                Employee.id == record.employee_id,
            )
        )
    ).scalar_one_or_none()
    if not target_emp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target employee not found.",
        )

    # Fetch reviewer employee profile
    reviewer_emp = (
        await session.execute(
            select(Employee).where(
                Employee.tenant_id == tenant_id,
                Employee.user_id == reviewer_user_id,
            )
        )
    ).scalar_one_or_none()

    # 1. Anti-Self-Approval Enforcement
    if target_emp.user_id == reviewer_user_id or (
        reviewer_emp and target_emp.id == reviewer_emp.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Anti-self-approval violation: Reviewers cannot approve or reject their own overtime records.",
        )

    # 2. Manager Reporting Hierarchy Scoping
    if role_lower == "manager":
        if not reviewer_emp or target_emp.reporting_manager_id != reviewer_emp.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Managers may only adjudicate overtime records for their direct reports.",
            )

    # 3. Validation for REJECT action
    action = payload.action.upper()
    if action == "REJECT":
        if not payload.reason or len(payload.reason.strip()) < 3:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Rejection requires an explanation of at least 3 characters.",
            )

    # 4. Idempotency Check
    if record.status == action:
        # Already decided identically
        return record

    now = datetime.now(UTC)

    # Import AttendanceDay to update projection
    from services.api.attendance.models import AttendanceDay

    day_stmt = (
        select(AttendanceDay)
        .where(
            AttendanceDay.tenant_id == tenant_id,
            AttendanceDay.id == record.attendance_day_id,
        )
        .with_for_update()
    )
    day_rec = (await session.execute(day_stmt)).scalar_one_or_none()

    if action == "APPROVE":
        approved_mins = (
            payload.approved_minutes
            if payload.approved_minutes is not None
            else record.raw_overtime_minutes
        )
        record.approved_overtime_minutes = approved_mins
        record.payable_overtime_minutes = int(round(Decimal(approved_mins) * record.multiplier))
        record.status = "APPROVED"
        record.reviewer_user_id = reviewer_user_id
        record.reviewer_notes = payload.reason
        record.decided_at = now
        record.updated_at = now

        if day_rec:
            day_rec.overtime_minutes = approved_mins
            day_rec.updated_at = now

    elif action == "REJECT":
        record.approved_overtime_minutes = 0
        record.payable_overtime_minutes = 0
        record.status = "REJECTED"
        record.reviewer_user_id = reviewer_user_id
        record.reviewer_notes = payload.reason
        record.decided_at = now
        record.updated_at = now

        if day_rec:
            day_rec.overtime_minutes = 0
            day_rec.updated_at = now

    await session.flush()
    return record
