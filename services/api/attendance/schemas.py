import re
import uuid
from datetime import UTC, date, datetime, time
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

BSSID_REGEX = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")


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
    start_time: time | None = None
    end_time: time | None = None
    grace_period_minutes: int = 15
    break_duration_minutes: int = 0
    is_overnight: bool = False
    is_flexible: bool = False
    weekly_off_days: list[int] = Field(default_factory=list)


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
    wifi_bssid: str | None = Field(
        default=None,
        description="Connected access point BSSID (MAC address in XX:XX:XX:XX:XX:XX format)",
    )
    wifi_ssid: str | None = Field(
        default=None,
        max_length=64,
        description="Connected access point SSID (diagnostic/display only)",
    )
    wifi_signal_status: Literal["AVAILABLE", "UNAVAILABLE", "UNSUPPORTED", "PERMISSION_DENIED"] = (
        Field(
            default="AVAILABLE",
            description="Device Wi-Fi telemetry capability status",
        )
    )
    device_id: str | None = Field(
        default=None,
        max_length=128,
        description="Hardware or browser identifier",
    )
    is_mock_location: bool | None = Field(
        default=None,
        description="Client-reported mock location flag (e.g. from Android mock provider)",
    )
    location_captured_at: datetime | None = Field(
        default=None,
        description="Hardware timestamp when the GPS fix was obtained",
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

    @field_validator("wifi_bssid")
    @classmethod
    def validate_wifi_bssid(cls, v: str | None) -> str | None:
        if v is None:
            return None
        clean = v.strip().upper().replace("-", ":")
        if not BSSID_REGEX.match(clean):
            raise ValueError(f"Invalid Wi-Fi BSSID format '{v}'. Expected XX:XX:XX:XX:XX:XX.")
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
    applied_policy_version: int | None = None
    wifi_bssid: str | None = None
    wifi_ssid: str | None = None
    is_mock_location: bool | None = None
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


# ==============================================================================
# Milestone 6.3.A: Company Attendance Policy & GPS Geofence Verification Schemas
# ==============================================================================


class AttendancePolicyMethod(StrEnum):
    """Supported attendance verification methods."""

    MANUAL = "MANUAL"
    GPS = "GPS"
    WIFI = "WIFI"
    BIOMETRIC = "BIOMETRIC"
    FACE_RECOGNITION = "FACE_RECOGNITION"


class AttendancePolicyMode(StrEnum):
    """Configurable operational modes for tenant attendance policies."""

    MANUAL = "MANUAL"
    GPS_ONLY = "GPS_ONLY"
    WIFI_ONLY = "WIFI_ONLY"
    BIOMETRIC_ONLY = "BIOMETRIC_ONLY"
    FACE_RECOGNITION = "FACE_RECOGNITION"
    COMBINED = "COMBINED"


class AttendanceCombinationRule(StrEnum):
    """Rule governing multi-method evaluation."""

    AND = "AND"
    OR = "OR"
    PRIMARY_WITH_FALLBACK = "PRIMARY_WITH_FALLBACK"


class OutOfGeofenceAction(StrEnum):
    """Action taken when punch coordinates fall outside workplace geofence."""

    REJECT = "REJECT"
    FLAG_PENDING_REVIEW = "FLAG_PENDING_REVIEW"


class TenantAttendancePolicyResponse(BaseModel):
    """Response DTO for full company attendance policy."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    version: int
    is_active: bool
    default_mode: str
    allowed_methods: list[str]
    required_methods: list[str]
    combination_rule: str
    fallback_policy: dict[str, Any] = Field(default_factory=dict)
    gps_config: dict[str, Any] = Field(default_factory=dict)
    wifi_config: dict[str, Any] = Field(default_factory=dict)
    biometric_config: dict[str, Any] = Field(default_factory=dict)
    face_config: dict[str, Any] = Field(default_factory=dict)
    created_by_user_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class TenantAttendancePolicyCreateRequest(BaseModel):
    """Payload to create a new immutable version of the company attendance policy."""

    default_mode: AttendancePolicyMode = AttendancePolicyMode.MANUAL
    allowed_methods: list[AttendancePolicyMethod] = Field(
        default_factory=lambda: [AttendancePolicyMethod.MANUAL]
    )
    required_methods: list[AttendancePolicyMethod] = Field(
        default_factory=lambda: [AttendancePolicyMethod.MANUAL]
    )
    combination_rule: AttendanceCombinationRule = AttendanceCombinationRule.OR
    fallback_policy: dict[str, Any] = Field(default_factory=dict)
    gps_config: dict[str, Any] = Field(
        default_factory=lambda: {
            "max_accuracy_meters": 100,
            "max_location_age_seconds": 30,
            "enforce_assigned_workplace": True,
            "out_of_geofence_action": "REJECT",
        }
    )
    wifi_config: dict[str, Any] = Field(default_factory=dict)
    biometric_config: dict[str, Any] = Field(default_factory=dict)
    face_config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_policy_rules(self) -> "TenantAttendancePolicyCreateRequest":
        # Ensure required methods are included in allowed methods
        for req in self.required_methods:
            if req not in self.allowed_methods:
                raise ValueError(
                    f"Required verification method '{req}' must also be included in allowed_methods."
                )

        # GPS validation constraints
        if (
            AttendancePolicyMethod.GPS in self.required_methods
            or self.default_mode == AttendancePolicyMode.GPS_ONLY
        ):
            max_acc = self.gps_config.get("max_accuracy_meters", 100)
            if not isinstance(max_acc, (int, float)) or max_acc <= 0 or max_acc > 1000:
                raise ValueError(
                    "gps_config.max_accuracy_meters must be a positive number up to 1000m."
                )
            max_age = self.gps_config.get("max_location_age_seconds", 30)
            if not isinstance(max_age, int) or max_age < 5 or max_age > 300:
                raise ValueError(
                    "gps_config.max_location_age_seconds must be an integer between 5s and 300s."
                )
            action = self.gps_config.get("out_of_geofence_action", "REJECT")
            if action not in ("REJECT", "FLAG_PENDING_REVIEW"):
                raise ValueError(
                    "gps_config.out_of_geofence_action must be 'REJECT' or 'FLAG_PENDING_REVIEW'."
                )

        # Wi-Fi validation constraints
        if (
            AttendancePolicyMethod.WIFI in self.required_methods
            or self.default_mode == AttendancePolicyMode.WIFI_ONLY
        ):
            max_wifi_age = self.wifi_config.get("max_wifi_age_seconds", 30)
            if not isinstance(max_wifi_age, int) or max_wifi_age < 5 or max_wifi_age > 300:
                raise ValueError(
                    "wifi_config.max_wifi_age_seconds must be an integer between 5s and 300s."
                )
            fallback_action = self.wifi_config.get("fallback_action", "REJECT")
            if fallback_action not in (
                "REJECT",
                "GPS_FALLBACK",
                "SUPERVISOR_REVIEW",
                "MANUAL_FALLBACK",
            ):
                raise ValueError(
                    "wifi_config.fallback_action must be one of: 'REJECT', 'GPS_FALLBACK', 'SUPERVISOR_REVIEW', 'MANUAL_FALLBACK'."
                )
            mismatch_action = self.wifi_config.get("mismatch_action", "REJECT")
            if mismatch_action not in ("REJECT", "FLAG_PENDING_REVIEW"):
                raise ValueError(
                    "wifi_config.mismatch_action must be 'REJECT' or 'FLAG_PENDING_REVIEW'."
                )

        return self


class EmployeeAttendancePolicyResponse(BaseModel):
    """Employee-safe minimal attendance policy DTO for mobile and web punch."""

    tenant_id: uuid.UUID
    version: int
    default_mode: str
    allowed_methods: list[str]
    required_methods: list[str]
    combination_rule: str
    requires_gps: bool
    requires_wifi: bool = False
    requires_biometric: bool = False
    requires_face: bool = False
    max_accuracy_meters: int = 100
    max_location_age_seconds: int = 30
    max_wifi_age_seconds: int = 30
    wifi_fallback_action: str = "REJECT"
    allowed_fallback_methods: list[str] = Field(default_factory=list)


class EmployeeGeofenceVerifyRequest(BaseModel):
    """Payload for employee coordinate verification against an assigned workplace."""

    location_id: uuid.UUID = Field(
        ...,
        validation_alias=AliasChoices("location_id", "workplace_id"),
        description="Target workplace location UUID",
    )
    latitude: Decimal = Field(..., ge=-90, le=90, description="Device latitude coordinate")
    longitude: Decimal = Field(..., ge=-180, le=180, description="Device longitude coordinate")
    accuracy_meters: Decimal | None = Field(
        default=None, ge=0, description="Horizontal accuracy in meters"
    )
    device_reported_at: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("device_reported_at", "recorded_at"),
        description="Coordinate capture timestamp",
    )


class EmployeeGeofenceVerifyResponse(BaseModel):
    """Result of employee workplace geofence verification."""

    location_id: uuid.UUID
    location_name: str
    location_code: str
    radius_meters: int
    reported_latitude: Decimal
    reported_longitude: Decimal
    accuracy_meters: Decimal | None = None
    distance_meters: float
    within_geofence: bool
    accuracy_acceptable: bool
    location_freshness_acceptable: bool
    freshness_acceptable: bool = True
    is_inside: bool = True
    can_punch: bool = True
    message: str = "Inside workplace geofence perimeter. Ready to punch."
    threat_boundary_notice: str = (
        "ST_DWithin verifies geometric spherical proximity against the workplace perimeter. "
        "Anti-spoofing and biometric liveness are enforced in Phase 7 Fraud Shield."
    )


# ---------------------------------------------------------------------------
# Employee Wi-Fi Verification DTOs (Phase 6 Milestone 6.4.A)
# ---------------------------------------------------------------------------


class WifiMatchStatus(StrEnum):
    """Classification of device-reported Wi-Fi verification signal state."""

    MATCHED = "MATCHED"
    MISMATCHED = "MISMATCHED"
    UNAVAILABLE = "UNAVAILABLE"
    UNSUPPORTED = "UNSUPPORTED"
    STALE = "STALE"
    UNASSIGNED_WORKPLACE = "UNASSIGNED"
    INACTIVE_WORKPLACE = "INACTIVE"


class EmployeeWifiVerifyRequest(BaseModel):
    """Payload for employee Wi-Fi verification probe against an assigned workplace."""

    location_id: uuid.UUID = Field(
        ...,
        validation_alias=AliasChoices("location_id", "workplace_id"),
        description="Target assigned workplace location UUID",
    )
    bssid: str | None = Field(
        default=None,
        description="Connected access point BSSID (MAC address in XX:XX:XX:XX:XX:XX format)",
    )
    ssid: str | None = Field(
        default=None,
        max_length=64,
        description="Connected access point SSID (display/diagnostic only)",
    )
    device_reported_at: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("device_reported_at", "recorded_at"),
        description="Timestamp when device observed the Wi-Fi connection",
    )
    signal_status: Literal["AVAILABLE", "UNAVAILABLE", "UNSUPPORTED", "PERMISSION_DENIED"] = Field(
        default="AVAILABLE",
        description="Device Wi-Fi telemetry capability status",
    )
    platform: str | None = Field(
        default=None,
        max_length=32,
        description="Client OS platform (android, ios, web)",
    )

    @field_validator("bssid")
    @classmethod
    def normalize_bssid(cls, v: str | None) -> str | None:
        if v is None:
            return None
        clean = v.strip().upper().replace("-", ":")
        if not BSSID_REGEX.match(clean):
            raise ValueError(f"Invalid BSSID format '{v}'. Expected XX:XX:XX:XX:XX:XX.")
        return clean


class EmployeeWifiVerifyResponse(BaseModel):
    """Result of employee workplace Wi-Fi verification probe."""

    location_id: uuid.UUID
    location_name: str
    location_code: str
    reported_bssid: str | None = None
    reported_ssid: str | None = None
    match_status: WifiMatchStatus
    is_verified: bool
    matched_access_point_name: str | None = None
    freshness_acceptable: bool
    applicable_fallback: str | None = None
    message: str


# ---------------------------------------------------------------------------
# Offline Conflict Resolution DTOs (Phase 8 Milestone 8.2)
# ---------------------------------------------------------------------------


class OfflineRejectedEventPayload(BaseModel):
    """Payload of the primary rejected attendance punch that triggered session quarantine."""

    model_config = ConfigDict(extra="ignore")

    local_id: str = Field(min_length=1, max_length=64, description="Client local SQLite queue ID")
    idempotency_key: str = Field(
        min_length=1, max_length=128, description="Unique client punch UUID"
    )
    event_type: str = Field(
        description="Punch action type (CHECK_IN, CHECK_OUT, BREAK_START, BREAK_END)"
    )
    device_reported_at: datetime = Field(description="Client hardware capture timestamp (UTC)")
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0, description="WGS84 Latitude")
    longitude: float | None = Field(
        default=None, ge=-180.0, le=180.0, description="WGS84 Longitude"
    )
    accuracy_meters: float | None = Field(
        default=None, ge=0.0, le=50000.0, description="Horizontal GPS accuracy"
    )
    device_id_hash: str | None = Field(
        default=None, max_length=128, description="SHA-256 hash of device identity"
    )
    device_model: str | None = Field(
        default=None, max_length=100, description="Hardware model name"
    )
    os_version: str | None = Field(
        default=None, max_length=50, description="Operating system version"
    )
    is_mock_location: bool | None = Field(
        default=False, description="Whether mock GPS provider was detected"
    )
    server_rejection_code: int | None = Field(
        default=None, description="HTTP status code received upon FIFO rejection"
    )
    server_rejection_reason: str | None = Field(
        default=None, max_length=500, description="Error detail message from backend"
    )
    location_id: uuid.UUID | None = Field(
        default=None, description="Workplace location UUID if geofenced"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional device or sensor telemetry"
    )

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        clean = v.strip().upper()
        if clean not in ("CHECK_IN", "CHECK_OUT", "BREAK_START", "BREAK_END"):
            raise ValueError(f"Invalid attendance event type: {v}")
        return clean

    @field_validator("device_reported_at")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v.astimezone(UTC)


class OfflineDependentEventPayload(BaseModel):
    """Payload of a quarantined dependent session punch."""

    model_config = ConfigDict(extra="ignore")

    local_id: str = Field(min_length=1, max_length=64, description="Client local SQLite queue ID")
    idempotency_key: str = Field(
        min_length=1, max_length=128, description="Unique client punch UUID"
    )
    event_type: str = Field(
        description="Punch action type (CHECK_IN, CHECK_OUT, BREAK_START, BREAK_END)"
    )
    device_reported_at: datetime = Field(description="Client hardware capture timestamp (UTC)")
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)
    accuracy_meters: float | None = Field(default=None, ge=0.0, le=50000.0)
    device_id_hash: str | None = Field(default=None, max_length=128)
    device_model: str | None = Field(default=None, max_length=100)
    os_version: str | None = Field(default=None, max_length=50)
    is_mock_location: bool | None = Field(default=False)
    location_id: uuid.UUID | None = Field(default=None)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        clean = v.strip().upper()
        if clean not in ("CHECK_IN", "CHECK_OUT", "BREAK_START", "BREAK_END"):
            raise ValueError(f"Invalid attendance event type: {v}")
        return clean

    @field_validator("device_reported_at")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v.astimezone(UTC)


class OfflineConflictBundleSubmitRequest(BaseModel):
    """Request payload to submit an offline sequence conflict bundle for supervisor adjudication."""

    model_config = ConfigDict(extra="ignore")

    bundle_id: str = Field(
        min_length=1,
        max_length=64,
        description="Client-generated unique bundle identifier for the conflict session",
    )
    session_id: str | None = Field(
        default=None,
        max_length=64,
        description="Shift/session correlation identifier",
    )
    employee_notes: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional employee-provided justification and context",
    )
    employee_id: uuid.UUID | None = Field(
        default=None,
        description="Optional target employee UUID (verified against caller)",
    )
    primary_rejected_event: OfflineRejectedEventPayload
    dependent_events: list[OfflineDependentEventPayload] = Field(
        default_factory=list,
        max_length=50,
        description="Quarantined dependent session punches",
    )

    @model_validator(mode="after")
    def validate_bundle_integrity(self) -> "OfflineConflictBundleSubmitRequest":
        # Check unique idempotency keys within the bundle
        seen_keys: set[str] = {self.primary_rejected_event.idempotency_key}
        for dep in self.dependent_events:
            if dep.idempotency_key in seen_keys:
                raise ValueError(
                    f"Duplicate idempotency_key '{dep.idempotency_key}' detected within conflict bundle."
                )
            seen_keys.add(dep.idempotency_key)

        # Validate chronological order: dependent events cannot precede primary rejected event
        primary_time = self.primary_rejected_event.device_reported_at
        prev_time = primary_time
        for i, dep in enumerate(self.dependent_events):
            if dep.device_reported_at < primary_time:
                raise ValueError(
                    f"Dependent event at index {i} ({dep.event_type}) timestamp "
                    f"({dep.device_reported_at.isoformat()}) precedes primary event timestamp ({primary_time.isoformat()})."
                )
            if dep.device_reported_at < prev_time:
                raise ValueError(
                    f"Dependent events must be in chronological order. Event at index {i} precedes previous dependent event."
                )
            prev_time = dep.device_reported_at

        return self


class OfflineConflictIncidentResponse(BaseModel):
    """Response returned upon conflict bundle submission."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    employee_id: uuid.UUID
    user_id: uuid.UUID
    bundle_id: str
    session_id: str | None = None
    status: str
    total_events_count: int
    rejection_summary: str | None = None
    employee_notes: str | None = None
    submitted_at: datetime
    conflict_code: str | None = None
    severity: str | None = "MEDIUM"
    classification: str | None = "NEEDS_MANAGER_REVIEW"
    employee_clarification: str | None = None
    clarification_requested_at: datetime | None = None
    clarification_submitted_at: datetime | None = None
    decision: str | None = None
    decision_reason: str | None = None
    decided_at: datetime | None = None
    resolved_correction_event_ids: list[str] = Field(default_factory=list)
    idempotent_replay: bool = False

    @field_validator("severity", mode="before")
    @classmethod
    def validate_severity_fallback(cls, v: Any) -> str:
        return str(v) if v is not None else "MEDIUM"

    @field_validator("classification", mode="before")
    @classmethod
    def validate_classification_fallback(cls, v: Any) -> str:
        return str(v) if v is not None else "NEEDS_MANAGER_REVIEW"


class EmployeeConflictIncidentSummary(BaseModel):
    """Sanitized summary of an attendance conflict incident tailored for employee mobile view."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bundle_id: str
    session_id: str | None = None
    status: str
    total_events_count: int
    primary_event_type: str
    primary_event_timestamp: datetime
    rejection_summary: str | None = None
    employee_notes: str | None = None
    submitted_at: datetime
    conflict_code: str | None = None
    severity: str | None = "MEDIUM"
    classification: str | None = "NEEDS_MANAGER_REVIEW"
    employee_clarification: str | None = None
    clarification_requested_at: datetime | None = None
    clarification_submitted_at: datetime | None = None
    decision: str | None = None
    decision_reason: str | None = None
    decided_at: datetime | None = None
    resolved_events_count: int = 0

    @field_validator("severity", mode="before")
    @classmethod
    def validate_summary_severity(cls, v: Any) -> str:
        return str(v) if v is not None else "MEDIUM"

    @field_validator("classification", mode="before")
    @classmethod
    def validate_summary_classification(cls, v: Any) -> str:
        return str(v) if v is not None else "NEEDS_MANAGER_REVIEW"


class EmployeeConflictIncidentListResponse(BaseModel):
    """Paginated list of conflict incidents for the authenticated employee."""

    items: list[EmployeeConflictIncidentSummary]
    total: int
    limit: int
    cursor: str | None = None
    has_more: bool = False


# ==============================================================================
# Phase 8 Milestone 8.3 & Phase 11.5: Multi-Device Conflict Adjudication Schemas
# ==============================================================================


class MultiDeviceConflictCode(StrEnum):
    """Machine-readable conflict codes for multi-device attendance arbitration."""

    OVERLAPPING_SESSIONS = "OVERLAPPING_SESSIONS"
    DUPLICATE_CHECK_IN = "DUPLICATE_CHECK_IN"
    UNPAIRED_CHECK_OUT = "UNPAIRED_CHECK_OUT"
    MULTIPLE_CHECK_OUT = "MULTIPLE_CHECK_OUT"
    OUT_OF_ORDER_SYNC = "OUT_OF_ORDER_SYNC"
    CONFLICTING_OFFLINE_TIMESTAMPS = "CONFLICTING_OFFLINE_TIMESTAMPS"
    POST_RECONCILIATION_ARRIVAL = "POST_RECONCILIATION_ARRIVAL"
    UNAUTHORIZED_OR_REVOKED_DEVICE = "UNAUTHORIZED_OR_REVOKED_DEVICE"
    IMPOSSIBLE_TRAVEL_TIMELINE = "IMPOSSIBLE_TRAVEL_TIMELINE"
    CONCURRENT_SYNC_RACE = "CONCURRENT_SYNC_RACE"


class ConflictSeverity(StrEnum):
    """Severity classification for attendance conflict incidents."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ConflictClassification(StrEnum):
    """Actionability classification for multi-device attendance conflicts."""

    AUTO_RESOLVABLE = "AUTO_RESOLVABLE"
    NEEDS_EMPLOYEE_CLARIFICATION = "NEEDS_EMPLOYEE_CLARIFICATION"
    NEEDS_MANAGER_REVIEW = "NEEDS_MANAGER_REVIEW"
    INVALID_UNAUTHORIZED = "INVALID_UNAUTHORIZED"


class ConflictIncidentStatus(StrEnum):
    """Lifecycle status for attendance conflict incidents."""

    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    UNRESOLVED = "UNRESOLVED"
    ESCALATED_HR = "ESCALATED_HR"
    AUTO_RESOLVED = "AUTO_RESOLVED"


class ConflictDecisionType(StrEnum):
    """Decision actions for conflict adjudication."""

    APPROVE = "APPROVE"
    REJECT = "REJECT"
    ACCEPT_SEQUENCE = "ACCEPT_SEQUENCE"
    REJECT_INVALID_EVENTS = "REJECT_INVALID_EVENTS"
    REQUEST_CLARIFICATION = "REQUEST_CLARIFICATION"
    MARK_UNRESOLVED = "MARK_UNRESOLVED"
    ESCALATE_HR = "ESCALATE_HR"


class AttendanceConflictClarificationRequest(BaseModel):
    """Payload submitted by an employee to clarify their punch timeline."""

    clarification_notes: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="Employee clarification regarding ambiguous punches",
    )

    @field_validator("clarification_notes")
    @classmethod
    def validate_notes(cls, v: str) -> str:
        clean = (v or "").strip()
        if len(clean) < 3:
            raise ValueError("Clarification notes must contain at least 3 non-whitespace characters.")
        return clean


