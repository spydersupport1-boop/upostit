"""Business logic service for workplace locations and geofence verification."""

import math
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.locations.models import EmployeeLocation, Location
from services.api.locations.schemas import (
    GeofenceVerifyResponse,
    LocationCreateRequest,
    LocationResponse,
    LocationUpdateRequest,
)


def date_ranges_overlap(
    start1: date,
    end1: date | None,
    start2: date,
    end2: date | None,
) -> bool:
    """Evaluates whether two date intervals [start1, end1] and [start2, end2] intersect.

    None represents an open-ended interval (+infinity). Both endpoints are inclusive.
    """
    e1 = end1 or date.max
    e2 = end2 or date.max
    return start1 <= e2 and start2 <= e1


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates spherical distance between two WGS 84 coordinates in meters using the Haversine formula."""
    r = 6371000.0  # Mean radius of the Earth in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


async def create_location(
    session: AsyncSession, tenant_id: uuid.UUID, data: LocationCreateRequest
) -> Location:
    """Creates a new workplace location with coordinates and geofencing radius."""
    # Check for duplicate code within tenant
    code_check = await session.execute(
        select(Location.id).where(Location.tenant_id == tenant_id, Location.code == data.code)
    )
    if code_check.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Workplace location with code '{data.code}' already exists.",
        )

    now = datetime.now(UTC)
    location = Location(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name=data.name.strip(),
        code=data.code,
        address_line1=data.address_line1.strip(),
        address_line2=data.address_line2.strip() if data.address_line2 else None,
        city=data.city.strip(),
        state=data.state.strip() if data.state else None,
        postal_code=data.postal_code.strip() if data.postal_code else None,
        country_code=data.country_code,
        latitude=data.latitude,
        longitude=data.longitude,
        radius_meters=data.radius_meters,
        timezone=data.timezone,
        wifi_bssids=data.wifi_bssids,
        ip_ranges=data.ip_ranges,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    session.add(location)
    await session.commit()
    await session.refresh(location)
    return location


async def get_location(
    session: AsyncSession, tenant_id: uuid.UUID, location_id: uuid.UUID
) -> Location:
    """Fetches a specific workplace location by ID."""
    stmt = select(Location).where(Location.tenant_id == tenant_id, Location.id == location_id)
    result = await session.execute(stmt)
    location = result.scalar_one_or_none()
    if location is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workplace location not found.",
        )
    return location


async def list_locations(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    search: str | None = None,
    is_active: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Location], int, dict[uuid.UUID, int]]:
    """Retrieves paginated workplace locations along with total counts and assigned active employee tallies."""
    base_query = select(Location).where(Location.tenant_id == tenant_id)

    if search:
        search_pattern = f"%{search.strip()}%"
        base_query = base_query.where(
            (Location.name.ilike(search_pattern))
            | (Location.code.ilike(search_pattern))
            | (Location.city.ilike(search_pattern))
        )

    if is_active is not None:
        base_query = base_query.where(Location.is_active == is_active)

    # 1. Total count
    count_stmt = select(func.count()).select_from(base_query.subquery())
    count_res = await session.execute(count_stmt)
    total = count_res.scalar_one() or 0

    # 2. Paginated rows
    rows_stmt = base_query.order_by(Location.name.asc()).limit(limit).offset(offset)
    rows_res = await session.execute(rows_stmt)
    locations = list(rows_res.scalars().all())

    # 3. Active employee counts per location
    emp_counts: dict[uuid.UUID, int] = {}
    if locations:
        loc_ids = [loc.id for loc in locations]
        emp_count_stmt = (
            select(EmployeeLocation.location_id, func.count(EmployeeLocation.id))
            .where(
                EmployeeLocation.tenant_id == tenant_id,
                EmployeeLocation.location_id.in_(loc_ids),
                EmployeeLocation.effective_to.is_(None),
            )
            .group_by(EmployeeLocation.location_id)
        )
        emp_count_res = await session.execute(emp_count_stmt)
        for loc_id, count in emp_count_res.all():
            emp_counts[loc_id] = count

    return locations, total, emp_counts


async def update_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID,
    data: LocationUpdateRequest,
) -> Location:
    """Updates an existing workplace location."""
    location = await get_location(session, tenant_id, location_id)

    if data.name is not None:
        location.name = data.name.strip()
    if data.address_line1 is not None:
        location.address_line1 = data.address_line1.strip()
    if data.address_line2 is not None:
        location.address_line2 = data.address_line2.strip() if data.address_line2 else None
    if data.city is not None:
        location.city = data.city.strip()
    if data.state is not None:
        location.state = data.state.strip() if data.state else None
    if data.postal_code is not None:
        location.postal_code = data.postal_code.strip() if data.postal_code else None
    if data.country_code is not None:
        location.country_code = data.country_code
    if data.latitude is not None:
        location.latitude = data.latitude
    if data.longitude is not None:
        location.longitude = data.longitude
    if data.radius_meters is not None:
        location.radius_meters = data.radius_meters
    if data.timezone is not None:
        location.timezone = data.timezone
    if data.wifi_bssids is not None:
        location.wifi_bssids = data.wifi_bssids
    if data.ip_ranges is not None:
        location.ip_ranges = data.ip_ranges
    if data.is_active is not None:
        # Note: Historical assignments are preserved in employee_locations
        location.is_active = data.is_active

    await session.commit()
    await session.refresh(location)
    return location


async def deactivate_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID,
) -> Location:
    """Deactivates a workplace location while preserving historical employee assignments."""
    location = await get_location(session, tenant_id, location_id)
    location.is_active = False
    await session.commit()
    await session.refresh(location)
    return location


async def verify_geofence_coordinates(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID,
    latitude: Decimal,
    longitude: Decimal,
) -> GeofenceVerifyResponse:
    """Tests reported coordinate proximity against a workplace geofence radius.

    IMPORTANT THREAT BOUNDARY:
    ST_DWithin validates that the reported coordinate payload is mathematically within the geofence.
    It DOES NOT verify hardware GPS authenticity or detect mock location spoofing.
    Anti-spoofing flags, app integrity attestations, and selfie liveness are enforced in Phase 7 Fraud Shield.
    """
    location = await get_location(session, tenant_id, location_id)

    # In PostgreSQL, execute PostGIS ST_Distance and ST_DWithin over indexed geography coordinates
    try:
        dist_stmt = text(
            "SELECT "
            "ST_Distance(coordinates, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) AS distance_meters, "
            "ST_DWithin(coordinates, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :radius) AS within_geofence "
            "FROM locations "
            "WHERE id = :loc_id AND tenant_id = :tenant_id"
        )
        dist_res = await session.execute(
            dist_stmt,
            {
                "lon": float(longitude),
                "lat": float(latitude),
                "radius": float(location.radius_meters),
                "loc_id": location.id,
                "tenant_id": tenant_id,
            },
        )
        row = dist_res.one_or_none()
        if row is not None:
            distance_meters = float(row[0])
            within_geofence = bool(row[1])
        else:
            raise ValueError("Empty spatial query result")
    except Exception:
        # Fallback to spherical Haversine computation if PostGIS functions are unavailable in mock/SQLite tests
        distance_meters = haversine_distance_meters(
            float(location.latitude), float(location.longitude), float(latitude), float(longitude)
        )
        within_geofence = distance_meters <= location.radius_meters

    return GeofenceVerifyResponse(
        location_id=location.id,
        location_name=location.name,
        location_code=location.code,
        radius_meters=location.radius_meters,
        reported_latitude=latitude,
        reported_longitude=longitude,
        distance_meters=round(distance_meters, 2),
        within_geofence=within_geofence,
    )


def map_location_to_response(location: Location, employee_count: int = 0) -> LocationResponse:
    """Helper to serialize a Location SQLAlchemy model to LocationResponse DTO."""
    return LocationResponse(
        id=location.id,
        tenant_id=location.tenant_id,
        name=location.name,
        code=location.code,
        address_line1=location.address_line1,
        address_line2=location.address_line2,
        city=location.city,
        state=location.state,
        postal_code=location.postal_code,
        country_code=location.country_code,
        latitude=location.latitude,
        longitude=location.longitude,
        radius_meters=location.radius_meters,
        timezone=location.timezone,
        wifi_bssids=location.wifi_bssids or [],
        ip_ranges=location.ip_ranges or [],
        is_active=location.is_active,
        employee_count=employee_count,
        created_at=location.created_at,
        updated_at=location.updated_at,
    )
