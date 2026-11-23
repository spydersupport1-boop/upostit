"""Pydantic v2 schemas for Phase 11.3 Downward Delta Sync Protocol.

Defines payloads for server-to-mobile synchronization of reference data:
- Employee profile & status
- Shifts & schedules
- Workplace locations & geofences
- Holidays & weekly offs
- Leave types, balances & requests
- Attendance policy
- Reporting hierarchy & direct reports
- Deletions / tombstones
"""

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SyncType(StrEnum):
    """Synchronization mode."""

    FULL = "FULL"
    DELTA = "DELTA"


class SyncEmployeePayload(BaseModel):
    """Employee profile and operational employment status."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    employee_id: str
    first_name: str
    last_name: str
    work_email: str
    phone_number: str | None = None
    department_id: uuid.UUID | None = None
    designation_id: uuid.UUID | None = None
    reporting_manager_id: uuid.UUID | None = None
    employment_type: str = "full_time"
    status: str = "active"  # active, inactive, terminated, on_leave
    work_location: str | None = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SyncShiftPayload(BaseModel):
    """Assigned shift schedule and operational parameters."""

    id: uuid.UUID  # ShiftAssignment ID
    shift_template_id: uuid.UUID
    name: str
    code: str
    start_time: str
    end_time: str
    grace_period_minutes: int = 15
    early_exit_grace_minutes: int = 15
    half_day_threshold_minutes: int = 240
    full_day_threshold_minutes: int = 480
    break_duration_minutes: int = 60
    is_overnight: bool = False
    is_flexible: bool = False
    weekly_off_days: list[int] = Field(default_factory=lambda: [6, 0])
    effective_from: date
    effective_to: date | None = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SyncWorkplacePayload(BaseModel):
    """Workplace location, PostGIS geofence and WiFi parameters."""

    id: uuid.UUID  # Location ID
    name: str
    code: str
    address_line1: str
    city: str
    latitude: float
    longitude: float
    radius_meters: int = 100
    timezone: str = "UTC"
    wifi_bssids: list[str] = Field(default_factory=list)
    is_active: bool = True
    is_assigned: bool = True
    is_primary: bool = False
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SyncHolidayPayload(BaseModel):
    """Official organization holiday date."""

    id: uuid.UUID
    calendar_id: uuid.UUID
    holiday_date: date
    name: str
    holiday_type: str = "PUBLIC"  # PUBLIC, COMPANY, OPTIONAL
    is_optional: bool = False
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SyncLeaveTypePayload(BaseModel):
    """Available leave category definition."""

    id: uuid.UUID
    code: str
    name: str
    is_paid: bool = True
    allow_half_day: bool = True
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SyncLeaveBalancePayload(BaseModel):
    """Current employee leave quota and available balance."""

    id: uuid.UUID
    leave_type_id: uuid.UUID
    year: int
    annual_allocation: float
    used: float
    available_balance: float
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SyncLeaveRequestPayload(BaseModel):
    """Recent employee leave application and decision state."""

    id: uuid.UUID
    leave_type_id: uuid.UUID
    start_date: date
    end_date: date
    is_half_day: bool = False
    total_days: float
    reason: str
    status: str  # PENDING_APPROVAL, APPROVED, REJECTED, CANCELLED
    decided_at: datetime | None = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SyncAttendancePolicyPayload(BaseModel):
    """Active company attendance policy and verification modes."""

    id: uuid.UUID
    version: int
    is_active: bool = True
    default_mode: str = "MANUAL"
    allowed_methods: list[str] = Field(default_factory=lambda: ["MANUAL"])
    required_methods: list[str] = Field(default_factory=lambda: ["MANUAL"])
    combination_rule: str = "OR"
    gps_config: dict[str, Any] = Field(default_factory=dict)
    wifi_config: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SyncDirectReportPayload(BaseModel):
    """Summary of a direct report employee for supervisor offline view."""

    id: uuid.UUID
    employee_id: str
    first_name: str
    last_name: str
    work_email: str
    department_name: str | None = None
    status: str = "active"
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SyncReportingHierarchyPayload(BaseModel):
    """Manager relationship and direct reports."""

    manager_id: uuid.UUID | None = None
    manager_name: str | None = None
    manager_email: str | None = None
    direct_reports: list[SyncDirectReportPayload] = Field(default_factory=list)


class SyncTombstonePayload(BaseModel):
    """Tombstone record indicating entity deletion or deactivation."""

    entity_type: str  # shift, workplace, holiday, leave_request, leave_balance
    entity_id: uuid.UUID
    deleted_at: datetime


class SyncDeltaResponse(BaseModel):
    """Server-to-mobile downward delta synchronization response."""

    sync_type: SyncType
    server_time: datetime
    next_cursor: str
    has_more: bool = False
    employee: SyncEmployeePayload | None = None
    shifts: list[SyncShiftPayload] = Field(default_factory=list)
    workplaces: list[SyncWorkplacePayload] = Field(default_factory=list)
    holidays: list[SyncHolidayPayload] = Field(default_factory=list)
    leave_types: list[SyncLeaveTypePayload] = Field(default_factory=list)
    leave_balances: list[SyncLeaveBalancePayload] = Field(default_factory=list)
    leave_requests: list[SyncLeaveRequestPayload] = Field(default_factory=list)
    attendance_policy: SyncAttendancePolicyPayload | None = None
    reporting_hierarchy: SyncReportingHierarchyPayload | None = None
    tombstones: list[SyncTombstonePayload] = Field(default_factory=list)
