import re
import uuid
from datetime import date, datetime, time
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _validate_shift_timing(
    start_time: time,
    end_time: time,
    is_overnight: bool,
    half_day: int,
    full_day: int,
    weekly_off_days: list[int],
) -> None:
    """Validates shift timings and threshold consistency."""
    if full_day < half_day:
        raise ValueError(
            "full_day_threshold_minutes must be greater than or equal to half_day_threshold_minutes."
        )

    for day in weekly_off_days:
        if day < 0 or day > 6:
            raise ValueError(
                f"Invalid weekly off day {day}. Must be between 0 (Sunday) and 6 (Saturday)."
            )
    if len(weekly_off_days) != len(set(weekly_off_days)):
        raise ValueError("weekly_off_days contains duplicate days.")

    if not is_overnight and start_time >= end_time:
        raise ValueError(
            "For standard day shifts (is_overnight=False), start_time must be strictly earlier than end_time. "
            "If the shift crosses midnight, set is_overnight=True."
        )


class ShiftVersionCreateRequest(BaseModel):
    """Payload to create a new immutable version of a shift template."""

    version_effective_from: date = Field(..., description="Calendar date this version takes effect")
    start_time: time = Field(..., description="Local scheduled start time (HH:MM or HH:MM:SS)")
    end_time: time = Field(..., description="Local scheduled end time (HH:MM or HH:MM:SS)")
    grace_period_minutes: int = Field(
        default=15, ge=0, le=180, description="Grace period before arrival is late"
    )
    early_exit_grace_minutes: int = Field(
        default=15, ge=0, le=180, description="Grace period before exit is early"
    )
    early_arrival_allowance_minutes: int = Field(
        default=120, ge=0, le=480, description="Shift window opening allowance before start"
    )
    late_departure_allowance_minutes: int = Field(
        default=180, ge=0, le=480, description="Shift window closing allowance after end"
    )
    half_day_threshold_minutes: int = Field(
        default=240, gt=0, le=1440, description="Minimum net minutes for half-day"
    )
    full_day_threshold_minutes: int = Field(
        default=480, gt=0, le=1440, description="Minimum net minutes for full-day"
    )
    break_duration_minutes: int = Field(
        default=60, ge=0, le=360, description="Default break allowance in minutes"
    )
    is_overnight: bool = Field(default=False, description="True if shift spans across midnight")
    is_flexible: bool = Field(default=False, description="True if core hours are flexible")
    weekly_off_days: list[int] = Field(
        default=[6, 0], description="List of rest days: 0=Sunday, 6=Saturday"
    )

    @model_validator(mode="after")
    def validate_rules(self) -> "ShiftVersionCreateRequest":
        _validate_shift_timing(
            self.start_time,
            self.end_time,
            self.is_overnight,
            self.half_day_threshold_minutes,
            self.full_day_threshold_minutes,
            self.weekly_off_days,
        )
        return self


