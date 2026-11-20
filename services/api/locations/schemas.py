"""Pydantic schemas and DTOs for workplace location management and geofence verification."""

import ipaddress
import re
import uuid
import zoneinfo
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Pre-load available system IANA timezones for O(1) lookup
AVAILABLE_TIMEZONES = zoneinfo.available_timezones()

# ISO 3166-1 alpha-2 2-letter uppercase country code pattern
COUNTRY_CODE_REGEX = re.compile(r"^[A-Z]{2}$")

# IEEE 802 standard MAC/BSSID pattern (e.g. 00:1A:2B:3C:4D:5E or 00-1A-2B-3C-4D-5E)
BSSID_REGEX = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")


class LocationCreateRequest(BaseModel):
    """Payload for creating a workplace location."""

    name: str = Field(..., min_length=1, max_length=255, description="Workplace site name")
    code: str = Field(
        ...,
        min_length=1,
        max_length=50,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Unique workplace code within the tenant organization",
    )
    address_line1: str = Field(..., min_length=1, max_length=255, description="Street address")
    address_line2: str | None = Field(
        default=None, max_length=255, description="Suite, building, floor"
    )
    city: str = Field(..., min_length=1, max_length=100, description="City or municipality")
    state: str | None = Field(
        default=None, max_length=100, description="State, province, or region"
    )
    postal_code: str | None = Field(default=None, max_length=20, description="Postal or ZIP code")
    country_code: str = Field(
        ..., description="ISO 3166-1 alpha-2 two-letter country code (e.g. IN, US, AE, GB)"
    )
    latitude: Decimal = Field(..., ge=-90, le=90, description="WGS 84 latitude in decimal degrees")
    longitude: Decimal = Field(
        ..., ge=-180, le=180, description="WGS 84 longitude in decimal degrees"
    )
    radius_meters: int = Field(
        default=100,
        ge=10,
        le=50000,
        description="Geofence circular radius in meters (10m to 50,000m)",
    )
    timezone: str = Field(
        ..., description="IANA timezone identifier (e.g. Asia/Kolkata, America/New_York)"
    )
    wifi_bssids: list[str] = Field(
        default_factory=list, description="Authorized Wi-Fi BSSID MAC addresses"
    )
    ip_ranges: list[str] = Field(
        default_factory=list, description="Authorized public IP CIDR ranges"
    )

    @field_validator("code")
    @classmethod
    def normalize_code(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("country_code")
    @classmethod
    def validate_country_code(cls, v: str) -> str:
        code = v.strip().upper()
        if not COUNTRY_CODE_REGEX.match(code):
            raise ValueError(
                f"Invalid country code '{v}'. Must be a 2-letter uppercase ISO 3166-1 alpha-2 code."
            )
        return code

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        tz = v.strip()
        if tz not in AVAILABLE_TIMEZONES:
            raise ValueError(
                f"Invalid IANA timezone '{v}'. Must be a valid identifier from the IANA Time Zone Database (e.g. 'Asia/Kolkata', 'America/New_York')."
            )
        return tz

    @field_validator("wifi_bssids")
    @classmethod
    def validate_wifi_bssids(cls, v: list[str]) -> list[str]:
        cleaned: list[str] = []
        for bssid in v:
            normalized = bssid.strip().upper()
            if not BSSID_REGEX.match(normalized):
                raise ValueError(
                    f"Invalid BSSID format '{bssid}'. Expected standard MAC format XX:XX:XX:XX:XX:XX."
                )
            cleaned.append(normalized)
        return cleaned

    @field_validator("ip_ranges")
    @classmethod
    def validate_ip_ranges(cls, v: list[str]) -> list[str]:
        cleaned: list[str] = []
        for cidr in v:
            raw = cidr.strip()
            try:
                ipaddress.ip_network(raw, strict=False)
                cleaned.append(raw)
            except ValueError:
                raise ValueError(
                    f"Invalid IP CIDR range '{cidr}'. Expected valid IPv4 or IPv6 network string."
                )
        return cleaned


class LocationUpdateRequest(BaseModel):
    """Payload for updating an existing workplace location."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    address_line1: str | None = Field(default=None, min_length=1, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    country_code: str | None = Field(default=None)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    radius_meters: int | None = Field(default=None, ge=10, le=50000)
    timezone: str | None = Field(default=None)
    wifi_bssids: list[str] | None = Field(default=None)
    ip_ranges: list[str] | None = Field(default=None)
    is_active: bool | None = Field(default=None)

    @field_validator("country_code")
    @classmethod
    def validate_country_code(cls, v: str | None) -> str | None:
        if v is None:
            return None
        code = v.strip().upper()
        if not COUNTRY_CODE_REGEX.match(code):
            raise ValueError(
                f"Invalid country code '{v}'. Must be a 2-letter uppercase ISO 3166-1 alpha-2 code."
            )
        return code

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str | None) -> str | None:
        if v is None:
            return None
        tz = v.strip()
        if tz not in AVAILABLE_TIMEZONES:
            raise ValueError(
                f"Invalid IANA timezone '{v}'. Must be a valid identifier from the IANA Time Zone Database."
            )
        return tz

    @field_validator("wifi_bssids")
    @classmethod
    def validate_wifi_bssids(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        cleaned: list[str] = []
        for bssid in v:
            normalized = bssid.strip().upper()
            if not BSSID_REGEX.match(normalized):
                raise ValueError(f"Invalid BSSID format '{bssid}'.")
            cleaned.append(normalized)
        return cleaned

    @field_validator("ip_ranges")
    @classmethod
    def validate_ip_ranges(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        cleaned: list[str] = []
        for cidr in v:
            raw = cidr.strip()
            try:
                ipaddress.ip_network(raw, strict=False)
                cleaned.append(raw)
            except ValueError:
                raise ValueError(f"Invalid IP CIDR range '{cidr}'.")
        return cleaned


class LocationResponse(BaseModel):
    """Workplace location response DTO."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    code: str
    address_line1: str
    address_line2: str | None
    city: str
    state: str | None
    postal_code: str | None
    country_code: str
    latitude: Decimal
    longitude: Decimal
    radius_meters: int
    timezone: str
    wifi_bssids: list[str]
    ip_ranges: list[str]
    is_active: bool
    employee_count: int = 0
    created_at: datetime
    updated_at: datetime


class LocationListResponse(BaseModel):
    """Paginated list of workplace locations."""

    items: list[LocationResponse]
    total: int
    limit: int
    offset: int


class GeofenceVerifyRequest(BaseModel):
    """Request payload to test coordinate proximity against a workplace geofence."""

    location_id: uuid.UUID = Field(..., description="Target workplace location ID")
    latitude: Decimal = Field(
        ..., ge=-90, le=90, description="Reported device latitude in decimal degrees"
    )
    longitude: Decimal = Field(
        ..., ge=-180, le=180, description="Reported device longitude in decimal degrees"
    )


class GeofenceVerifyResponse(BaseModel):
    """Result of spatial geofence calculation."""

    location_id: uuid.UUID
    location_name: str
    location_code: str
    radius_meters: int
    reported_latitude: Decimal
    reported_longitude: Decimal
    distance_meters: float
    within_geofence: bool
    threat_boundary_notice: str = (
        "ST_DWithin verifies mathematical proximity of reported coordinates to the geofence perimeter. "
        "It does not authenticate hardware GPS integrity, mock location provider spoofing, or device presence. "
        "Anti-spoofing flags and biometric liveness are enforced in Phase 7 Fraud Shield."
    )


class EmployeeWorkplaceAssignRequest(BaseModel):
    """Payload to assign a workplace location to an employee."""

    location_id: uuid.UUID = Field(..., description="Target workplace location UUID")
    is_primary: bool = Field(
        default=False, description="Whether this workplace is the employee's primary location"
    )
    effective_from: date = Field(
        default_factory=date.today, description="Assignment start date (inclusive)"
    )
    effective_to: date | None = Field(
        default=None, description="Assignment end date (inclusive, optional for ongoing)"
    )

    @model_validator(mode="after")
    def validate_date_range(self) -> "EmployeeWorkplaceAssignRequest":
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be greater than or equal to effective_from")
        return self


class EmployeeWorkplaceUpdateRequest(BaseModel):
    """Payload to update an existing workplace assignment."""

    is_primary: bool | None = Field(default=None, description="Updated primary status")
    effective_from: date | None = Field(default=None, description="Updated start date")
    effective_to: date | None = Field(
        default=None, description="Updated end date (null for ongoing)"
    )

    @model_validator(mode="after")
    def validate_date_range(self) -> "EmployeeWorkplaceUpdateRequest":
        if (
            self.effective_from is not None
            and self.effective_to is not None
            and self.effective_to < self.effective_from
        ):
            raise ValueError("effective_to must be greater than or equal to effective_from")
        return self


class EmployeeWorkplaceResponse(BaseModel):
    """Workplace assignment details for an employee."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    location_id: uuid.UUID
    location_name: str
    location_code: str
    location_address: str
    location_city: str
    location_country_code: str
    location_is_active: bool
    is_primary: bool
    effective_from: date
    effective_to: date | None
    is_current: bool
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    radius_meters: int | None = None
    created_at: datetime


class EmployeeWorkplaceListResponse(BaseModel):
    """List of workplace assignments for an employee."""

    items: list[EmployeeWorkplaceResponse]
    total: int
    page: int
    page_size: int


class LocationEmployeeItem(BaseModel):
    """Employee record assigned to a workplace location."""

    model_config = ConfigDict(from_attributes=True)

    assignment_id: uuid.UUID
    employee_id: uuid.UUID
    employee_code: str
    employee_name: str
    work_email: str
    department_id: uuid.UUID | None = None
    department_name: str | None = None
    designation_id: uuid.UUID | None = None
    designation_title: str | None = None
    is_primary: bool
    effective_from: date
    effective_to: date | None
    is_current: bool


class LocationEmployeeListResponse(BaseModel):
    """Paginated list of employees assigned to a workplace location."""

    items: list[LocationEmployeeItem]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Workplace Wi-Fi Access Point DTOs (Phase 6 Milestone 6.4.A)
# ---------------------------------------------------------------------------


class WorkplaceWifiAccessPointCreateRequest(BaseModel):
    """Payload to register an authorized Wi-Fi Access Point for a workplace."""

    friendly_name: str = Field(..., min_length=1, max_length=100, description="Friendly hardware/zone name")
    bssid: str = Field(..., description="Access point BSSID / MAC address (XX:XX:XX:XX:XX:XX)")
    ssid: str | None = Field(default=None, max_length=64, description="Optional network SSID for diagnostic display")
    is_active: bool = Field(default=True, description="Whether this AP is active for attendance matching")
    effective_from: date = Field(default_factory=date.today, description="Date from which this AP is effective")
    effective_to: date | None = Field(default=None, description="Optional expiry date")

    @field_validator("bssid")
    @classmethod
    def validate_bssid(cls, v: str) -> str:
        clean = v.strip().upper().replace("-", ":")
        if not BSSID_REGEX.match(clean):
            raise ValueError(
                f"Invalid BSSID format '{v}'. Expected standard MAC format XX:XX:XX:XX:XX:XX."
            )
        return clean

    @model_validator(mode="after")
    def validate_dates(self) -> "WorkplaceWifiAccessPointCreateRequest":
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to cannot be earlier than effective_from.")
        return self


class WorkplaceWifiAccessPointUpdateRequest(BaseModel):
    """Payload to update an authorized Wi-Fi Access Point."""

    friendly_name: str | None = Field(default=None, min_length=1, max_length=100)
    ssid: str | None = Field(default=None, max_length=64)
    is_active: bool | None = Field(default=None)
    effective_from: date | None = Field(default=None)
    effective_to: date | None = Field(default=None)

    @model_validator(mode="after")
    def validate_dates(self) -> "WorkplaceWifiAccessPointUpdateRequest":
        if self.effective_from is not None and self.effective_to is not None:
            if self.effective_to < self.effective_from:
                raise ValueError("effective_to cannot be earlier than effective_from.")
        return self


class WorkplaceWifiAccessPointResponse(BaseModel):
    """Response DTO for an authorized Wi-Fi Access Point."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    location_id: uuid.UUID
    friendly_name: str
    bssid: str
    ssid: str | None = None
    is_active: bool
    effective_from: date
    effective_to: date | None = None
    created_by_user_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class WorkplaceWifiAccessPointListResponse(BaseModel):
    """List of authorized Wi-Fi Access Points for a workplace."""

    items: list[WorkplaceWifiAccessPointResponse]
    total: int


