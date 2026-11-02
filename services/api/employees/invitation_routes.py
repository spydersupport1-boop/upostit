"""API routes for employee invitations management under /api/v1/invitations."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.auth.dependencies import (
    AuthenticatedContext,
    get_authenticated_context,
    require_permission,
)
from services.api.auth.permissions import Permission
from services.api.database import get_db
from services.api.employees.invitation_schemas import (
    InvitationListResponse,
    InvitationResponse,
)
from services.api.employees.invitation_service import (
    get_invitation,
    list_invitations,
    resend_invitation,
    revoke_invitation,
)

router = APIRouter(prefix="/invitations", tags=["Employee Invitations"])


@router.get(
    "",
    response_model=InvitationListResponse,
    summary="List employee invitations for the current organization",
    dependencies=[Depends(require_permission(Permission.INVITE_EMPLOYEES))],
)
async def list_invitations_endpoint(
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    status: Annotated[str | None, Query(description="Filter by invitation status")] = None,
    employee_id: Annotated[uuid.UUID | None, Query(description="Filter by employee ID")] = None,
    skip: Annotated[int, Query(ge=0, description="Offset")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Page size")] = 50,
) -> InvitationListResponse:
    """Lists employee invitations for the caller's tenant with pagination and optional filtering."""
    return await list_invitations(
        session=session,
        tenant_id=context.tenant.id,
        status_filter=status,
        employee_id_filter=employee_id,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{invitation_id}",
    response_model=InvitationResponse,
    summary="Retrieve details for a specific invitation",
    dependencies=[Depends(require_permission(Permission.INVITE_EMPLOYEES))],
)
async def get_invitation_endpoint(
    invitation_id: uuid.UUID,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InvitationResponse:
    """Retrieves an employee invitation record by its unique ID within the tenant scope."""
    return await get_invitation(
        session=session,
        tenant_id=context.tenant.id,
        invitation_id=invitation_id,
    )


@router.post(
    "/{invitation_id}/resend",
    response_model=InvitationResponse,
    summary="Regenerate token and resend invitation email",
    dependencies=[Depends(require_permission(Permission.INVITE_EMPLOYEES))],
)
async def resend_invitation_endpoint(
    invitation_id: uuid.UUID,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InvitationResponse:
    """Regenerates a secure token, resets expiry and attempt counts, and redispatches email."""
    return await resend_invitation(
        session=session,
        tenant_id=context.tenant.id,
        invitation_id=invitation_id,
        current_user_id=context.user.id,
    )


@router.post(
    "/{invitation_id}/revoke",
    response_model=InvitationResponse,
    summary="Revoke an outstanding invitation",
    dependencies=[Depends(require_permission(Permission.INVITE_EMPLOYEES))],
)
async def revoke_invitation_endpoint(
    invitation_id: uuid.UUID,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InvitationResponse:
    """Marks an invitation as revoked, preventing future account activation."""
    return await revoke_invitation(
        session=session,
        tenant_id=context.tenant.id,
        invitation_id=invitation_id,
        current_user_id=context.user.id,
    )
