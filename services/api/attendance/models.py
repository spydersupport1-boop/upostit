"""SQLAlchemy models for shift templates, immutable shift versions, and employee assignments."""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

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
    Time,
    UniqueConstraint,
    column,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym

from services.api.auth.models import User  # noqa: F401
from services.api.database import Base
from services.api.employees.models import Employee  # noqa: F401
from services.api.locations.models import Location  # noqa: F401
from services.api.tenants.models import Tenant  # noqa: F401


class ShiftTemplate(Base):
    """Represents a master shift template identity within an organization."""

    __tablename__ = "shift_templates"

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
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
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
        UniqueConstraint("tenant_id", "code", name="uq_shift_templates_tenant_code"),
        UniqueConstraint("tenant_id", "id", name="uq_shift_templates_tenant_id"),
        Index("ix_shift_templates_tenant_active", "tenant_id", "is_active"),
    )

    # Relationships
    tenant = relationship("Tenant", overlaps="shift_template,template,versions,assignments")
    versions = relationship(
        "ShiftTemplateVersion",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="desc(ShiftTemplateVersion.version_number)",
        overlaps="tenant",
    )
    assignments = relationship(
        "ShiftAssignment",
        back_populates="shift_template",
        overlaps="tenant",
    )


class ShiftTemplateVersion(Base):
    """Immutable snapshot of operational shift parameters effective from a specific calendar date."""

    __tablename__ = "shift_template_versions"

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
    shift_template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    version_effective_from: Mapped[date] = mapped_column(Date, nullable=False)

    start_time: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    end_time: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)

    grace_period_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    early_exit_grace_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    early_arrival_allowance_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=120
    )
    late_departure_allowance_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=180
    )
    half_day_threshold_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=240)
    full_day_threshold_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=480)
    break_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)

    is_overnight: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_flexible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    weekly_off_days: Mapped[list[int]] = mapped_column(
        JSONB, nullable=False, default=lambda: [6, 0]
    )

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "shift_template_id"],
            ["shift_templates.tenant_id", "shift_templates.id"],
            name="fk_shift_versions_template",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "created_by_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_shift_versions_user",
            ondelete="SET NULL (created_by_user_id)",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_shift_versions_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "shift_template_id",
            "version_number",
            name="uq_shift_versions_tenant_template_vnum",
        ),
        UniqueConstraint(
            "tenant_id",
            "shift_template_id",
            "version_effective_from",
            name="uq_shift_versions_tenant_template_date",
        ),
        CheckConstraint(
            "half_day_threshold_minutes > 0 AND full_day_threshold_minutes >= half_day_threshold_minutes",
            name="chk_shift_versions_thresholds",
        ),
        CheckConstraint(
            "grace_period_minutes >= 0 AND early_exit_grace_minutes >= 0 AND "
            "early_arrival_allowance_minutes >= 0 AND late_departure_allowance_minutes >= 0",
            name="chk_shift_versions_graces",
        ),
        Index(
            "ix_shift_versions_tenant_tmpl_date",
            "tenant_id",
            "shift_template_id",
            "version_effective_from",
        ),
    )

    # Relationships
    tenant = relationship("Tenant", overlaps="template,versions")
    template = relationship("ShiftTemplate", back_populates="versions", overlaps="tenant")
    created_by_user = relationship("User", foreign_keys=[created_by_user_id])


class ShiftAssignment(Base):
    """Junction mapping employees to shift templates with temporal validity and non-overlapping exclusion."""

    __tablename__ = "shift_assignments"

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
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    shift_template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)

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
        ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            name="fk_shift_assignments_employee",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "shift_template_id"],
            ["shift_templates.tenant_id", "shift_templates.id"],
            name="fk_shift_assignments_template",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_shift_assignments_tenant_id"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="chk_shift_assignments_dates",
        ),
        ExcludeConstraint(
            ("tenant_id", "="),
            ("employee_id", "="),
            (
                func.daterange(
                    column("effective_from"),
                    func.coalesce(column("effective_to"), text("'infinity'::date")),
                    "[]",
                ),
                "&&",
            ),
            using="gist",
            name="excl_shift_assignments_overlap",
        ),
        Index("ix_shift_assignments_tenant_emp", "tenant_id", "employee_id"),
        Index("ix_shift_assignments_tenant_shift", "tenant_id", "shift_template_id"),
    )

    # Relationships
    tenant = relationship("Tenant", overlaps="assignments,shift_template")
    employee = relationship("Employee", foreign_keys=[employee_id])
    shift_template = relationship(
        "ShiftTemplate",
        foreign_keys=[shift_template_id],
        back_populates="assignments",
        overlaps="tenant",
    )


