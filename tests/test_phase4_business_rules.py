"""Unit tests for Phase 4 workplace locations business rules and services."""

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from services.api.auth.models import RefreshToken, User  # noqa: F401
from services.api.employees.models import Employee  # noqa: F401
from services.api.locations.models import Location
from services.api.locations.schemas import (
    LocationCreateRequest,
    LocationUpdateRequest,
)
from services.api.locations.service import (
    create_location,
    date_ranges_overlap,
    deactivate_location,
    get_location,
    haversine_distance_meters,
    list_locations,
    update_location,
    verify_geofence_coordinates,
)
from services.api.organization.models import Department, Designation  # noqa: F401
from services.api.tenants.models import Tenant  # noqa: F401


def test_haversine_distance_calculation():
    """Verify haversine spherical distance calculation on known benchmark points."""
    # Point A: Empire State Building (40.748817, -73.985428)
    # Point B: Times Square (40.758896, -73.985130) -> Distance approx 1.12 km (1120m)
    dist = haversine_distance_meters(40.748817, -73.985428, 40.758896, -73.985130)
    assert 1100 <= dist <= 1140

    # Identical coordinates should be 0 distance
    dist_zero = haversine_distance_meters(12.9249, 77.6744, 12.9249, 77.6744)
    assert round(dist_zero, 4) == 0.0


@pytest.mark.asyncio
async def test_create_location_duplicate_code_rejected():
    """Verify creating a location with an existing code for the same tenant raises HTTP 409."""
    session = AsyncMock()
    tenant_id = uuid.uuid4()

    existing_loc_id = uuid.uuid4()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = existing_loc_id
    session.execute.return_value = mock_res

    req = LocationCreateRequest(
        name="Chicago Branch",
        code="ORD-01",
        address_line1="100 Michigan Ave",
        city="Chicago",
        state="IL",
        country_code="US",
        latitude=Decimal("41.8818"),
        longitude=Decimal("-87.6231"),
        radius_meters=100,
        timezone="America/Chicago",
    )

    with pytest.raises(HTTPException) as exc:
        await create_location(session, tenant_id, req)
    assert exc.value.status_code == 409
    assert "already exists" in exc.value.detail


@pytest.mark.asyncio
async def test_create_location_success():
    """Verify creating a new location persists and commits."""
    session = AsyncMock()
    session.add = MagicMock()
    tenant_id = uuid.uuid4()

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_res

    req = LocationCreateRequest(
        name="Bengaluru Tech Hub",
        code="BLR-01",
        address_line1="Outer Ring Rd",
        city="Bengaluru",
        state="KA",
        postal_code="560103",
        country_code="IN",
        latitude=Decimal("12.9249000"),
        longitude=Decimal("77.6744000"),
        radius_meters=150,
        timezone="Asia/Kolkata",
    )

    loc = await create_location(session, tenant_id, req)
    assert loc.tenant_id == tenant_id
    assert loc.code == "BLR-01"
    assert loc.country_code == "IN"
    assert loc.timezone == "Asia/Kolkata"
    assert loc.is_active is True
    session.add.assert_called_once()
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_get_location_not_found():
    """Verify get_location raises HTTP 404 when location does not exist."""
    session = AsyncMock()
    tenant_id = uuid.uuid4()
    loc_id = uuid.uuid4()

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_res

    with pytest.raises(HTTPException) as exc:
        await get_location(session, tenant_id, loc_id)
    assert exc.value.status_code == 404
    assert "not found" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_list_locations_query():
    """Verify list_locations executes count and pagination query with filters."""
    session = AsyncMock()
    tenant_id = uuid.uuid4()

    # 1. Total count mock
    res_count = MagicMock()
    res_count.scalar_one.return_value = 1

    # 2. Rows mock
    loc = Location(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name="HQ",
        code="HQ-01",
        address_line1="1 Main St",
        city="NYC",
        country_code="US",
        latitude=Decimal("40.7128"),
        longitude=Decimal("-74.0060"),
        radius_meters=100,
        timezone="America/New_York",
        is_active=True,
    )
    res_rows = MagicMock()
    res_rows.scalars.return_value.all.return_value = [loc]

    # 3. Employee counts mock
    res_emp = MagicMock()
    res_emp.all.return_value = [(loc.id, 5)]

    session.execute.side_effect = [res_count, res_rows, res_emp]

    items, total, emp_counts = await list_locations(session, tenant_id, search="HQ", is_active=True)
    assert total == 1
    assert len(items) == 1
    assert items[0].code == "HQ-01"
    assert emp_counts[loc.id] == 5


