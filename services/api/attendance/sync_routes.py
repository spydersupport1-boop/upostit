"""FastAPI routes for Downward Delta Synchronization (Phase 11.3)."""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.attendance.downward_sync_schemas import SyncDeltaResponse
from services.api.attendance.downward_sync_service import process_downward_delta_sync
from services.api.auth.dependencies import (
    AuthenticatedContext,
    get_authenticated_context,
    require_permission,
)
from services.api.auth.permissions import Permission
from services.api.database import get_db

sync_router = APIRouter(prefix="/sync", tags=["Sync Engine"])


@sync_router.get(
    "/delta",
    response_model=SyncDeltaResponse,
    status_code=status.HTTP_200_OK,
    summary="Download reference data deltas and shift rosters for offline cache",
    dependencies=[Depends(require_permission(Permission.VIEW_OWN_PROFILE))],
)
async def downward_sync_endpoint(
    cursor: str | None = Query(None, description="Opaque server-generated cursor token from previous sync"),
    limit: int = Query(50, ge=1, le=200, description="Maximum items per page"),
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
) -> SyncDeltaResponse:
    """Retrieves incremental reference data and shift rosters for the authenticated employee.

    Guarantees:
    - Initial full synchronization when cursor is null.
    - Incremental delta synchronization when cursor is provided.
    - Cryptographically verified HMAC cursor with tenant and user isolation.
    - Stable ordering and idempotent retries.
    - Bounded response sizing with pagination.
    - Tombstone generation for deleted or deactivated assignments.
    """
    return await process_downward_delta_sync(
        session=db,
        tenant_id=ctx.tenant.id,
        user_id=ctx.user.id,
        cursor=cursor,
        limit=limit,
    )