class AttendanceEvent(Base):
    """Append-only presence event ledger recording punch actions with offline-readiness attributes."""

    __tablename__ = "attendance_events"

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
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # CHECK_IN, CHECK_OUT, BREAK_START, BREAK_END
    event_category: Mapped[str] = mapped_column(
        String(30), nullable=False, default="STANDARD"
    )  # STANDARD, CORRECTION_INSERT, etc.
    supersedes_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    correction_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    server_received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    device_reported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    clock_drift_seconds: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 3),
        nullable=True,
        default=Decimal("0.000"),
    )
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="WEB"
    )  # WEB, MOBILE, ADMIN, DEVICE, API
    device_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    timestamp_verification_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="SERVER_AUTHORITATIVE"
    )
    review_status: Mapped[str] = mapped_column(String(30), nullable=False, default="NOT_REQUIRED")
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)

    location_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    accuracy_meters: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    applied_policy_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wifi_bssid: Mapped[str | None] = mapped_column(String(17), nullable=True)
    wifi_ssid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_mock_location: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    # Synonyms for bidirectional compatibility
    server_timestamp = synonym("server_received_at")
    device_reported_timestamp = synonym("device_reported_at")
    effective_timestamp = synonym("effective_at")
    device_identifier = synonym("device_id")

    @property
    def risk_score(self) -> int:
        return int((self.metadata_json or {}).get("risk_score", 0))

    @property
    def risk_category(self) -> str:
        return str((self.metadata_json or {}).get("risk_category", "NORMAL"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            name="fk_attendance_events_employee",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "location_id"],
            ["locations.tenant_id", "locations.id"],
            name="fk_attendance_events_location",
            ondelete="SET NULL (location_id)",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "actor_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_attendance_events_actor",
            ondelete="SET NULL (actor_user_id)",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "supersedes_event_id"],
            ["attendance_events.tenant_id", "attendance_events.id"],
            name="fk_attendance_events_supersedes",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_attendance_events_tenant_id"),
        UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_attendance_events_tenant_idempotency"
        ),
        CheckConstraint(
            "event_type IN ('CHECK_IN', 'CHECK_OUT', 'BREAK_START', 'BREAK_END')",
            name="chk_attendance_events_type",
        ),
        CheckConstraint(
            "event_category IN ('STANDARD', 'CORRECTION_INSERT', 'CORRECTION_SUPERSEDE', 'CORRECTION_VOID')",
            name="chk_attendance_events_category",
        ),
        CheckConstraint(
            "source IN ('WEB', 'MOBILE', 'BIOMETRIC', 'CCTV', 'ADMIN', 'DEVICE', 'API')",
            name="chk_attendance_events_source",
        ),
        CheckConstraint(
            "timestamp_verification_status IN ('SERVER_AUTHORITATIVE', 'DEVICE_VERIFIED_NTP', 'SUSPICIOUS_CLOCK_DRIFT', 'UNVERIFIED_OFFLINE')",
            name="chk_attendance_events_verification",
        ),
        CheckConstraint(
            "review_status IN ('NOT_REQUIRED', 'PENDING_REVIEW', 'FLAGGED', 'APPROVED', 'REJECTED')",
            name="chk_attendance_events_review",
        ),
        Index("ix_attendance_events_tenant_emp_eff", "tenant_id", "employee_id", "effective_at"),
        Index(
            "ix_attendance_events_tenant_superseded",
            "tenant_id",
            "supersedes_event_id",
            postgresql_where=column("supersedes_event_id").isnot(None),
        ),
        Index("ix_attendance_events_tenant_created", "tenant_id", "created_at"),
    )

    # Relationships
    tenant = relationship("Tenant", overlaps="events")
    employee = relationship("Employee", foreign_keys=[employee_id])
    location = relationship("Location", foreign_keys=[location_id])
    actor_user = relationship("User", foreign_keys=[actor_user_id])