class ShiftVersionResponse(BaseModel):
    """Response DTO for an immutable shift version."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    shift_template_id: uuid.UUID
    version_number: int
    version_effective_from: date
    start_time: time
    end_time: time
    grace_period_minutes: int
    early_exit_grace_minutes: int
    early_arrival_allowance_minutes: int
    late_departure_allowance_minutes: int
    half_day_threshold_minutes: int
    full_day_threshold_minutes: int
    break_duration_minutes: int
    is_overnight: bool
    is_flexible: bool
    weekly_off_days: list[int]
    created_by_user_id: uuid.UUID | None
    created_at: datetime


class ShiftTemplateCreateRequest(BaseModel):
    """Payload to create a shift template along with its initial Version 1."""

    name: str = Field(..., min_length=2, max_length=100, description="Human-readable shift name")
    code: str = Field(
        ..., min_length=2, max_length=50, description="Unique alphanumeric company code"
    )
    description: str | None = Field(default=None, max_length=500)

    # Initial Version Parameters
    effective_from: date | None = Field(
        default=None, description="Effective date for initial version (defaults to today)"
    )
    start_time: time = Field(..., description="Scheduled start time")
    end_time: time = Field(..., description="Scheduled end time")
    grace_period_minutes: int = Field(default=15, ge=0, le=180)
    early_exit_grace_minutes: int = Field(default=15, ge=0, le=180)
    early_arrival_allowance_minutes: int = Field(default=120, ge=0, le=480)
    late_departure_allowance_minutes: int = Field(default=180, ge=0, le=480)
    half_day_threshold_minutes: int = Field(default=240, gt=0, le=1440)
    full_day_threshold_minutes: int = Field(default=480, gt=0, le=1440)
    break_duration_minutes: int = Field(default=60, ge=0, le=360)
    is_overnight: bool = Field(default=False)
    is_flexible: bool = Field(default=False)
    weekly_off_days: list[int] = Field(default=[6, 0])

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        clean = v.strip().upper()
        if not re.match(r"^[A-Z0-9_-]+$", clean):
            raise ValueError(
                "Shift code must contain only alphanumeric characters, dashes, or underscores."
            )
        return clean

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Shift name cannot be empty or whitespace.")
        return clean

    @model_validator(mode="after")
    def validate_rules(self) -> "ShiftTemplateCreateRequest":
        _validate_shift_timing(
            self.start_time,
            self.end_time,
            self.is_overnight,
            self.half_day_threshold_minutes,
            self.full_day_threshold_minutes,
            self.weekly_off_days,
        )
        return self


class ShiftTemplateUpdateRequest(BaseModel):
    """Payload to update shift template metadata (name, description, active status)."""

    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        if v is not None:
            clean = v.strip()
            if not clean:
                raise ValueError("Shift name cannot be whitespace.")
            return clean
        return None


class ShiftTemplateResponse(BaseModel):
    """Response DTO for shift template summary."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    current_version: ShiftVersionResponse | None = None


class ShiftTemplateDetailResponse(ShiftTemplateResponse):
    """Response DTO for shift template with complete version history."""

    versions: list[ShiftVersionResponse] = Field(default_factory=list)


class ShiftTemplateListResponse(BaseModel):
    """Paginated list response for shift templates."""

    items: list[ShiftTemplateResponse]
    total: int
    next_cursor: str | None = None


class ShiftAssignmentCreateRequest(BaseModel):
    """Payload to assign a shift template to an employee."""

    employee_id: uuid.UUID = Field(..., description="Target employee UUID")
    shift_template_id: uuid.UUID = Field(..., description="Target shift template UUID")
    effective_from: date = Field(default_factory=date.today, description="Assignment start date")
    effective_to: date | None = Field(default=None, description="Optional assignment end date")

    @model_validator(mode="after")
    def validate_date_range(self) -> "ShiftAssignmentCreateRequest":
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be greater than or equal to effective_from.")
        return self


class ShiftAssignmentUpdateRequest(BaseModel):
    """Payload to update an assignment's effective_to date without deleting history."""

    effective_to: date | None = Field(
        ..., description="Updated assignment end date (or null for open-ended)"
    )


class ShiftAssignmentEndRequest(BaseModel):
    """Payload to terminate an active assignment as of a given calendar date."""

    end_date: date = Field(
        default_factory=date.today, description="Termination date for assignment"
    )


class ShiftAssignmentResponse(BaseModel):
    """Response DTO for an employee shift assignment."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    shift_template_id: uuid.UUID
    shift_name: str
    shift_code: str
    effective_from: date
    effective_to: date | None
    created_at: datetime
    updated_at: datetime


class ShiftAssignmentListResponse(BaseModel):
    """Paginated list response for employee shift assignments."""

    items: list[ShiftAssignmentResponse]
    total: int
    next_cursor: str | None = None


# ==============================================================================
# Milestone 2: Punch & Attendance Event Ledger Schemas
# ==============================================================================


class PunchRequest(BaseModel):
    """Payload to record an attendance punch (check-in, check-out, break start, break end)."""

    event_type: Literal["CHECK_IN", "CHECK_OUT", "BREAK_START", "BREAK_END"] = Field(
        ..., description="Attendance event action"
    )
    idempotency_key: str = Field(
        ...,
        min_length=8,
        max_length=64,
        description="Client-generated unique punch key (UUID or client ID)",
    )
    employee_id: uuid.UUID | None = Field(
        default=None,
        description="Target employee UUID (required if punching on behalf of another employee)",
    )
    device_reported_at: datetime | None = Field(
        default=None,
        description="Optional client device local capture timestamp",
    )
    location_id: uuid.UUID | None = Field(
        default=None,
        description="Workplace location identifier where punch occurred",
    )
    latitude: Decimal | None = Field(
        default=None,
        ge=-90,
        le=90,
        description="GPS latitude coordinate",
    )
    longitude: Decimal | None = Field(
        default=None,
        ge=-180,
        le=180,
        description="GPS longitude coordinate",
    )
    accuracy_meters: Decimal | None = Field(
        default=None,
        ge=0,
        description="GPS radius accuracy in meters",
    )
    device_id: str | None = Field(
        default=None,
        max_length=128,
        description="Hardware or browser identifier",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary client metadata (browser user-agent, network info)",
    )

    @field_validator("idempotency_key")
    @classmethod
    def validate_idempotency_key(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("idempotency_key cannot be empty or whitespace.")
        return clean


class AttendanceEventResponse(BaseModel):
    """Response DTO for an immutable attendance event in the ledger."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    employee_id: uuid.UUID
    event_type: str
    event_category: str
    supersedes_event_id: uuid.UUID | None = None
    correction_reason: str | None = None
    server_received_at: datetime
    device_reported_at: datetime | None = None
    effective_at: datetime
    clock_drift_seconds: Decimal | None = None
    source: str
    device_id: str | None = None
    timestamp_verification_status: str
    review_status: str
    idempotency_key: str
    location_id: uuid.UUID | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    accuracy_meters: Decimal | None = None
    actor_user_id: uuid.UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_json")
    created_at: datetime


