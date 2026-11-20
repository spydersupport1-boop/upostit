"""Business logic service for workplace Wi-Fi access points."""

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.locations.models import Location, WorkplaceWifiAccessPoint
from services.api.locations.schemas import (
    WorkplaceWifiAccessPointCreateRequest,
    WorkplaceWifiAccessPointUpdateRequest,
)


async def create_workplace_wifi_access_point(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID,
    user_id: uuid.UUID | None,
    data: WorkplaceWifiAccessPointCreateRequest,
) -> WorkplaceWifiAccessPoint:
    """Registers an authorized Wi-Fi access point for a workplace location."""
    # Ensure workplace location exists within this tenant
    loc_check = await session.execute(
        select(Location.id).where(
            Location.tenant_id == tenant_id,
            Location.id == location_id,
        )
    )
    if loc_check.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workplace location not found.",
        )

    # Check for duplicate BSSID within the same workplace location
    existing = await session.execute(
        select(WorkplaceWifiAccessPoint.id).where(
            WorkplaceWifiAccessPoint.tenant_id == tenant_id,
            WorkplaceWifiAccessPoint.location_id == location_id,
            WorkplaceWifiAccessPoint.bssid == data.bssid,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Access point with BSSID '{data.bssid}' is already registered for this workplace.",
        )

    now = datetime.now(UTC)
    ap = WorkplaceWifiAccessPoint(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        location_id=location_id,
        friendly_name=data.friendly_name.strip(),
        bssid=data.bssid,
        ssid=data.ssid.strip() if data.ssid else None,
        is_active=data.is_active,
        effective_from=data.effective_from,
        effective_to=data.effective_to,
        created_by_user_id=user_id,
        created_at=now,
        updated_at=now,
    )
    session.add(ap)
    try:
        await session.commit()
        await session.refresh(ap)
    except IntegrityError as exc:
        await session.rollback()
        err_msg = str(exc).lower()
        if "uq_workplace_wifi_location_bssid" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Access point with BSSID '{data.bssid}' is already registered for this workplace.",
            ) from exc
        if "chk_workplace_wifi_bssid_format" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid BSSID format '{data.bssid}'.",
            ) from exc
        if "chk_workplace_wifi_dates" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="effective_to cannot be earlier than effective_from.",
            ) from exc
        raise
    return ap


async def list_workplace_wifi_access_points(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID,
    is_active: bool | None = None,
) -> tuple[list[WorkplaceWifiAccessPoint], int]:
    """Lists authorized Wi-Fi access points for a workplace location."""
    # Verify location belongs to tenant
    loc_check = await session.execute(
        select(Location.id).where(
            Location.tenant_id == tenant_id,
            Location.id == location_id,
        )
    )
    if loc_check.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workplace location not found.",
        )

    stmt = select(WorkplaceWifiAccessPoint).where(
        WorkplaceWifiAccessPoint.tenant_id == tenant_id,
        WorkplaceWifiAccessPoint.location_id == location_id,
    )
    count_stmt = select(func.count(WorkplaceWifiAccessPoint.id)).where(
        WorkplaceWifiAccessPoint.tenant_id == tenant_id,
        WorkplaceWifiAccessPoint.location_id == location_id,
    )

    if is_active is not None:
        stmt = stmt.where(WorkplaceWifiAccessPoint.is_active == is_active)
        count_stmt = count_stmt.where(WorkplaceWifiAccessPoint.is_active == is_active)

    stmt = stmt.order_by(WorkplaceWifiAccessPoint.friendly_name.asc())

    total = (await session.execute(count_stmt)).scalar_one()
    result = await session.execute(stmt)
    return list(result.scalars().all()), total


async def get_workplace_wifi_access_point(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID,
    ap_id: uuid.UUID,
) -> WorkplaceWifiAccessPoint:
    """Retrieves a single Wi-Fi access point by ID."""
    stmt = select(WorkplaceWifiAccessPoint).where(
        WorkplaceWifiAccessPoint.tenant_id == tenant_id,
        WorkplaceWifiAccessPoint.location_id == location_id,
        WorkplaceWifiAccessPoint.id == ap_id,
    )
    result = await session.execute(stmt)
    ap = result.scalar_one_or_none()
    if ap is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wi-Fi access point not found.",
        )
    return ap


async def update_workplace_wifi_access_point(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID,
    ap_id: uuid.UUID,
    data: WorkplaceWifiAccessPointUpdateRequest,
) -> WorkplaceWifiAccessPoint:
    """Updates an existing Wi-Fi access point."""
    ap = await get_workplace_wifi_access_point(
        session=session, tenant_id=tenant_id, location_id=location_id, ap_id=ap_id
    )

    if data.friendly_name is not None:
        ap.friendly_name = data.friendly_name.strip()
    if data.ssid is not None:
        ap.ssid = data.ssid.strip() if data.ssid.strip() else None
    if data.is_active is not None:
        ap.is_active = data.is_active
    if data.effective_from is not None:
        ap.effective_from = data.effective_from
    if data.effective_to is not None:
        ap.effective_to = data.effective_to

    # Verify effective dates consistency
    if ap.effective_to is not None and ap.effective_to < ap.effective_from:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="effective_to cannot be earlier than effective_from.",
        )

    ap.updated_at = datetime.now(UTC)
    try:
        await session.commit()
        await session.refresh(ap)
    except IntegrityError as exc:
        await session.rollback()
        err_msg = str(exc).lower()
        if "chk_workplace_wifi_dates" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="effective_to cannot be earlier than effective_from.",
            ) from exc
        raise
    return ap


async def deactivate_workplace_wifi_access_point(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID,
    ap_id: uuid.UUID,
) -> WorkplaceWifiAccessPoint:
    """Soft deactivates an authorized Wi-Fi access point."""
    ap = await get_workplace_wifi_access_point(
        session=session, tenant_id=tenant_id, location_id=location_id, ap_id=ap_id
    )
    ap.is_active = False
    ap.updated_at = datetime.now(UTC)
    try:
        await session.commit()
        await session.refresh(ap)
    except Exception:
        await session.rollback()
        raise
    return ap