class AttendanceIdempotencyRecord(Base):
    """Tracks punch idempotency keys, SHA-256 request fingerprints, and cached response payloads."""

    __tablename__ = "attendance_idempotency_records"

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
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="IN_PROGRESS"
    )  # IN_PROGRESS, COMPLETED, FAILED
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=lambda: datetime.now(UTC) + timedelta(minutes=15),
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            name="fk_idempotency_employee",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "event_id"],
            ["attendance_events.tenant_id", "attendance_events.id"],
            name="fk_idempotency_event",
            ondelete="SET NULL (event_id)",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_idempotency_tenant_id"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_idempotency_tenant_key"),
        UniqueConstraint(
            "tenant_id", "employee_id", "idempotency_key", name="uq_idempotency_tenant_emp_key"
        ),
        CheckConstraint(
            "status IN ('IN_PROGRESS', 'COMPLETED', 'FAILED')",
            name="chk_idempotency_status",
        ),
        Index(
            "ix_idempotency_tenant_expires",
            "tenant_id",
            "expires_at",
            postgresql_where=column("expires_at").isnot(None),
        ),
        Index("ix_idempotency_tenant_emp", "tenant_id", "employee_id"),
    )

    # Relationships
    tenant = relationship("Tenant", overlaps="idempotency_records")
    employee = relationship("Employee", foreign_keys=[employee_id])
    event = relationship("AttendanceEvent", foreign_keys=[event_id])


class AttendanceDay(Base):
    """Derived projection table storing daily attendance summaries calculated from events."""

    __tablename__ = "attendance_days"

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
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    attendance_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    shift_template_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    shift_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    first_check_in: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_check_out: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    total_working_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_break_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    net_working_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actual_late_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    late_arrival_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actual_early_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    early_departure_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overtime_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="ABSENT"
    )  # 'PRESENT', 'LATE', 'HALF_DAY', 'ABSENT', 'INCOMPLETE', 'WEEK_OFF', 'ON_LEAVE', 'HOLIDAY', 'PENDING_REVIEW'
    calculation_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="CALCULATED"
    )  # 'CALCULATED', 'INCOMPLETE', 'FLAGGED'
    calculation_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_incomplete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    missing_punch: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    last_calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    source_event_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

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
        ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            name="fk_attendance_days_employee",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "shift_template_id"],
            ["shift_templates.tenant_id", "shift_templates.id"],
            name="fk_attendance_days_shift",
            ondelete="SET NULL (shift_template_id)",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "shift_version_id"],
            ["shift_template_versions.tenant_id", "shift_template_versions.id"],
            name="fk_attendance_days_shift_version",
            ondelete="SET NULL (shift_version_id)",
        ),
        UniqueConstraint(
            "tenant_id", "employee_id", "attendance_date", name="uq_attendance_days_tenant_emp_date"
        ),
        UniqueConstraint("tenant_id", "id", name="uq_attendance_days_tenant_id"),
        CheckConstraint(
            "status IN ('PRESENT', 'LATE', 'HALF_DAY', 'ABSENT', 'INCOMPLETE', 'WEEK_OFF', 'ON_LEAVE', 'HOLIDAY', 'PENDING_REVIEW')",
            name="chk_attendance_days_status",
        ),
        CheckConstraint(
            "calculation_status IN ('CALCULATED', 'INCOMPLETE', 'FLAGGED')",
            name="chk_attendance_days_calc_status",
        ),
        Index("ix_attendance_days_tenant_date", "tenant_id", "attendance_date"),
        Index("ix_attendance_days_tenant_status", "tenant_id", "status"),
        Index("ix_attendance_days_tenant_emp_date", "tenant_id", "employee_id", "attendance_date"),
    )

    # Relationships
    tenant = relationship("Tenant", overlaps="days")
    employee = relationship("Employee", foreign_keys=[employee_id])
    shift_template = relationship("ShiftTemplate", foreign_keys=[shift_template_id])
    shift_version = relationship("ShiftTemplateVersion", foreign_keys=[shift_version_id])


class TenantAttendancePolicy(Base):
    """Company Attendance Policy defining verification rules, methods, and fallbacks."""

    __tablename__ = "tenant_attendance_policies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    default_mode: Mapped[str] = mapped_column(String(30), nullable=False, default="MANUAL")
    allowed_methods: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=lambda: ["MANUAL"]
    )
    required_methods: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=lambda: ["MANUAL"]
    )
    combination_rule: Mapped[str] = mapped_column(String(20), nullable=False, default="OR")
    fallback_policy: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    gps_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: {
            "max_accuracy_meters": 100,
            "max_location_age_seconds": 30,
            "enforce_assigned_workplace": True,
            "out_of_geofence_action": "REJECT",
        },
    )
    wifi_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    biometric_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    face_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
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
        UniqueConstraint("tenant_id", "version", name="uq_tenant_attendance_policy_tenant_version"),
        UniqueConstraint("tenant_id", "id", name="uq_tenant_attendance_policy_tenant_id"),
        CheckConstraint(
            "default_mode IN ('MANUAL', 'GPS_ONLY', 'WIFI_ONLY', 'BIOMETRIC_ONLY', 'FACE_RECOGNITION', 'COMBINED')",
            name="chk_tenant_attendance_policy_default_mode",
        ),
        CheckConstraint(
            "combination_rule IN ('AND', 'OR', 'PRIMARY_WITH_FALLBACK')",
            name="chk_tenant_attendance_policy_combination_rule",
        ),
        Index("ix_tenant_attendance_policies_tenant_active", "tenant_id", "is_active"),
    )

    # Relationships
    tenant = relationship("Tenant", foreign_keys=[tenant_id])
    created_by_user = relationship("User", foreign_keys=[created_by_user_id])


