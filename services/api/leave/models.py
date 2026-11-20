"""SQLAlchemy data models for Phase 9: Leave, Holidays and Overtime Multipliers.

Entities:
- LeaveType (leave_types)
- LeaveBalance (leave_balances)
- LeaveRequest (leave_requests)
- HolidayCalendar (holiday_calendars)
- Holiday (holidays)
- OvertimeRule (overtime_rules)
- OvertimeRecord (overtime_records)
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from services.api.attendance.models import AttendanceDay  # noqa: F401
from services.api.auth.models import User  # noqa: F401
from services.api.database import Base
from services.api.employees.models import Employee  # noqa: F401
from services.api.locations.models import Location  # noqa: F401
from services.api.organization.models import Department  # noqa: F401
from services.api.tenants.models import Tenant  # noqa: F401


class LeaveType(Base):
    """Configurable leave category within an organization."""

    __tablename__ = "leave_types"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_paid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_half_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    max_consecutive_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    carry_forward_limit: Mapped[Decimal] = mapped_column(
        Numeric(4, 1), nullable=False, default=Decimal("0.0")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_leave_types_tenant_id"),
        UniqueConstraint("tenant_id", "code", name="uq_leave_types_tenant_code"),
        CheckConstraint("carry_forward_limit >= 0", name="chk_leave_types_carry_forward"),
        CheckConstraint(
            "max_consecutive_days IS NULL OR max_consecutive_days > 0",
            name="chk_leave_types_max_consecutive",
        ),
        Index("ix_leave_types_tenant_active", "tenant_id", "is_active"),
    )

    # Relationships
    tenant = relationship("Tenant", foreign_keys=[tenant_id])
    balances = relationship("LeaveBalance", back_populates="leave_type")
    requests = relationship("LeaveRequest", back_populates="leave_type")


class LeaveBalance(Base):
    """Per-employee, per-leave-type entitlement quota and balance tracking."""

    __tablename__ = "leave_balances"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    leave_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)

    annual_allocation: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0.00")
    )
    carried_forward: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0.00")
    )
    accrued: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    used: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    pending_approval: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0.00")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_leave_balances_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "employee_id",
            "leave_type_id",
            "year",
            name="uq_leave_balances_tenant_emp_type_year",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            name="fk_leave_balances_employee",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "leave_type_id"],
            ["leave_types.tenant_id", "leave_types.id"],
            name="fk_leave_balances_leave_type",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "annual_allocation >= 0 AND carried_forward >= 0 AND accrued >= 0 AND used >= 0 AND pending_approval >= 0",
            name="chk_leave_balances_non_negative",
        ),
        Index("ix_leave_balances_tenant_emp_year", "tenant_id", "employee_id", "year"),
    )

    # Invariant helper property
    @property
    def available_balance(self) -> Decimal:
        """Available balance = allocation + carried + accrued - used - pending."""
        return (
            self.annual_allocation
            + self.carried_forward
            + self.accrued
            - self.used
            - self.pending_approval
        )

    # Relationships
    employee = relationship("Employee", foreign_keys=[tenant_id, employee_id], overlaps="balances")
    leave_type = relationship(
        "LeaveType",
        back_populates="balances",
        foreign_keys=[tenant_id, leave_type_id],
        overlaps="employee",
    )


class LeaveRequest(Base):
    """Employee-initiated time-off application record with supervisor approval state machine."""

    __tablename__ = "leave_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    leave_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_half_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    half_day_period: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )  # 'FIRST_HALF', 'SECOND_HALF'
    total_days: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="PENDING_APPROVAL",
    )  # 'PENDING_APPROVAL', 'APPROVED', 'REJECTED', 'CANCELLED'

    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_leave_requests_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            name="fk_leave_requests_employee",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "leave_type_id"],
            ["leave_types.tenant_id", "leave_types.id"],
            name="fk_leave_requests_leave_type",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "reviewer_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_leave_requests_reviewer",
            ondelete="SET NULL",
        ),
        CheckConstraint("end_date >= start_date", name="chk_leave_requests_date_range"),
        CheckConstraint("total_days > 0", name="chk_leave_requests_total_days"),
        CheckConstraint(
            "status IN ('PENDING_APPROVAL', 'APPROVED', 'REJECTED', 'CANCELLED')",
            name="chk_leave_requests_status",
        ),
        CheckConstraint(
            "(is_half_day = FALSE AND half_day_period IS NULL) OR "
            "(is_half_day = TRUE AND half_day_period IN ('FIRST_HALF', 'SECOND_HALF') AND start_date = end_date AND total_days = 0.50)",
            name="chk_leave_requests_half_day",
        ),
        CheckConstraint(
            "(status = 'PENDING_APPROVAL' AND decided_at IS NULL AND reviewer_user_id IS NULL) OR "
            "(status IN ('APPROVED', 'REJECTED') AND decided_at IS NOT NULL AND reviewer_user_id IS NOT NULL) OR "
            "(status = 'CANCELLED')",
            name="chk_leave_requests_decision",
        ),
        Index("ix_leave_requests_tenant_emp_status", "tenant_id", "employee_id", "status"),
        Index("ix_leave_requests_tenant_dates", "tenant_id", "start_date", "end_date"),
        Index("ix_leave_requests_tenant_status", "tenant_id", "status"),
    )

    # Relationships
    employee = relationship("Employee", foreign_keys=[tenant_id, employee_id], overlaps="requests")
    leave_type = relationship(
        "LeaveType",
        back_populates="requests",
        foreign_keys=[tenant_id, leave_type_id],
        overlaps="employee",
    )
    reviewer = relationship(
        "User",
        foreign_keys=[tenant_id, reviewer_user_id],
        overlaps="employee,leave_type,requests",
    )


class HolidayCalendar(Base):
    """Annual holiday calendar with optional workplace location or department overrides."""

    __tablename__ = "holiday_calendars"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_holiday_calendars_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "location_id"],
            ["locations.tenant_id", "locations.id"],
            name="fk_holiday_calendars_location",
            ondelete="SET NULL",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "department_id"],
            ["departments.tenant_id", "departments.id"],
            name="fk_holiday_calendars_department",
            ondelete="SET NULL",
        ),
        Index("ix_holiday_calendars_tenant_year", "tenant_id", "year"),
        Index("ix_holiday_calendars_tenant_location", "tenant_id", "location_id"),
    )

    # Relationships
    tenant = relationship("Tenant", foreign_keys=[tenant_id])
    location = relationship("Location", foreign_keys=[tenant_id, location_id], overlaps="tenant")
    department = relationship(
        "Department", foreign_keys=[tenant_id, department_id], overlaps="location,tenant"
    )
    holidays = relationship("Holiday", back_populates="calendar", cascade="all, delete-orphan")


class Holiday(Base):
    """Specific holiday date within an annual holiday calendar."""

    __tablename__ = "holidays"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    calendar_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    holiday_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    holiday_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="PUBLIC",
    )  # 'PUBLIC', 'COMPANY', 'OPTIONAL'
    is_optional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_holidays_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "calendar_id",
            "holiday_date",
            name="uq_holidays_tenant_calendar_date",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "calendar_id"],
            ["holiday_calendars.tenant_id", "holiday_calendars.id"],
            name="fk_holidays_calendar",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "holiday_type IN ('PUBLIC', 'COMPANY', 'OPTIONAL')",
            name="chk_holidays_type",
        ),
        Index("ix_holidays_tenant_date", "tenant_id", "holiday_date"),
        Index("ix_holidays_tenant_calendar", "tenant_id", "calendar_id"),
    )

    # Relationships
    calendar = relationship(
        "HolidayCalendar", back_populates="holidays", foreign_keys=[tenant_id, calendar_id]
    )


class OvertimeRule(Base):
    """Tenant-level overtime policy and multiplier configuration."""

    __tablename__ = "overtime_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    min_overtime_threshold_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    max_daily_overtime_minutes: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=240
    )
    max_weekly_overtime_minutes: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=720
    )
    workday_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), nullable=False, default=Decimal("1.50")
    )
    weekend_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), nullable=False, default=Decimal("2.00")
    )
    holiday_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), nullable=False, default=Decimal("2.00")
    )
    requires_manager_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    requires_pre_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_overtime_rules_tenant_id"),
        CheckConstraint(
            "min_overtime_threshold_minutes >= 0",
            name="chk_overtime_rules_min_threshold",
        ),
        CheckConstraint(
            "max_daily_overtime_minutes IS NULL OR max_daily_overtime_minutes >= min_overtime_threshold_minutes",
            name="chk_overtime_rules_max_daily",
        ),
        CheckConstraint(
            "workday_multiplier >= 1.00 AND weekend_multiplier >= 1.00 AND holiday_multiplier >= 1.00",
            name="chk_overtime_rules_multipliers",
        ),
        Index("ix_overtime_rules_tenant_active", "tenant_id", "is_active"),
        Index("ix_overtime_rules_tenant_default", "tenant_id", "is_default"),
    )

    # Relationships
    tenant = relationship("Tenant", foreign_keys=[tenant_id])


class OvertimeRecord(Base):
    """Derived overtime calculation record per employee and attendance day."""

    __tablename__ = "overtime_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    attendance_day_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    overtime_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    attendance_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    raw_overtime_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    approved_overtime_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    multiplier: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), nullable=False, default=Decimal("1.00")
    )
    payable_overtime_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overtime_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )  # 'WORKDAY', 'WEEK_OFF', 'HOLIDAY'
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="PENDING_APPROVAL",
    )  # 'AUTO_APPROVED', 'PENDING_APPROVAL', 'APPROVED', 'REJECTED'

    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_overtime_records_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "employee_id",
            "attendance_date",
            name="uq_overtime_records_tenant_emp_date",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            name="fk_overtime_records_employee",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "attendance_day_id"],
            ["attendance_days.tenant_id", "attendance_days.id"],
            name="fk_overtime_records_attendance_day",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "reviewer_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_overtime_records_reviewer",
            ondelete="SET NULL",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "overtime_rule_id"],
            ["overtime_rules.tenant_id", "overtime_rules.id"],
            name="fk_overtime_records_rule",
            ondelete="SET NULL",
        ),
        CheckConstraint(
            "raw_overtime_minutes >= 0 AND approved_overtime_minutes >= 0 AND payable_overtime_minutes >= 0",
            name="chk_overtime_records_minutes_positive",
        ),
        CheckConstraint(
            "multiplier >= 1.00",
            name="chk_overtime_records_multiplier",
        ),
        CheckConstraint(
            "overtime_type IN ('WORKDAY', 'WEEK_OFF', 'HOLIDAY')",
            name="chk_overtime_records_type",
        ),
        CheckConstraint(
            "status IN ('AUTO_APPROVED', 'PENDING_APPROVAL', 'APPROVED', 'REJECTED')",
            name="chk_overtime_records_status",
        ),
        CheckConstraint(
            "(status = 'PENDING_APPROVAL' AND decided_at IS NULL AND reviewer_user_id IS NULL) OR "
            "(status IN ('APPROVED', 'REJECTED') AND decided_at IS NOT NULL AND reviewer_user_id IS NOT NULL) OR "
            "(status = 'AUTO_APPROVED')",
            name="chk_overtime_records_decision",
        ),
        Index("ix_overtime_records_tenant_status", "tenant_id", "status"),
        Index("ix_overtime_records_tenant_emp_status", "tenant_id", "employee_id", "status"),
        Index("ix_overtime_records_tenant_date", "tenant_id", "attendance_date"),
        Index("ix_overtime_records_tenant_rule", "tenant_id", "overtime_rule_id"),
    )

    # Relationships
    employee = relationship("Employee", foreign_keys=[tenant_id, employee_id])
    attendance_day = relationship(
        "AttendanceDay", foreign_keys=[tenant_id, attendance_day_id], overlaps="employee"
    )
    overtime_rule = relationship(
        "OvertimeRule",
        foreign_keys=[tenant_id, overtime_rule_id],
        overlaps="employee,attendance_day",
    )
    reviewer = relationship(
        "User",
        foreign_keys=[tenant_id, reviewer_user_id],
        overlaps="attendance_day,employee,overtime_rule",
    )