@pytest.mark.asyncio
async def test_update_location_preserves_historical_assignments():
    """Verify updating location parameters persists and commits without deleting employee_locations."""
    session = AsyncMock()
    tenant_id = uuid.uuid4()
    loc_id = uuid.uuid4()

    loc = Location(
        id=loc_id,
        tenant_id=tenant_id,
        name="Old Name",
        code="HQ-01",
        address_line1="1 Main St",
        city="NYC",
        country_code="US",
        latitude=Decimal("40.7128"),
        longitude=Decimal("-74.0060"),
        radius_meters=100,
        timezone="America/New_York",
        is_active=True,
    )
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = loc
    session.execute.return_value = mock_res

    update_req = LocationUpdateRequest(
        name="New Headquarters",
        radius_meters=200,
    )

    updated = await update_location(session, tenant_id, loc_id, update_req)
    assert updated.name == "New Headquarters"
    assert updated.radius_meters == 200
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_deactivate_location_soft_toggles_is_active():
    """Verify deactivation marks location is_active=False while preserving historical records."""
    session = AsyncMock()
    tenant_id = uuid.uuid4()
    loc_id = uuid.uuid4()

    loc = Location(
        id=loc_id,
        tenant_id=tenant_id,
        name="Site A",
        code="SITE-A",
        address_line1="1 Site Rd",
        city="Austin",
        country_code="US",
        latitude=Decimal("30.2672"),
        longitude=Decimal("-97.7431"),
        radius_meters=100,
        timezone="America/Chicago",
        is_active=True,
    )
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = loc
    session.execute.return_value = mock_res

    deactivated = await deactivate_location(session, tenant_id, loc_id)
    assert deactivated.is_active is False
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_verify_geofence_coordinates_inside_and_outside():
    """Verify geofence coordinate probe identifies inside vs outside coordinates."""
    session = AsyncMock()
    tenant_id = uuid.uuid4()
    loc_id = uuid.uuid4()

    loc = Location(
        id=loc_id,
        tenant_id=tenant_id,
        name="Downtown Office",
        code="DT-01",
        address_line1="100 Market St",
        city="San Francisco",
        country_code="US",
        latitude=Decimal("37.7749000"),
        longitude=Decimal("-122.4194000"),
        radius_meters=100,  # 100 meters
        timezone="America/Los_Angeles",
        is_active=True,
    )
    mock_res_loc = MagicMock()
    mock_res_loc.scalar_one_or_none.return_value = loc

    # Point 1: PostGIS mock for inside point (~11.1 meters)
    mock_dist_inside = MagicMock()
    mock_dist_inside.one_or_none.return_value = (11.1, True)
    session.execute.side_effect = [mock_res_loc, mock_dist_inside]

    res_inside = await verify_geofence_coordinates(
        session, tenant_id, loc_id, Decimal("37.7750000"), Decimal("-122.4194000")
    )
    assert res_inside.within_geofence is True
    assert res_inside.distance_meters <= 100
    assert "Phase 7 Fraud Shield" in res_inside.threat_boundary_notice

    # Point 2: PostGIS mock for outside point (~1111.9 meters)
    mock_dist_outside = MagicMock()
    mock_dist_outside.one_or_none.return_value = (1111.9, False)
    session.execute.side_effect = [mock_res_loc, mock_dist_outside]

    res_outside = await verify_geofence_coordinates(
        session, tenant_id, loc_id, Decimal("37.7849000"), Decimal("-122.4194000")
    )
    assert res_outside.within_geofence is False
    assert res_outside.distance_meters > 100

    # Point 3: Haversine fallback when PostGIS is unavailable / raises exception
    mock_dist_err = MagicMock()
    mock_dist_err.one_or_none.side_effect = RuntimeError("PostGIS function not found")
    session.execute.side_effect = [mock_res_loc, mock_dist_err]

    res_fallback = await verify_geofence_coordinates(
        session, tenant_id, loc_id, Decimal("37.7849000"), Decimal("-122.4194000")
    )
    assert res_fallback.within_geofence is False
    assert res_fallback.distance_meters > 100


def test_primary_workplace_date_ranges_overlap():
    """Verify temporal intersection detection between primary employee assignments.

    Scenario:
    - Primary Location 1: Jan 1 – Jan 31
    - Primary Location 2: Jan 15 – Feb 15
    These overlap and must be flagged as conflicting.
    """
    jan_1 = date(2026, 1, 1)
    jan_15 = date(2026, 1, 15)
    jan_31 = date(2026, 1, 31)
    feb_1 = date(2026, 2, 1)
    feb_15 = date(2026, 2, 15)
    feb_28 = date(2026, 2, 28)
    mar_1 = date(2026, 3, 1)
    mar_15 = date(2026, 3, 15)
    apr_1 = date(2026, 4, 1)
    apr_15 = date(2026, 4, 15)

    # 1. Overlapping date-bounded primary assignments: Jan 1-31 vs Jan 15-Feb 15
    assert date_ranges_overlap(jan_1, jan_31, jan_15, feb_15) is True
    assert date_ranges_overlap(jan_15, feb_15, jan_1, jan_31) is True

    # 2. Contiguous non-overlapping primary assignments: Jan 1-31 vs Feb 1-Feb 28
    assert date_ranges_overlap(jan_1, jan_31, feb_1, feb_28) is False
    assert date_ranges_overlap(feb_1, feb_28, jan_1, jan_31) is False

    # 3. Touching date boundary (same day overlap on Jan 31): Jan 1-31 vs Jan 31-Feb 15
    assert date_ranges_overlap(jan_1, jan_31, jan_31, feb_15) is True

    # 4. Open-ended vs open-ended (both span into +infinity)
    assert date_ranges_overlap(mar_1, None, apr_1, None) is True
    assert date_ranges_overlap(apr_1, None, mar_1, None) is True

    # 5. Open-ended vs prior bounded assignment: Mar 1-None vs Jan 1-Jan 31 (no overlap)
    assert date_ranges_overlap(mar_1, None, jan_1, jan_31) is False
    assert date_ranges_overlap(jan_1, jan_31, mar_1, None) is False

    # 6. Open-ended vs overlapping bounded assignment: Mar 1-None vs Mar 15-Apr 15 (overlap)
    assert date_ranges_overlap(mar_1, None, mar_15, apr_15) is True
    assert date_ranges_overlap(mar_15, apr_15, mar_1, None) is True
