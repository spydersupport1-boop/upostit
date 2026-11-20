"""Service layer for Leave Type configuration and management."""

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.leave.models import LeaveBalance, LeaveRequest, LeaveType
from services.api.leave.schemas import (
    LeaveTypeCreateRequest,
    LeaveTypeResponse,
    LeaveTypeUpdateRequest,
)


def map_leave_type_to_response(lt: LeaveType) -> LeaveTypeResponse:
    """Maps a SQLAlchemy LeaveType model to a Pydantic response."""
    now = datetime.now(UTC)
    return LeaveTypeResponse(
        id=lt.id or uuid.uuid4(),
        tenant_id=lt.tenant_id,
        code=lt.code,
        name=lt.name,
        description=lt.description,
        is_paid=lt.is_paid,
        requires_approval=lt.requires_approval,
        allow_half_day=lt.allow_half_day,
        max_consecutive_days=lt.max_consecutive_days,
        carry_forward_limit=lt.carry_forward_limit,
        is_active=lt.is_active,
        created_at=lt.created_at or now,
        updated_at=lt.updated_at or now,
    )


async def create_leave_type(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    payload: LeaveTypeCreateRequest,
) -> LeaveType:
    """Creates a new leave type within a tenant organization.

    Guarantees:
    - Code uniqueness per tenant (case-insensitive).
    - Validation of carry forward limit (>= 0).
    - Validation of max consecutive days (> 0 if specified).
    """
    code_upper = payload.code.strip().upper()

    # 1. Check for duplicate code within tenant
    existing_stmt = select(LeaveType).where(
        LeaveType.tenant_id == tenant_id,
        func.upper(LeaveType.code) == code_upper,
    )
    existing = (await session.execute(existing_stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Leave type with code '{code_upper}' already exists in this organization.",
        )

    # 2. Instantiate model
    now = datetime.now(UTC)
    leave_type = LeaveType(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        code=code_upper,
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        is_paid=payload.is_paid,
        requires_approval=payload.requires_approval,
        allow_half_day=payload.allow_half_day,
        max_consecutive_days=payload.max_consecutive_days,
        carry_forward_limit=payload.carry_forward_limit,
        is_active=payload.is_active,
        created_at=now,
        updated_at=now,
    )

    session.add(leave_type)
    await session.flush()
    return leave_type


async def list_leave_types(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    search: str | None = None,
    is_active: bool | None = None,
    is_paid: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[LeaveType], int]:
    """Lists and filters leave types for the given tenant."""
    base_conditions = [LeaveType.tenant_id == tenant_id]

    if is_active is not None:
        base_conditions.append(LeaveType.is_active.is_(is_active))
    if is_paid is not None:
        base_conditions.append(LeaveType.is_paid.is_(is_paid))
    if search:
        search_pattern = f"%{search.strip()}%"
        base_conditions.append(
            (LeaveType.name.ilike(search_pattern)) | (LeaveType.code.ilike(search_pattern))
        )

    # Count query
    count_stmt = select(func.count()).select_from(LeaveType).where(*base_conditions)
    total = (await session.execute(count_stmt)).scalar() or 0

    # Data query
    data_stmt = (
        select(LeaveType)
        .where(*base_conditions)
        .order_by(LeaveType.code.asc())
        .limit(limit)
        .offset(offset)
    )
    items = list((await session.execute(data_stmt)).scalars().all())

    return items, total


async def get_leave_type(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    leave_type_id: uuid.UUID,
) -> LeaveType:
    """Retrieves a single leave type by ID scoped to tenant."""
    stmt = select(LeaveType).where(
        LeaveType.id == leave_type_id,
        LeaveType.tenant_id == tenant_id,
    )
    leave_type = (await session.execute(stmt)).scalar_one_or_none()
    if not leave_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Leave type '{leave_type_id}' not found.",
        )
    return leave_type


async def update_leave_type(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    payload: LeaveTypeUpdateRequest,
) -> LeaveType:
    """Updates an existing leave type's configuration."""
    leave_type = await get_leave_type(session, tenant_id, leave_type_id)

    if payload.name is not None:
        leave_type.name = payload.name.strip()
    if payload.description is not None:
        leave_type.description = payload.description.strip() if payload.description else None
    if payload.is_paid is not None:
        leave_type.is_paid = payload.is_paid
    if payload.requires_approval is not None:
        leave_type.requires_approval = payload.requires_approval
    if payload.allow_half_day is not None:
        leave_type.allow_half_day = payload.allow_half_day
    if payload.max_consecutive_days is not None:
        leave_type.max_consecutive_days = payload.max_consecutive_days
    if payload.carry_forward_limit is not None:
        leave_type.carry_forward_limit = payload.carry_forward_limit
    if payload.is_active is not None:
        leave_type.is_active = payload.is_active

    await session.flush()
    return leave_type


async def delete_leave_type(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    leave_type_id: uuid.UUID,
) -> None:
    """Safely deletes a leave type, preventing deletion if referenced by balances or requests."""
    leave_type = await get_leave_type(session, tenant_id, leave_type_id)

    # 1. Check if referenced by leave balances
    balance_count_stmt = (
        select(func.count())
        .select_from(LeaveBalance)
        .where(
            LeaveBalance.tenant_id == tenant_id,
            LeaveBalance.leave_type_id == leave_type_id,
        )
    )
    balance_count = (await session.execute(balance_count_stmt)).scalar() or 0
    if balance_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot delete leave type '{leave_type.code}' because it is referenced by "
                f"{balance_count} employee balance record(s). Deactivate the leave type instead."
            ),
        )

    # 2. Check if referenced by leave requests
    request_count_stmt = (
        select(func.count())
        .select_from(LeaveRequest)
        .where(
            LeaveRequest.tenant_id == tenant_id,
            LeaveRequest.leave_type_id == leave_type_id,
        )
    )
    request_count = (await session.execute(request_count_stmt)).scalar() or 0
    if request_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot delete leave type '{leave_type.code}' because it is referenced by "
                f"{request_count} employee leave request(s). Deactivate the leave type instead."
            ),
        )

    await session.delete(leave_type)
    await session.flush()