class AttendanceConflictDecisionRequest(BaseModel):
    """Payload to adjudicate an offline attendance conflict incident."""

    action: str = Field(
        ...,
        description="Decision action (APPROVE, REJECT, ACCEPT_SEQUENCE, REJECT_INVALID_EVENTS, REQUEST_CLARIFICATION, MARK_UNRESOLVED, ESCALATE_HR)",
    )
    reason: str = Field(
        ...,
        min_length=3,
        description="Mandatory decision reason (minimum 3 non-whitespace characters)",
    )
    override_location_id: uuid.UUID | None = Field(
        default=None,
        description="Optional workplace location UUID override for approved punches",
    )

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        clean = (v or "").strip().upper()
        if clean in ("APPROVE", "APPROVED"):
            return "APPROVE"
        if clean in ("REJECT", "REJECTED"):
            return "REJECT"
        if clean in (
            "ACCEPT_SEQUENCE",
            "REJECT_INVALID_EVENTS",
            "REQUEST_CLARIFICATION",
            "MARK_UNRESOLVED",
            "ESCALATE_HR",
        ):
            return clean
        raise ValueError(
            f"Invalid decision action '{v}'. Must be one of APPROVE, REJECT, "
            "ACCEPT_SEQUENCE, REJECT_INVALID_EVENTS, REQUEST_CLARIFICATION, "
            "MARK_UNRESOLVED, ESCALATE_HR."
        )

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        clean = (v or "").strip()
        if len(clean) < 3:
            raise ValueError("Decision reason must contain at least 3 non-whitespace characters.")
        return clean


