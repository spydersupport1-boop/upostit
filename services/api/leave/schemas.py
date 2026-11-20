"""Pydantic v2 schemas for Phase 9 Leave Types, Holiday Calendars, and Holidays."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

# ==============================================================================
# Leave Types Schemas
# ==============================================================================


class LeaveTypeCreateRequest(BaseModel):
    """Payload to configure a new organization leave type."""

    model_config = ConfigDict(str_strip_whitespace=True)

    code: str = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Unique leave code (e.g., 'CL', 'SL', 'AL', 'LOP')",
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Human-readable title for the leave category",
    )
    description: str | None = Field(
        default=None,
        description="Optional policy summary or guidelines",
    )
    is_paid: bool = Field(
        default=True,
        description="Whether this leave is paid time off",
    )
    requires_approval: bool = Field(
        default=True,
        description="Whether managerial approval is mandated before confirmation",
    )
    allow_half_day: bool = Field(
        default=True,
        description="Whether employees can apply for half-day increments",
    )
    max_consecutive_days: int | None = Field(
        default=None,
        gt=0,
        description="Maximum consecutive days permissible per single application",
    )
    carry_forward_limit: Decimal = Field(
        default=Decimal("0.0"),
        ge=Decimal("0.0"),
        description="Maximum unused balance days that roll over into next calendar year",
    )
    is_active: bool = Field(
        default=True,
        description="Whether this leave type is currently active for application",
    )


class LeaveTypeUpdateRequest(BaseModel):
    """Payload to update an existing leave type."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    description: str | None = None
    is_paid: bool | None = None
    requires_approval: bool | None = None
    allow_half_day: bool | None = None
    max_consecutive_days: int | None = Field(default=None, gt=0)
    carry_forward_limit: Decimal | None = Field(default=None, ge=Decimal("0.0"))
    is_active: bool | None = None


class LeaveTypeResponse(BaseModel):
    """Response representation of a leave type."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    is_paid: bool
    requires_approval: bool
    allow_half_day: bool
    max_consecutive_days: int | None = None
    carry_forward_limit: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime


class LeaveTypeListResponse(BaseModel):
    """Paginated list of leave types."""

    items: list[LeaveTypeResponse]
    total: int
    limit: int
    offset: int


# ==============================================================================
# Holiday & Calendar Schemas
# ==============================================================================


class HolidayCreateRequest(BaseModel):
    """Payload to add a holiday to a calendar."""

    model_config = ConfigDict(str_strip_whitespace=True)

    holiday_date: date = Field(..., description="Date of the holiday")
    name: str = Field(..., min_length=1, max_length=100, description="Name of the holiday")
    holiday_type: str = Field(
        default="PUBLIC",
        pattern=r"^(PUBLIC|COMPANY|OPTIONAL)$",
        description="Type: 'PUBLIC', 'COMPANY', or 'OPTIONAL'",
    )
    is_optional: bool = Field(
        default=False,
        description="Whether this is a floating/restricted holiday",
    )
    description: str | None = Field(default=None, description="Optional notes")


class HolidayUpdateRequest(BaseModel):
    """Payload to update a holiday entry."""

    model_config = ConfigDict(str_strip_whitespace=True)

    holiday_date: date | None = None
    name: str | None = Field(default=None, min_length=1, max_length=100)
    holiday_type: str | None = Field(default=None, pattern=r"^(PUBLIC|COMPANY|OPTIONAL)$")
    is_optional: bool | None = None
    description: str | None = None


class HolidayResponse(BaseModel):
    """Response representation of a single holiday."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    calendar_id: uuid.UUID
    holiday_date: date
    name: str
    holiday_type: str
    is_optional: bool
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class HolidayListResponse(BaseModel):
    """List of holidays within a calendar or query."""

    items: list[HolidayResponse]
    total: int