class AttendanceConflictIncident(Base):
    """Represents an employee-submitted multi-event offline sequence conflict incident."""

    __tablename__ = "attendance_conflict_incidents"

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
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    bundle_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    session_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="PENDING_REVIEW",
    )
    conflict_code: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="MEDIUM",
    )
    classification: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="NEEDS_MANAGER_REVIEW",
    )
    primary_rejected_event: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )
    dependent_events: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    total_events_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    rejection_summary: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    employee_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    employee_clarification: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    clarification_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    clarification_submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    assigned_reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    decision: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    decision_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    resolved_correction_event_ids: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
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
        UniqueConstraint("tenant_id", "id", name="uq_conflict_incidents_tenant_id"),
        UniqueConstraint("tenant_id", "bundle_id", name="uq_conflict_incidents_tenant_bundle"),
        ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            name="fk_conflict_incidents_employee",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_conflict_incidents_user",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "assigned_reviewer_id"],
            ["users.tenant_id", "users.id"],
            name="fk_conflict_incidents_assigned_reviewer",
            ondelete="SET NULL (assigned_reviewer_id)",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "reviewer_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_conflict_incidents_reviewer",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('PENDING_REVIEW', 'APPROVED', 'REJECTED') OR status IN ('NEEDS_CLARIFICATION', 'UNRESOLVED', 'ESCALATED_HR', 'AUTO_RESOLVED')",
            name="chk_conflict_incidents_status",
        ),
        CheckConstraint(
            "decision IS NULL OR decision IN ('APPROVED', 'REJECTED') OR decision IN ('ACCEPT_SEQUENCE', 'REJECT_INVALID_EVENTS', 'REQUEST_CLARIFICATION', 'MARK_UNRESOLVED', 'ESCALATE_HR')",
            name="chk_conflict_incidents_decision",
        ),
        CheckConstraint(
            "decision IS NULL OR length(trim(decision_reason)) >= 3",
            name="chk_conflict_incidents_reason",
        ),
        CheckConstraint(
            "(status = 'PENDING_REVIEW' AND decision IS NULL) OR "
            "(status = 'APPROVED' AND decision = 'APPROVED') OR "
            "(status = 'REJECTED' AND decision = 'REJECTED') OR "
            "(status = 'APPROVED' AND decision = 'ACCEPT_SEQUENCE') OR "
            "(status = 'REJECTED' AND decision = 'REJECT_INVALID_EVENTS') OR "
            "(status = 'NEEDS_CLARIFICATION' AND decision = 'REQUEST_CLARIFICATION') OR "
            "(status = 'UNRESOLVED' AND decision = 'MARK_UNRESOLVED') OR "
            "(status = 'ESCALATED_HR' AND decision = 'ESCALATE_HR') OR "
            "(status = 'AUTO_RESOLVED' AND decision IS NULL)",
            name="chk_conflict_incidents_status_decision",
        ),
        CheckConstraint(
            "severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="chk_conflict_incidents_severity",
        ),
        Index("ix_conflict_incidents_tenant_status", "tenant_id", "status"),
        Index("ix_conflict_incidents_tenant_code", "tenant_id", "conflict_code"),
        Index("ix_conflict_incidents_tenant_severity", "tenant_id", "severity"),
        Index("ix_conflict_incidents_tenant_employee", "tenant_id", "employee_id"),
        Index("ix_conflict_incidents_tenant_submitted", "tenant_id", "submitted_at"),
        Index("ix_conflict_incidents_tenant_decided", "tenant_id", "decided_at"),
        Index(
            "ix_conflict_incidents_tenant_assigned_reviewer", "tenant_id", "assigned_reviewer_id"
        ),
    )

    # Relationships
    tenant = relationship("Tenant", foreign_keys=[tenant_id])
    employee = relationship("Employee", foreign_keys=[employee_id])
    submitting_user = relationship("User", foreign_keys=[user_id])
    assigned_reviewer = relationship("User", foreign_keys=[assigned_reviewer_id])
    reviewer = relationship("User", foreign_keys=[reviewer_user_id])