class SupervisorConflictQueueItem(BaseModel):
    """Summary item for the supervisor review queue."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    employee_code: str
    department_name: str | None = None
    bundle_id: str
    session_id: str | None = None
    status: str
    total_events_count: int
    primary_event_type: str
    primary_device_reported_at: datetime
    rejection_summary: str | None = None
    employee_notes: str | None = None
    submitted_at: datetime
    conflict_code: str | None = None
    severity: str | None = "MEDIUM"
    classification: str | None = "NEEDS_MANAGER_REVIEW"
    employee_clarification: str | None = None
    clarification_requested_at: datetime | None = None
    clarification_submitted_at: datetime | None = None
    decision: str | None = None
    decision_reason: str | None = None
    reviewer_user_id: uuid.UUID | None = None
    decided_at: datetime | None = None
    resolved_correction_event_ids: list[str] = Field(default_factory=list)

    @field_validator("severity", mode="before")
    @classmethod
    def validate_queue_severity(cls, v: Any) -> str:
        return str(v) if v is not None else "MEDIUM"

    @field_validator("classification", mode="before")
    @classmethod
    def validate_queue_classification(cls, v: Any) -> str:
        return str(v) if v is not None else "NEEDS_MANAGER_REVIEW"


class SupervisorConflictQueueListResponse(BaseModel):
    """Paginated list of conflict incidents for supervisor review."""

    items: list[SupervisorConflictQueueItem]
    total: int
    limit: int
    cursor: str | None = None
    has_more: bool = False


class ConflictIncidentEmployeeDetail(BaseModel):
    """Employee profile details associated with a conflict incident."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_code: str
    first_name: str
    last_name: str
    work_email: str
    department_name: str | None = None
    reporting_manager_id: uuid.UUID | None = None


