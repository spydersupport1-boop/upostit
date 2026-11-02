"""SQLAlchemy models for workplace locations and employee location assignments."""

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
    UniqueConstraint,
    column,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from services.api.database import Base
from services.api.employees.models import Employee  # noqa: F401
from services.api.tenants.models import Tenant  # noqa: F401


class Location(Base):
    """Represents a physical workplace location with PostGIS geofencing."""

    __tablename__ = "locations"

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
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    address_line1: Mapped[str] = mapped_column(String(255), nullable=False)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    latitude: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False)
    radius_meters: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False)
    wifi_bssids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    ip_ranges: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
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
        UniqueConstraint("tenant_id", "code", name="uq_locations_tenant_code"),
        UniqueConstraint("tenant_id", "id", name="uq_locations_tenant_id"),
        CheckConstraint(
            "latitude >= -90.0000000 AND latitude <= 90.0000000",
            name="chk_locations_latitude_bounds",
        ),
        CheckConstraint(
            "longitude >= -180.0000000 AND longitude <= 180.0000000",
            name="chk_locations_longitude_bounds",
        ),
        CheckConstraint(
            "radius_meters >= 10 AND radius_meters <= 50000", name="chk_locations_radius_bounds"
        ),
        Index("ix_locations_tenant_active", "tenant_id", "is_active"),
    )

    # Relationships
    tenant = relationship("Tenant")
    employee_assignments = relationship(
        "EmployeeLocation", back_populates="location", cascade="all, delete-orphan"
    )


class EmployeeLocation(Base):
    """Junction model connecting employees to physical workplace locations."""

    __tablename__ = "employee_locations"

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
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            name="fk_emp_loc_employee",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "location_id"],
            ["locations.tenant_id", "locations.id"],
            name="fk_emp_loc_location",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "tenant_id",
            "employee_id",
            "location_id",
            "effective_from",
            name="uq_emp_loc_assignment",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from", name="chk_emp_loc_dates"
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
            where=text("is_primary = TRUE"),
            using="gist",
            name="excl_emp_primary_workplace_overlap",
        ),
        Index("ix_emp_loc_tenant_emp", "tenant_id", "employee_id"),
        Index("ix_emp_loc_tenant_loc", "tenant_id", "location_id"),
    )

    # Relationships
    tenant = relationship("Tenant", overlaps="employee_assignments")
    employee = relationship("Employee", foreign_keys=[employee_id])
    location = relationship(
        "Location", foreign_keys=[location_id], back_populates="employee_assignments"
    )