class HolidayCalendarCreateRequest(BaseModel):
    """Payload to configure a new annual holiday calendar."""

    model_config = ConfigDict(str_strip_whitespace=True)

    year: int = Field(..., ge=2000, le=2100, description="Calendar year")
    name: str = Field(..., min_length=1, max_length=100, description="Calendar name")
    location_id: uuid.UUID | None = Field(
        default=None,
        description="Optional workplace location ID override",
    )
    department_id: uuid.UUID | None = Field(
        default=None,
        description="Optional department ID override",
    )
    is_default: bool = Field(
        default=False,
        description="Whether this calendar serves as the tenant default fallback",
    )


class HolidayCalendarUpdateRequest(BaseModel):
    """Payload to update a holiday calendar header."""

    model_config = ConfigDict(str_strip_whitespace=True)

    year: int | None = Field(default=None, ge=2000, le=2100)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    location_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    is_default: bool | None = None


class HolidayCalendarResponse(BaseModel):
    """Response representation of an annual holiday calendar."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    year: int
    name: str
    location_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    is_default: bool
    holiday_count: int = 0
    holidays: list[HolidayResponse] = []
    created_at: datetime
    updated_at: datetime


class HolidayCalendarListResponse(BaseModel):
    """Paginated list of holiday calendars."""

    items: list[HolidayCalendarResponse]
    total: int
    limit: int
    offset: int


# ==============================================================================
# Employee Upcoming Holidays Schemas
# ==============================================================================


class UpcomingHolidayItem(BaseModel):
    """Single upcoming holiday item for employee display."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    holiday_date: date
    name: str
    holiday_type: str
    is_optional: bool
    description: str | None = None
    calendar_id: uuid.UUID
    calendar_name: str


class UpcomingHolidaysResponse(BaseModel):
    """Response for upcoming employee holidays."""

    items: list[UpcomingHolidayItem]
    total: int
    limit: int
    offset: int
    resolved_calendar_id: uuid.UUID | None = None
    resolved_calendar_name: str | None = None
    resolution_source: str  # "LOCATION", "DEPARTMENT", "TENANT_DEFAULT", "NONE"


# ==============================================================================
# Leave Balance Schemas
# ==============================================================================


class LeaveBalanceResponse(BaseModel):
    """Employee leave balance representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    employee_id: uuid.UUID
    leave_type_id: uuid.UUID
    leave_type_code: str
    leave_type_name: str
    year: int
    annual_allocation: Decimal
    carried_forward: Decimal
    accrued: Decimal
    used: Decimal
    pending_approval: Decimal
    available_balance: Decimal
    created_at: datetime
    updated_at: datetime


class LeaveBalanceListResponse(BaseModel):
    """List of leave balances for an employee."""

    items: list[LeaveBalanceResponse]
    total: int


# ==============================================================================
# Leave Request Schemas
# ==============================================================================


class LeaveRequestCreate(BaseModel):
    """Payload to apply for leave."""

    model_config = ConfigDict(str_strip_whitespace=True)

    leave_type_id: uuid.UUID
    start_date: date
    end_date: date
    is_half_day: bool = False
    half_day_period: str | None = Field(
        default=None,
        pattern=r"^(FIRST_HALF|SECOND_HALF)$",
        description="Must be 'FIRST_HALF' or 'SECOND_HALF' when is_half_day=True",
    )
    reason: str = Field(..., min_length=3, max_length=1000)


class LeaveRequestResponse(BaseModel):
    """Representation of an employee leave request."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str | None = None
    leave_type_id: uuid.UUID
    leave_type_code: str | None = None
    leave_type_name: str | None = None
    start_date: date
    end_date: date
    is_half_day: bool
    half_day_period: str | None = None
    total_days: Decimal
    reason: str
    status: str
    reviewer_user_id: uuid.UUID | None = None
    reviewer_notes: str | None = None
    decided_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class LeaveRequestListResponse(BaseModel):
    """Paginated list of leave requests."""

    items: list[LeaveRequestResponse]
    total: int
    limit: int
    offset: int


