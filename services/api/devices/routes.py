"""FastAPI router for employee device registration, management, and binding under /api/v1/devices."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.auth.dependencies import (
    AuthenticatedContext,
    get_authenticated_context,
    require_permission,
)
from services.api.auth.permissions import Permission
from services.api.database import get_db
from services.api.devices.schemas import (
    DeviceListResponse,
    DeviceRegisterRequest,
    DeviceRegistrationResponse,
    DeviceReplacementApprovalRequest,
    DeviceReRegisterRequest,
    DeviceResponse,
    DeviceRevokeRequest,
    DeviceSecurityStatusResponse,
    DeviceStatusResponse,
)
from services.api.devices.service import (
    approve_device_replacement,
    get_device_by_id,
    get_device_security_status,
    get_employee_device_status,
    list_devices,
    re_register_device,
    register_device,
    revoke_device,
)
from services.api.employees.models import Employee

router = APIRouter(prefix="/devices", tags=["Device Binding"])


@router.post(
    "/register",
    response_model=DeviceRegistrationResponse,
    status_code=status.HTTP_200_OK,
    summary="Register Employee Device",
    description="Registers a mobile or client device for the authenticated employee, enforcing the single-device policy.",
)
async def register_device_endpoint(
    payload: DeviceRegisterRequest,
    ctx: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DeviceRegistrationResponse:
    """Registers an employee's mobile device against their authenticated profile."""
    # Resolve the calling user's employee record
    emp_stmt = select(Employee).where(
        Employee.tenant_id == ctx.tenant.id,
        Employee.user_id == ctx.user.id,
    )
    emp = (await db.execute(emp_stmt)).scalar_one_or_none()
    if emp is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No employee profile linked to current user account.",
        )

    return await register_device(
        session=db,
        tenant_id=ctx.tenant.id,
        employee_id=emp.id,
        payload=payload,
    )


@router.get(
    "/me",
    response_model=DeviceStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get My Device Status",
    description="Retrieves the active or pending device binding status for the calling employee.",
)
async def get_my_device_status_endpoint(
    ctx: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DeviceStatusResponse:
    """Returns the current user's bound mobile device information."""
    emp_stmt = select(Employee).where(
        Employee.tenant_id == ctx.tenant.id,
        Employee.user_id == ctx.user.id,
    )
    emp = (await db.execute(emp_stmt)).scalar_one_or_none()
    if emp is None:
        return DeviceStatusResponse(is_bound=False, status=None, device=None)

    return await get_employee_device_status(
        session=db,
        tenant_id=ctx.tenant.id,
        employee_id=emp.id,
    )


@router.get(
    "/security-status",
    response_model=DeviceSecurityStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Device Security Status",
    description="Returns device security posture, revocation status, and encryption parameters.",
)
async def get_device_security_status_endpoint(
    ctx: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DeviceSecurityStatusResponse:
    emp_stmt = select(Employee).where(
        Employee.tenant_id == ctx.tenant.id,
        Employee.user_id == ctx.user.id,
    )
    emp = (await db.execute(emp_stmt)).scalar_one_or_none()
    if emp is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current user has no employee profile.",
        )
    return await get_device_security_status(db, ctx.tenant.id, emp.id)


@router.post(
    "/re-register",
    response_model=DeviceRegistrationResponse,
    status_code=status.HTTP_200_OK,
    summary="Re-Register Device",
    description="Re-registers a mobile device following key wipe, recovery, or hardware replacement.",
)
async def re_register_device_endpoint(
    payload: DeviceReRegisterRequest,
    ctx: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DeviceRegistrationResponse:
    emp_stmt = select(Employee).where(
        Employee.tenant_id == ctx.tenant.id,
        Employee.user_id == ctx.user.id,
    )
    emp = (await db.execute(emp_stmt)).scalar_one_or_none()
    if emp is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current user has no employee profile.",
        )
    return await re_register_device(db, ctx.tenant.id, emp.id, payload)


@router.get(
    "",
    response_model=DeviceListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Organization Devices",
    description="Lists registered employee devices within the tenant. Requires VIEW_DEVICES permission.",
    dependencies=[Depends(require_permission(Permission.VIEW_DEVICES))],
)
async def list_devices_endpoint(
    ctx: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    employee_id: uuid.UUID | None = Query(default=None, description="Filter by employee ID."),
    status: str | None = Query(default=None, description="Filter by device status."),
    platform: str | None = Query(default=None, description="Filter by platform."),
    limit: int = Query(default=50, ge=1, le=100, description="Items per page."),
    offset: int = Query(default=0, ge=0, description="Page offset."),
) -> DeviceListResponse:
    """Lists company devices with filtering and pagination."""
    items, total = await list_devices(
        session=db,
        tenant_id=ctx.tenant.id,
        employee_id=employee_id,
        status_filter=status,
        platform_filter=platform,
        limit=limit,
        offset=offset,
    )
    return DeviceListResponse(
        items=[DeviceResponse.model_validate(d) for d in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{device_id}",
    response_model=DeviceResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Device Details",
    description="Retrieves metadata for a specific registered device. Requires VIEW_DEVICES permission.",
    dependencies=[Depends(require_permission(Permission.VIEW_DEVICES))],
)
async def get_device_endpoint(
    device_id: uuid.UUID,
    ctx: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DeviceResponse:
    """Fetches details for a single device by ID."""
    device = await get_device_by_id(
        session=db,
        tenant_id=ctx.tenant.id,
        device_id=device_id,
    )
    return DeviceResponse.model_validate(device)


@router.post(
    "/{device_id}/revoke",
    response_model=DeviceResponse,
    status_code=status.HTTP_200_OK,
    summary="Revoke Device Registration",
    description="Revokes a registered device, barring it from recording attendance. Requires MANAGE_DEVICES permission.",
    dependencies=[Depends(require_permission(Permission.MANAGE_DEVICES))],
)
async def revoke_device_endpoint(
    device_id: uuid.UUID,
    payload: DeviceRevokeRequest,
    ctx: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DeviceResponse:
    """Revokes a device registration with a mandatory reason."""
    revoked = await revoke_device(
        session=db,
        tenant_id=ctx.tenant.id,
        device_id=device_id,
        actor_user_id=ctx.user.id,
        reason=payload.reason,
    )
    return DeviceResponse.model_validate(revoked)


@router.post(
    "/{device_id}/approve-replacement",
    response_model=DeviceResponse,
    status_code=status.HTTP_200_OK,
    summary="Approve Device Replacement",
    description="Approves a pending device replacement request, deactivating the previous device. Requires MANAGE_DEVICES permission.",
    dependencies=[Depends(require_permission(Permission.MANAGE_DEVICES))],
)
async def approve_replacement_endpoint(
    device_id: uuid.UUID,
    payload: DeviceReplacementApprovalRequest,
    ctx: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DeviceResponse:
    """Approves a replacement device, atomically rotating the employee's active device."""
    approved_device, _ = await approve_device_replacement(
        session=db,
        tenant_id=ctx.tenant.id,
        device_id=device_id,
        actor_user_id=ctx.user.id,
        notes=payload.notes,
    )
    return DeviceResponse.model_validate(approved_device)
