"""Unit tests for Phase 4 workplace location schemas and validation."""

import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from services.api.locations.schemas import (
    GeofenceVerifyRequest,
    GeofenceVerifyResponse,
    LocationCreateRequest,
    LocationUpdateRequest,
)


def test_location_create_valid_india():
    """Verify valid location creation in India (Asia/Kolkata)."""
    req = LocationCreateRequest(
        name="Bengaluru Technology Center",
        code="BLR-TECH-01",
        address_line1="100 Outer Ring Road, Bellandur",
        city="Bengaluru",
        state="Karnataka",
        postal_code="560103",
        country_code="IN",
        latitude=Decimal("12.9249000"),
        longitude=Decimal("77.6744000"),
        radius_meters=150,
        timezone="Asia/Kolkata",
        wifi_bssids=["00:1A:2B:3C:4D:5E", "aa:bb:cc:dd:ee:ff"],
        ip_ranges=["203.0.113.0/24"],
    )
    assert req.name == "Bengaluru Technology Center"
    assert req.code == "BLR-TECH-01"
    assert req.country_code == "IN"
    assert req.timezone == "Asia/Kolkata"
    assert req.wifi_bssids == ["00:1A:2B:3C:4D:5E", "AA:BB:CC:DD:EE:FF"]
    assert req.ip_ranges == ["203.0.113.0/24"]


def test_location_create_valid_us():
    """Verify valid location creation in US (America/New_York)."""
    req = LocationCreateRequest(
        name="Manhattan HQ",
        code="NYC-HQ-01",
        address_line1="350 5th Ave",
        city="New York",
        state="NY",
        postal_code="10118",
        country_code="US",
        latitude=Decimal("40.7484000"),
        longitude=Decimal("-73.9857000"),
        radius_meters=80,
        timezone="America/New_York",
    )
    assert req.country_code == "US"
    assert req.timezone == "America/New_York"
    assert req.radius_meters == 80


def test_location_create_invalid_country_code():
    """Verify invalid country codes are rejected."""
    with pytest.raises(ValidationError) as exc:
        LocationCreateRequest(
            name="Office",
            code="OFF-01",
            address_line1="Street 1",
            city="City",
            country_code="IND",  # 3 letters instead of 2
            latitude=Decimal("10.0"),
            longitude=Decimal("20.0"),
            timezone="UTC",
        )
    assert "Invalid country code" in str(exc.value)


def test_location_create_invalid_timezone():
    """Verify non-IANA timezones are rejected."""
    with pytest.raises(ValidationError) as exc:
        LocationCreateRequest(
            name="Office",
            code="OFF-01",
            address_line1="Street 1",
            city="City",
            country_code="IN",
            latitude=Decimal("12.0"),
            longitude=Decimal("77.0"),
            timezone="Mars/Olympus",  # Invalid IANA timezone
        )
    assert "Invalid IANA timezone" in str(exc.value)


def test_location_create_latitude_bounds():
    """Verify latitude boundary checks (-90 to +90)."""
    with pytest.raises(ValidationError):
        LocationCreateRequest(
            name="Office",
            code="OFF-01",
            address_line1="Street 1",
            city="City",
            country_code="US",
            latitude=Decimal("91.0000000"),  # Out of range
            longitude=Decimal("0.0"),
            timezone="UTC",
        )

    with pytest.raises(ValidationError):
        LocationCreateRequest(
            name="Office",
            code="OFF-01",
            address_line1="Street 1",
            city="City",
            country_code="US",
            latitude=Decimal("-90.0000001"),  # Out of range
            longitude=Decimal("0.0"),
            timezone="UTC",
        )


def test_location_create_longitude_bounds():
    """Verify longitude boundary checks (-180 to +180)."""
    with pytest.raises(ValidationError):
        LocationCreateRequest(
            name="Office",
            code="OFF-01",
            address_line1="Street 1",
            city="City",
            country_code="US",
            latitude=Decimal("0.0"),
            longitude=Decimal("180.0000001"),  # Out of range
            timezone="UTC",
        )


def test_location_create_radius_bounds():
    """Verify radius boundary checks (10m to 50,000m)."""
    with pytest.raises(ValidationError):
        LocationCreateRequest(
            name="Office",
            code="OFF-01",
            address_line1="Street 1",
            city="City",
            country_code="US",
            latitude=Decimal("0.0"),
            longitude=Decimal("0.0"),
            radius_meters=5,  # Too small (<10m)
            timezone="UTC",
        )

    with pytest.raises(ValidationError):
        LocationCreateRequest(
            name="Office",
            code="OFF-01",
            address_line1="Street 1",
            city="City",
            country_code="US",
            latitude=Decimal("0.0"),
            longitude=Decimal("0.0"),
            radius_meters=60000,  # Too large (>50,000m)
            timezone="UTC",
        )


def test_location_create_invalid_bssid():
    """Verify malformed BSSID format is rejected."""
    with pytest.raises(ValidationError) as exc:
        LocationCreateRequest(
            name="Office",
            code="OFF-01",
            address_line1="Street 1",
            city="City",
            country_code="US",
            latitude=Decimal("0.0"),
            longitude=Decimal("0.0"),
            timezone="UTC",
            wifi_bssids=["not-a-mac-address"],
        )
    assert "Invalid BSSID format" in str(exc.value)


def test_location_create_invalid_ip_range():
    """Verify malformed IP CIDR range is rejected."""
    with pytest.raises(ValidationError) as exc:
        LocationCreateRequest(
            name="Office",
            code="OFF-01",
            address_line1="Street 1",
            city="City",
            country_code="US",
            latitude=Decimal("0.0"),
            longitude=Decimal("0.0"),
            timezone="UTC",
            ip_ranges=["999.999.999.999/99"],
        )
    assert "Invalid IP CIDR range" in str(exc.value)


def test_location_update_partial_valid():
    """Verify partial updates allow updating individual attributes."""
    req = LocationUpdateRequest(
        name="Updated Hub",
        radius_meters=200,
        is_active=False,
    )
    assert req.name == "Updated Hub"
    assert req.radius_meters == 200
    assert req.is_active is False
    assert req.timezone is None


def test_geofence_verify_request_and_response():
    """Verify geofence verification request and response schema."""
    loc_id = uuid.uuid4()
    req = GeofenceVerifyRequest(
        location_id=loc_id,
        latitude=Decimal("12.9250000"),
        longitude=Decimal("77.6745000"),
    )
    assert req.location_id == loc_id
    assert req.latitude == Decimal("12.9250000")

    res = GeofenceVerifyResponse(
        location_id=loc_id,
        location_name="Bengaluru Center",
        location_code="BLR-01",
        radius_meters=100,
        reported_latitude=Decimal("12.9250000"),
        reported_longitude=Decimal("77.6745000"),
        distance_meters=15.42,
        within_geofence=True,
    )
    assert res.within_geofence is True
    assert "ST_DWithin verifies mathematical proximity" in res.threat_boundary_notice
    assert "Phase 7 Fraud Shield" in res.threat_boundary_notice