class LeaveRequestDecisionRequest(BaseModel):
    """Supervisor decision payload."""

    model_config = ConfigDict(str_strip_whitespace=True)

    action: str = Field(..., pattern=r"^(APPROVE|REJECT)$")
    reason: str | None = Field(
        default=None,
        description="Mandatory reason if action is REJECT (min 3 characters)",
    )


class LeaveRequestCancelRequest(BaseModel):
    """Employee cancellation request."""

    model_config = ConfigDict(str_strip_whitespace=True)

    reason: str | None = None


# ==============================================================================
# Overtime Rules & Records Schemas (Milestone 9.4)
# ==============================================================================


class OvertimeRuleCreateRequest(BaseModel):
    """Payload to configure a new tenant overtime rule."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=100)
    min_overtime_threshold_minutes: int = Field(default=30, ge=0)
    max_daily_overtime_minutes: int | None = Field(default=240, gt=0)
    max_weekly_overtime_minutes: int | None = Field(default=720, gt=0)
    workday_multiplier: Decimal = Field(default=Decimal("1.50"), ge=Decimal("1.00"))
    weekend_multiplier: Decimal = Field(default=Decimal("2.00"), ge=Decimal("1.00"))
    holiday_multiplier: Decimal = Field(default=Decimal("2.00"), ge=Decimal("1.00"))
    requires_manager_approval: bool = True
    requires_pre_approval: bool = False
    is_default: bool = False
    is_active: bool = True


class OvertimeRuleUpdateRequest(BaseModel):
    """Payload to update an existing overtime rule."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=100)
    min_overtime_threshold_minutes: int | None = Field(default=None, ge=0)
    max_daily_overtime_minutes: int | None = Field(default=None, gt=0)
    max_weekly_overtime_minutes: int | None = Field(default=None, gt=0)
    workday_multiplier: Decimal | None = Field(default=None, ge=Decimal("1.00"))
    weekend_multiplier: Decimal | None = Field(default=None, ge=Decimal("1.00"))
    holiday_multiplier: Decimal | None = Field(default=None, ge=Decimal("1.00"))
    requires_manager_approval: bool | None = None
    requires_pre_approval: bool | None = None
    is_default: bool | None = None
    is_active: bool | None = None


class OvertimeRuleResponse(BaseModel):
    """Response representation of an overtime rule."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    min_overtime_threshold_minutes: int
    max_daily_overtime_minutes: int | None = None
    max_weekly_overtime_minutes: int | None = None
    workday_multiplier: Decimal
    weekend_multiplier: Decimal
    holiday_multiplier: Decimal
    requires_manager_approval: bool
    requires_pre_approval: bool
    is_default: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class OvertimeRuleListResponse(BaseModel):
    """Paginated list of overtime rules."""

    items: list[OvertimeRuleResponse]
    total: int
    limit: int
    offset: int


class OvertimeRecordResponse(BaseModel):
    """Response representation of an overtime calculation record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str | None = None
    attendance_day_id: uuid.UUID
    attendance_date: date
    overtime_rule_id: uuid.UUID | None = None
    raw_overtime_minutes: int
    approved_overtime_minutes: int
    multiplier: Decimal
    payable_overtime_minutes: int
    overtime_type: str
    status: str
    reviewer_user_id: uuid.UUID | None = None
    reviewer_notes: str | None = None
    decided_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class OvertimeRecordListResponse(BaseModel):
    """Paginated list of overtime records."""

    items: list[OvertimeRecordResponse]
    total: int
    limit: int
    offset: int


class OvertimeDecisionRequest(BaseModel):
    """Supervisor decision payload on an overtime record."""

    model_config = ConfigDict(str_strip_whitespace=True)

    action: str = Field(..., pattern=r"^(APPROVE|REJECT)$")
    reason: str | None = Field(
        default=None,
        description="Mandatory explanation if action is REJECT (min 3 characters)",
    )
    approved_minutes: int | None = Field(
        default=None,
        ge=0,
        description="Optional adjusted approved minutes (defaults to raw_overtime_minutes if omitted)",
    )