class PunchResponse(BaseModel):
    """Response DTO returned upon recording punch(es)."""

    event: AttendanceEventResponse
    additional_events: list[AttendanceEventResponse] = Field(default_factory=list)
    idempotent_replay: bool = False


class AttendanceEventListResponse(BaseModel):
    """Paginated list response for attendance events."""

    items: list[AttendanceEventResponse]
    total: int
    next_cursor: str | None = None


# ==============================================================================
# Milestone 3: Derived Attendance Days & Recalculation Schemas
# ==============================================================================


class AttendanceDayResponse(BaseModel):
    """Response DTO for a derived daily attendance projection record."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    employee_id: uuid.UUID
    attendance_date: date
    shift_template_id: uuid.UUID | None = None
    shift_version_id: uuid.UUID | None = None
    first_check_in: datetime | None = None
    last_check_out: datetime | None = None
    total_working_minutes: int
    total_break_minutes: int
    net_working_minutes: int
    actual_late_minutes: int
    late_arrival_minutes: int
    actual_early_minutes: int
    early_departure_minutes: int
    overtime_minutes: int = 0
    status: str
    calculation_status: str
    calculation_version: int
    is_incomplete: bool
    missing_punch: bool
    source_event_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_json")
    last_calculated_at: datetime
    created_at: datetime
    updated_at: datetime


class AttendanceDayListResponse(BaseModel):
    """Paginated list response for attendance day records."""

    items: list[AttendanceDayResponse]
    total: int
    next_cursor: str | None = None


class AttendanceRecalculateRequest(BaseModel):
    """Payload to trigger attendance day recalculation."""

    employee_id: uuid.UUID = Field(..., description="Target employee UUID to recalculate")
    attendance_date: date = Field(..., description="Target attendance calendar date")


# ==============================================================================
# Milestone 4: Attendance Correction Engine, Audit & Reconciliation Schemas
# ==============================================================================


class AttendanceCorrectionType(StrEnum):
    """Supported administrative attendance correction actions."""

    CORRECTION_INSERT = "CORRECTION_INSERT"
    CORRECTION_SUPERSEDE = "CORRECTION_SUPERSEDE"
    CORRECTION_VOID = "CORRECTION_VOID"


class AttendanceCorrectionCreateRequest(BaseModel):
    """Payload to submit an explicit attendance correction."""

    employee_id: uuid.UUID = Field(..., description="Target employee UUID")
    correction_type: AttendanceCorrectionType = Field(
        ..., description="Correction action type (INSERT, SUPERSEDE, VOID)"
    )
    event_type: str = Field(
        default="CHECK_IN",
        description="Event punch type ('CHECK_IN', 'CHECK_OUT', 'BREAK_START', 'BREAK_END')",
    )
    effective_at: datetime | None = Field(
        default=None,
        description="Effective punch timestamp in ISO format (mandatory for INSERT and SUPERSEDE)",
    )
    supersedes_event_id: uuid.UUID | None = Field(
        default=None,
        description="UUID of original attendance event being superseded or voided (mandatory for SUPERSEDE and VOID, must be None for INSERT)",
    )
    correction_reason: str = Field(
        ...,
        description="Mandatory audit reason explaining the administrative correction (minimum 5 non-whitespace characters)",
    )
    idempotency_key: str = Field(
        ...,
        min_length=8,
        max_length=64,
        description="Client-generated unique key ensuring idempotent retry semantics",
    )
    location_id: uuid.UUID | None = Field(
        default=None, description="Optional workplace location UUID"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary audit or client metadata"
    )

    @field_validator("correction_reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        clean = (v or "").strip()
        if len(clean) < 5:
            raise ValueError("Correction reason must contain at least 5 non-whitespace characters.")
        return clean

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        valid_types = {"CHECK_IN", "CHECK_OUT", "BREAK_START", "BREAK_END"}
        if v not in valid_types:
            raise ValueError(f"Invalid event_type '{v}'. Must be one of {valid_types}.")
        return v

    @model_validator(mode="after")
    def validate_correction_constraints(self) -> "AttendanceCorrectionCreateRequest":
        if self.correction_type == AttendanceCorrectionType.CORRECTION_INSERT:
            if self.supersedes_event_id is not None:
                raise ValueError("CORRECTION_INSERT must not specify supersedes_event_id.")
            if self.effective_at is None:
                raise ValueError("CORRECTION_INSERT requires effective_at timestamp.")

        elif self.correction_type == AttendanceCorrectionType.CORRECTION_SUPERSEDE:
            if self.supersedes_event_id is None:
                raise ValueError("CORRECTION_SUPERSEDE requires supersedes_event_id.")
            if self.effective_at is None:
                raise ValueError("CORRECTION_SUPERSEDE requires effective_at timestamp.")

        elif self.correction_type == AttendanceCorrectionType.CORRECTION_VOID:
            if self.supersedes_event_id is None:
                raise ValueError("CORRECTION_VOID requires supersedes_event_id.")

        return self


class AttendanceCorrectionResponse(BaseModel):
    """Response DTO for an applied attendance correction."""

    correction_event: AttendanceEventResponse = Field(
        ..., description="The newly created immutable correction event in the ledger"
    )
    affected_attendance_dates: list[date] = Field(
        ..., description="Calendar attendance dates affected by this correction"
    )
    recalculated_days: list[AttendanceDayResponse] = Field(
        ..., description="Recalculated daily attendance projections"
    )
    idempotent_replay: bool = Field(
        default=False, description="True if this response was replayed from a previous execution"
    )


class AttendanceEventAuditResponse(BaseModel):
    """Detailed audit representation of an attendance event in the ledger."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    employee_id: uuid.UUID
    event_type: str
    event_category: str
    effective_at: datetime
    server_received_at: datetime
    supersedes_event_id: uuid.UUID | None = None
    correction_reason: str | None = None
    actor_user_id: uuid.UUID | None = None
    source: str
    review_status: str
    timestamp_verification_status: str
    is_active: bool = True
    superseded_by_event_id: uuid.UUID | None = None
    voided_by_event_id: uuid.UUID | None = None
    created_at: datetime


