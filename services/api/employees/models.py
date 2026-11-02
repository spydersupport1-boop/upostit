"""SQLAlchemy models for employee management."""

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from services.api.database import Base


class Employee(Base):
    """Represents an employee profile in a tenant organization."""

    __tablename__ = "employees"

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
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    employee_id: Mapped[str] = mapped_column(String(50), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    work_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone_number: Mapped[str | None] = mapped_column(String(50), nullable=True)

    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    designation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("designations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reporting_manager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    employment_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="full_time"
    )  # full_time, part_time, contract, intern, temporary
    joining_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", index=True
    )  # active, inactive, on_leave, terminated
    work_location: Mapped[str | None] = mapped_column(String(100), nullable=True)

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
        UniqueConstraint("tenant_id", "employee_id", name="uq_employees_tenant_employee_id"),
        UniqueConstraint("tenant_id", "work_email", name="uq_employees_tenant_work_email"),
        UniqueConstraint("tenant_id", "id", name="uq_employees_tenant_id"),
        UniqueConstraint("tenant_id", "user_id", name="uq_employees_tenant_user_id"),
        Index("ix_employees_tenant_status", "tenant_id", "status"),
        Index("ix_employees_tenant_dept", "tenant_id", "department_id"),
    )

    # Relationships
    tenant = relationship("Tenant")
    user = relationship("User")
    department = relationship(
        "Department", foreign_keys=[department_id], back_populates="employees"
    )
    designation = relationship(
        "Designation", foreign_keys=[designation_id], back_populates="employees"
    )
    manager = relationship("Employee", foreign_keys=[reporting_manager_id], remote_side=[id])
    invitations = relationship(
        "EmployeeInvitation", back_populates="employee", cascade="all, delete-orphan"
    )


class ImportJob(Base):
    """Tracks asynchronous bulk employee import jobs, file storage references, and row-level progress."""

    __tablename__ = "import_jobs"

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
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_format: Mapped[str] = mapped_column(String(10), nullable=False)  # csv, xlsx
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="queued", index=True
    )  # queued, processing, completed, failed
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    succeeded_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_processed_row_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_summary: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    s3_file_key: Mapped[str] = mapped_column(String(500), nullable=False)
    s3_error_key: Mapped[str | None] = mapped_column(String(500), nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
            ["tenant_id", "created_by_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_import_jobs_user",
            ondelete="SET NULL (created_by_user_id)",
        ),
        Index("ix_import_jobs_tenant_status", "tenant_id", "status"),
        Index("ix_import_jobs_tenant_created", "tenant_id", "created_at"),
    )

    # Relationships
    tenant = relationship("Tenant")
    creator = relationship("User", foreign_keys=[created_by_user_id])


class EmployeeInvitation(Base):
    """Tracks employee invitation tokens, lifecycle statuses, and account activation attempts."""

    __tablename__ = "employee_invitations"

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
    invited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )  # pending, accepted, expired, revoked
    delivery_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending"
    )  # pending, sent, failed
    delivery_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
        UniqueConstraint("tenant_id", "id", name="uq_employee_invitations_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            name="fk_invitations_employee",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "invited_by_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_invitations_user",
            ondelete="SET NULL (invited_by_user_id)",
        ),
        Index("ix_invitations_tenant_employee", "tenant_id", "employee_id"),
        Index("ix_invitations_tenant_status", "tenant_id", "status"),
        Index(
            "uq_invitations_active_employee",
            "tenant_id",
            "employee_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
    )

    # Relationships
    tenant = relationship("Tenant", overlaps="invitations")
    employee = relationship("Employee", foreign_keys=[employee_id], back_populates="invitations")
    invited_by = relationship("User", foreign_keys=[invited_by_user_id])


