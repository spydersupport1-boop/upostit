"""FastAPI route handlers for workplace locations and geofence verification."""

import uuid
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
from services.api.locations.assignment_service import list_location_employees
from services.api.locations.schemas import (
    GeofenceVerifyRequest,
    GeofenceVerifyResponse,
    LocationCreateRequest,
    LocationEmployeeListResponse,
    LocationListResponse,
    LocationResponse,
    LocationUpdateRequest,
    WorkplaceWifiAccessPointCreateRequest,
    WorkplaceWifiAccessPointListResponse,
    WorkplaceWifiAccessPointResponse,
    WorkplaceWifiAccessPointUpdateRequest,
)
from services.api.locations.service import (
    create_location,
    deactivate_location,
    get_location,
    list_locations,
    map_location_to_response,
    update_location,
    verify_geofence_coordinates,
)
from services.api.locations.wifi_service import (
    create_workplace_wifi_access_point,
    deactivate_workplace_wifi_access_point,
    get_workplace_wifi_access_point,
    list_workplace_wifi_access_points,
    update_workplace_wifi_access_point,
)

router = APIRouter(prefix="/locations", tags=["Workplaces & Locations"])


@router.get(
    "",
    response_model=LocationListResponse,
    summary="List workplace locations",
    dependencies=[Depends(require_permission(Permission.VIEW_LOCATIONS))],
)
async def get_locations_endpoint(
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    search: Annotated[
        str | None, Query(description="Search by location name, code, or city")
    ] = None,
    is_active: Annotated[bool | None, Query(description="Filter by active status")] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 50,
    offset: Annotated[int, Query(ge=0, description="Page offset")] = 0,
) -> LocationListResponse:
    """Retrieves paginated workplace locations for the caller's tenant."""
    locations, total, emp_counts = await list_locations(
        session=session,
        tenant_id=context.tenant.id,
        search=search,
        is_active=is_active,
        limit=limit,
        offset=offset,
    )
    items = [map_location_to_response(loc, emp_counts.get(loc.id, 0)) for loc in locations]
    return LocationListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post(
    "",
    response_model=LocationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create workplace location",
    dependencies=[Depends(require_permission(Permission.MANAGE_LOCATIONS))],
)
async def create_location_endpoint(
    request: LocationCreateRequest,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> LocationResponse:
    """Creates a new geofenced workplace location."""
    location = await create_location(session=session, tenant_id=context.tenant.id, data=request)
    return map_location_to_response(location, employee_count=0)


@router.get(
    "/{location_id}",
    response_model=LocationResponse,
    summary="Get workplace location details",
    dependencies=[Depends(require_permission(Permission.VIEW_LOCATIONS))],
)
async def get_location_endpoint(
    location_id: uuid.UUID,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> LocationResponse:
    """Retrieves a specific workplace location by ID."""
    location = await get_location(
        session=session, tenant_id=context.tenant.id, location_id=location_id
    )
    return map_location_to_response(location, employee_count=0)


@router.put(
    "/{location_id}",
    response_model=LocationResponse,
    summary="Update workplace location",
    dependencies=[Depends(require_permission(Permission.MANAGE_LOCATIONS))],
)
async def update_location_endpoint(
    location_id: uuid.UUID,
    request: LocationUpdateRequest,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> LocationResponse:
    """Updates an existing workplace location's parameters or geofence radius."""
    location = await update_location(
        session=session,
        tenant_id=context.tenant.id,
        location_id=location_id,
        data=request,
    )
    return map_location_to_response(location, employee_count=0)


@router.delete(
    "/{location_id}",
    response_model=LocationResponse,
    summary="Deactivate workplace location",
    dependencies=[Depends(require_permission(Permission.MANAGE_LOCATIONS))],
)
async def deactivate_location_endpoint(
    location_id: uuid.UUID,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> LocationResponse:
    """Deactivates a workplace location while safely preserving historical employee assignments."""
    location = await deactivate_location(
        session=session, tenant_id=context.tenant.id, location_id=location_id
    )
    return map_location_to_response(location, employee_count=0)


@router.post(
    "/verify-coordinates",
    response_model=GeofenceVerifyResponse,
    summary="Test coordinate proximity against geofence",
    dependencies=[Depends(require_permission(Permission.VIEW_LOCATIONS))],
)
async def verify_coordinates_endpoint(
    request: GeofenceVerifyRequest,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> GeofenceVerifyResponse:
    """Validates whether a coordinate pair falls within a workplace's geofence perimeter using ST_DWithin.

    Note: ST_DWithin checks geometric spherical proximity only. GPS spoofing protection is in Phase 7.
    """
    return await verify_geofence_coordinates(
        session=session,
        tenant_id=context.tenant.id,
        location_id=request.location_id,
        latitude=request.latitude,
        longitude=request.longitude,
    )


@router.get(
    "/{location_id}/employees",
    response_model=LocationEmployeeListResponse,
    summary="List employees assigned to a workplace location",
    dependencies=[Depends(require_permission(Permission.VIEW_LOCATIONS))],
)
async def list_location_employees_endpoint(
    location_id: uuid.UUID,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    search: Annotated[
        str | None,
        Query(description="Search by employee name, code, or email"),
    ] = None,
    is_primary: Annotated[
        bool | None,
        Query(description="Filter by primary workplace status"),
    ] = None,
    is_current: Annotated[
        bool | None,
        Query(description="Filter by currently effective status"),
    ] = None,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
) -> LocationEmployeeListResponse:
    """Lists employees assigned to a workplace location with search and filtering."""
    items, total = await list_location_employees(
        session=session,
        tenant_id=context.tenant.id,
        location_id=location_id,
        search=search,
        is_primary=is_primary,
        is_current=is_current,
        page=page,
        page_size=page_size,
    )
    return LocationEmployeeListResponse(items=items, total=total, page=page, page_size=page_size)


# ---------------------------------------------------------------------------
# Workplace Wi-Fi Access Point Endpoints (Phase 6 Milestone 6.4.A)
# ---------------------------------------------------------------------------


@router.post(
    "/{location_id}/wifi-access-points",
    response_model=WorkplaceWifiAccessPointResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register an authorized Wi-Fi access point for a workplace",
    dependencies=[Depends(require_permission(Permission.MANAGE_LOCATIONS))],
)
async def create_wifi_access_point_endpoint(
    location_id: uuid.UUID,
    data: WorkplaceWifiAccessPointCreateRequest,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> WorkplaceWifiAccessPointResponse:
    """Registers an authorized Wi-Fi access point (BSSID) for attendance verification."""
    ap = await create_workplace_wifi_access_point(
        session=session,
        tenant_id=context.tenant.id,
        location_id=location_id,
        user_id=context.user.id,
        data=data,
    )
    return WorkplaceWifiAccessPointResponse.model_validate(ap)


@router.get(
    "/{location_id}/wifi-access-points",
    response_model=WorkplaceWifiAccessPointListResponse,
    summary="List authorized Wi-Fi access points for a workplace",
    dependencies=[Depends(require_permission(Permission.VIEW_LOCATIONS))],
)
async def list_wifi_access_points_endpoint(
    location_id: uuid.UUID,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    is_active: Annotated[bool | None, Query(description="Filter by active status")] = None,
) -> WorkplaceWifiAccessPointListResponse:
    """Retrieves all authorized Wi-Fi access points configured for a workplace."""
    items, total = await list_workplace_wifi_access_points(
        session=session,
        tenant_id=context.tenant.id,
        location_id=location_id,
        is_active=is_active,
    )
    return WorkplaceWifiAccessPointListResponse(
        items=[WorkplaceWifiAccessPointResponse.model_validate(ap) for ap in items],
        total=total,
    )


@router.get(
    "/{location_id}/wifi-access-points/{ap_id}",
    response_model=WorkplaceWifiAccessPointResponse,
    summary="Get details of a workplace Wi-Fi access point",
    dependencies=[Depends(require_permission(Permission.VIEW_LOCATIONS))],
)
async def get_wifi_access_point_endpoint(
    location_id: uuid.UUID,
    ap_id: uuid.UUID,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> WorkplaceWifiAccessPointResponse:
    """Retrieves details of a specific authorized Wi-Fi access point."""
    ap = await get_workplace_wifi_access_point(
        session=session,
        tenant_id=context.tenant.id,
        location_id=location_id,
        ap_id=ap_id,
    )
    return WorkplaceWifiAccessPointResponse.model_validate(ap)


@router.patch(
    "/{location_id}/wifi-access-points/{ap_id}",
    response_model=WorkplaceWifiAccessPointResponse,
    summary="Update a workplace Wi-Fi access point",
    dependencies=[Depends(require_permission(Permission.MANAGE_LOCATIONS))],
)
async def update_wifi_access_point_endpoint(
    location_id: uuid.UUID,
    ap_id: uuid.UUID,
    data: WorkplaceWifiAccessPointUpdateRequest,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> WorkplaceWifiAccessPointResponse:
    """Updates friendly name, SSID, active status, or effective dates for an access point."""
    ap = await update_workplace_wifi_access_point(
        session=session,
        tenant_id=context.tenant.id,
        location_id=location_id,
        ap_id=ap_id,
        data=data,
    )
    return WorkplaceWifiAccessPointResponse.model_validate(ap)


@router.delete(
    "/{location_id}/wifi-access-points/{ap_id}",
    response_model=WorkplaceWifiAccessPointResponse,
    summary="Deactivate a workplace Wi-Fi access point",
    dependencies=[Depends(require_permission(Permission.MANAGE_LOCATIONS))],
)
async def deactivate_wifi_access_point_endpoint(
    location_id: uuid.UUID,
    ap_id: uuid.UUID,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> WorkplaceWifiAccessPointResponse:
    """Soft-deactivates an access point so it can no longer be used for attendance verification."""
    ap = await deactivate_workplace_wifi_access_point(
        session=session,
        tenant_id=context.tenant.id,
        location_id=location_id,
        ap_id=ap_id,
    )
    return WorkplaceWifiAccessPointResponse.model_validate(ap)