class AttendanceEventAuditListResponse(BaseModel):
    """List response for event audit trail records."""

    items: list[AttendanceEventAuditResponse]
    total: int


class AttendanceCorrectionListResponse(BaseModel):
    """List response for administrative corrections."""

    items: list[AttendanceEventResponse]
    total: int
    next_cursor: str | None = None


class ReconciliationRequest(BaseModel):
    """Payload to trigger background or administrative attendance reconciliation."""

    target_date: date | None = Field(
        default=None, description="Specific calendar date to reconcile (defaults to yesterday)"
    )
    start_date: date | None = Field(default=None, description="Start date for range reconciliation")
    end_date: date | None = Field(default=None, description="End date for range reconciliation")
    employee_id: uuid.UUID | None = Field(
        default=None, description="Optional employee UUID to reconcile only a single employee"
    )
    batch_size: int = Field(default=100, ge=1, le=500, description="Batch processing chunk size")


class ReconciliationResponse(BaseModel):
    """Result summary of an executed attendance reconciliation run."""

    status: str = Field(..., description="'COMPLETED' or 'FAILED'")
    tenant_id: uuid.UUID
    target_dates: list[date]
    total_candidates: int
    recalculated_count: int
    failed_count: int
    errors: list[str] = Field(default_factory=list)