class AttendanceConflictIncidentDetailResponse(BaseModel):
    """Detailed forensic view of an attendance conflict incident."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    bundle_id: str
    session_id: str | None = None
    status: str
    employee: ConflictIncidentEmployeeDetail
    primary_rejected_event: dict[str, Any]
    dependent_events: list[dict[str, Any]] = Field(default_factory=list)
    total_events_count: int
    rejection_summary: str | None = None
    employee_notes: str | None = None
    submitted_at: datetime
    conflict_code: str | None = None
    severity: str | None = "MEDIUM"
    classification: str | None = "NEEDS_MANAGER_REVIEW"
    employee_clarification: str | None = None
    clarification_requested_at: datetime | None = None
    clarification_submitted_at: datetime | None = None
    assigned_reviewer_id: uuid.UUID | None = None
    decision: str | None = None
    decision_reason: str | None = None
    reviewer_user_id: uuid.UUID | None = None
    decided_at: datetime | None = None
    resolved_correction_event_ids: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @field_validator("severity", mode="before")
    @classmethod
    def validate_detail_severity(cls, v: Any) -> str:
        return str(v) if v is not None else "MEDIUM"

    @field_validator("classification", mode="before")
    @classmethod
    def validate_detail_classification(cls, v: Any) -> str:
        return str(v) if v is not None else "NEEDS_MANAGER_REVIEW"


class AttendanceConflictDecisionResponse(BaseModel):
    """Response returned upon supervisor conflict adjudication."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    employee_id: uuid.UUID
    bundle_id: str
    status: str
    decision: str
    decision_reason: str
    reviewer_user_id: uuid.UUID
    decided_at: datetime
    resolved_correction_event_ids: list[str] = Field(default_factory=list)
    affected_attendance_dates: list[date] = Field(default_factory=list)
    recalculated_days_count: int = 0


