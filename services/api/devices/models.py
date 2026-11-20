"""SQLAlchemy model for employee device hardware binding."""

import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from services.api.database import Base


class Device(Base):
    """Registered employee mobile or terminal device."""

    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    device_id_hash: Mapped[str] = mapped_column(
        sa.String(128),
        nullable=False,
    )
    platform: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
    )
    device_model: Mapped[str | None] = mapped_column(
        sa.String(100),
        nullable=True,
    )
    os_name: Mapped[str | None] = mapped_column(
        sa.String(50),
        nullable=True,
    )
    os_version: Mapped[str | None] = mapped_column(
        sa.String(50),
        nullable=True,
    )
    app_version: Mapped[str | None] = mapped_column(
        sa.String(50),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        sa.String(30),
        default="ACTIVE",
        nullable=False,
    )
    registered_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    revoked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    revocation_reason: Mapped[str | None] = mapped_column(
        sa.Text,
        nullable=True,
    )
    replacement_for_device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    replacement_approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    replacement_approved_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            name="fk_devices_employee",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "revoked_by_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_devices_revoked_by",
            ondelete="SET NULL (revoked_by_user_id)",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "replacement_for_device_id"],
            ["devices.tenant_id", "devices.id"],
            name="fk_devices_replacement_for",
            ondelete="SET NULL (replacement_for_device_id)",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "replacement_approved_by_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_devices_replacement_approved_by",
            ondelete="SET NULL (replacement_approved_by_user_id)",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_devices_tenant_id"),
        sa.UniqueConstraint("tenant_id", "device_id_hash", name="uq_devices_tenant_device_hash"),
        sa.CheckConstraint(
            "platform IN ('ANDROID', 'IOS', 'WEB', 'OTHER')",
            name="chk_devices_platform",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING_APPROVAL', 'ACTIVE', 'REVOKED', 'REPLACED')",
            name="chk_devices_status",
        ),
    )