# ==============================================================================
# Phase 11 Milestone 11.2: Backend Batch Synchronization Schemas
# ==============================================================================


class BatchSyncItemStatus(StrEnum):
    """Execution status for an individual offline attendance punch within a sync batch."""

    ACCEPTED = "ACCEPTED"
    DUPLICATE = "DUPLICATE"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    REJECTED = "REJECTED"
    CONFLICT = "CONFLICT"
    RETRYABLE = "RETRYABLE"


class BatchSyncPunchItem(BaseModel):
    """An individual attendance punch event queued offline on a mobile client."""

    model_config = ConfigDict(extra="ignore")

    local_id: str = Field(
        min_length=1,
        max_length=64,
        description="Client local SQLite queue item UUID or identifier",
    )
    idempotency_key: str = Field(
        min_length=1,
        max_length=128,
        description="Unique client-generated UUID v4 idempotency key",
    )
    event_type: str = Field(
        description="Punch action type (CHECK_IN, CHECK_OUT, BREAK_START, BREAK_END)"
    )
    device_reported_at: datetime = Field(
        description="Client hardware capture timestamp in UTC"
    )
    sequence_number: int | None = Field(
        default=None,
        ge=1,
        description="Client-side strictly monotonic sequence number",
    )
    session_id: str | None = Field(
        default=None,
        max_length=64,
        description="Client shift/session correlation identifier",
    )
    location_id: uuid.UUID | None = Field(
        default=None,
        description="Workplace location UUID if geofenced",
    )
    latitude: Decimal | None = Field(
        default=None,
        ge=-90,
        le=90,
        description="WGS84 latitude",
    )
    longitude: Decimal | None = Field(
        default=None,
        ge=-180,
        le=180,
        description="WGS84 longitude",
    )
    accuracy_meters: Decimal | None = Field(
        default=None,
        ge=0,
        le=50000,
        description="Horizontal GPS accuracy in meters",
    )
    wifi_bssid: str | None = Field(
        default=None,
        max_length=32,
        description="Connected access point BSSID",
    )
    wifi_ssid: str | None = Field(
        default=None,
        max_length=64,
        description="Connected access point SSID",
    )
    wifi_signal_status: Literal[
        "AVAILABLE", "UNAVAILABLE", "UNSUPPORTED", "PERMISSION_DENIED"
    ] = Field(
        default="AVAILABLE",
        description="Device Wi-Fi telemetry capability status",
    )
    device_id: str | None = Field(
        default=None,
        max_length=128,
        description="Hardware installation identifier",
    )
    is_mock_location: bool | None = Field(
        default=False,
        description="Whether mock GPS was detected on client",
    )
    location_captured_at: datetime | None = Field(
        default=None,
        description="Hardware timestamp when GPS was acquired",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional device or sensor telemetry",
    )

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        clean = v.strip().upper()
        if clean not in ("CHECK_IN", "CHECK_OUT", "BREAK_START", "BREAK_END"):
            raise ValueError(f"Invalid attendance event type: {v}")
        return clean

    @field_validator("device_reported_at", "location_captured_at")
    @classmethod
    def ensure_utc(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        if v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v.astimezone(UTC)


class AttendanceBatchSyncRequest(BaseModel):
    """Batch payload containing up to 50 queued offline attendance punches from a client device."""

    model_config = ConfigDict(extra="ignore")

    batch_id: str | None = Field(
        default=None,
        max_length=64,
        description="Client batch correlation identifier",
    )
    device_id: str | None = Field(
        default=None,
        max_length=128,
        description="Device hardware identifier",
    )
    employee_id: uuid.UUID | None = Field(
        default=None,
        description="Target employee UUID (must match authenticated user unless Owner/Admin/HR)",
    )
    items: list[BatchSyncPunchItem] = Field(
        min_length=1,
        max_length=50,
        description="List of offline attendance punches (minimum 1, maximum 50)",
    )


class BatchSyncReceiptItem(BaseModel):
    """Individual processing receipt for a single item submitted in an attendance sync batch."""

    model_config = ConfigDict(from_attributes=True)

    local_id: str = Field(description="Client local SQLite queue ID")
    idempotency_key: str = Field(description="Unique client punch UUID")
    status: BatchSyncItemStatus = Field(description="Processing result status")
    event_type: str = Field(description="Attendance event type")
    server_event_id: uuid.UUID | None = Field(
        default=None,
        description="Created or existing attendance event UUID in ledger",
    )
    effective_at: datetime | None = Field(
        default=None,
        description="Authoritative effective timestamp applied for shift calculation",
    )
    review_status: str | None = Field(
        default=None,
        description="Review status (NOT_REQUIRED, PENDING_REVIEW, FLAGGED, etc.)",
    )
    error_code: str | None = Field(
        default=None,
        description="Standardized error code if rejected or conflict",
    )
    error_message: str | None = Field(
        default=None,
        description="Detailed explanation of rejection or conflict",
    )
    idempotent_replay: bool = Field(
        default=False,
        description="Whether this receipt represents a replay of a previously completed punch",
    )


class AttendanceBatchSyncResponse(BaseModel):
    """Aggregate response for a batch synchronization request."""

    model_config = ConfigDict(from_attributes=True)

    batch_id: str | None = None
    total_items: int
    accepted_count: int
    duplicate_count: int
    requires_review_count: int
    conflict_count: int
    rejected_count: int
    receipts: list[BatchSyncReceiptItem]

