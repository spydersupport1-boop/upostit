"""SQLAlchemy data models for Phase 10: Notifications (Outbound Alerts).

Entities:
- NotificationTemplate (notification_templates): System-defined and tenant-customized templates
- NotificationPreference (notification_preferences): Tenant defaults and user-level channel & quiet-hours preferences
- Notification (notifications): Outbound dispatch requests and persistent delivery audit records
- DevicePushToken (device_push_tokens): FCM device tokens for mobile push delivery
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from services.api.auth.models import User  # noqa: F401
from services.api.database import Base
from services.api.devices.models import Device  # noqa: F401
from services.api.employees.models import Employee  # noqa: F401
from services.api.organization.models import Department  # noqa: F401
from services.api.tenants.models import Tenant  # noqa: F401


class NotificationTemplate(Base):
    """System-defined or tenant-customizable notification template."""

    __tablename__ = "notification_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    template_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    channel: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    subject_template: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    body_template: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    locale: Mapped[str] = mapped_column(
        String(10),
        default="en",
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "channel IN ('PUSH', 'EMAIL', 'SMS')",
            name="chk_notification_templates_channel",
        ),
        CheckConstraint(
            "(is_system = true AND tenant_id IS NULL) OR (is_system = false AND tenant_id IS NOT NULL)",
            name="chk_notification_templates_system_tenant",
        ),
        Index(
            "uq_notification_templates_tenant",
            "tenant_id",
            "template_key",
            "channel",
            "locale",
            unique=True,
            postgresql_where=text("tenant_id IS NOT NULL"),
        ),
        Index(
            "uq_notification_templates_system",
            "template_key",
            "channel",
            "locale",
            unique=True,
            postgresql_where=text("tenant_id IS NULL"),
        ),
        Index(
            "ix_notification_templates_lookup",
            "tenant_id",
            "event_type",
            "channel",
            "is_active",
        ),
    )

    # Relationships
    tenant = relationship("Tenant", foreign_keys=[tenant_id])
    created_by_user = relationship("User", foreign_keys=[created_by_user_id])
    updated_by_user = relationship("User", foreign_keys=[updated_by_user_id])

    def __repr__(self) -> str:
        return (
            f"<NotificationTemplate id={self.id} key={self.template_key} "
            f"channel={self.channel} tenant_id={self.tenant_id} is_system={self.is_system}>"
        )


class NotificationPreference(Base):
    """Tenant-level default and user-level override notification preferences."""

    __tablename__ = "notification_preferences"

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
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    is_push_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    is_email_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    is_sms_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    quiet_hours_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    quiet_hours_start: Mapped[str | None] = mapped_column(
        String(5),  # 24h format "HH:MM" e.g. "22:00"
        nullable=True,
    )
    quiet_hours_end: Mapped[str | None] = mapped_column(
        String(5),  # 24h format "HH:MM" e.g. "07:00"
        nullable=True,
    )
    timezone: Mapped[str] = mapped_column(
        String(50),
        default="UTC",
        nullable=False,
    )
    category_preferences: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "uq_notification_preferences_user",
            "tenant_id",
            "user_id",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
        ),
        Index(
            "uq_notification_preferences_tenant_default",
            "tenant_id",
            unique=True,
            postgresql_where=text("user_id IS NULL"),
        ),
    )

    # Relationships
    tenant = relationship("Tenant", foreign_keys=[tenant_id])
    user = relationship("User", foreign_keys=[user_id])

    def __repr__(self) -> str:
        return (
            f"<NotificationPreference id={self.id} tenant_id={self.tenant_id} "
            f"user_id={self.user_id} push={self.is_push_enabled} email={self.is_email_enabled} sms={self.is_sms_enabled}>"
        )


class Notification(Base):
    """Outbound notification dispatch request and permanent delivery audit record."""

    __tablename__ = "notifications"

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
    recipient_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    recipient_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    channel: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notification_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    template_key: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
    recipient_destination: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    subject: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    body: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="PENDING",
        nullable=False,
    )
    priority: Mapped[str] = mapped_column(
        String(20),
        default="NORMAL",
        nullable=False,
    )
    scheduled_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        default=3,
        nullable=False,
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    provider_name: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    provider_message_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    provider_response: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )
    related_entity_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    related_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "channel IN ('PUSH', 'EMAIL', 'SMS')",
            name="chk_notifications_channel",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'RETRY_SCHEDULED', 'SENT', 'DELIVERED', 'FAILED', 'CANCELLED')",
            name="chk_notifications_status",
        ),
        CheckConstraint(
            "priority IN ('LOW', 'NORMAL', 'HIGH', 'URGENT')",
            name="chk_notifications_priority",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="chk_notifications_attempt_count",
        ),
        CheckConstraint(
            "max_attempts > 0",
            name="chk_notifications_max_attempts",
        ),
        Index(
            "uq_notifications_tenant_idempotency",
            "tenant_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index(
            "ix_notifications_worker_queue",
            "status",
            "scheduled_for",
            "priority",
        ),
        Index(
            "ix_notifications_recipient_user",
            "tenant_id",
            "recipient_user_id",
            "created_at",
        ),
        Index(
            "ix_notifications_recipient_employee",
            "tenant_id",
            "recipient_employee_id",
            "created_at",
        ),
        Index(
            "ix_notifications_related_entity",
            "tenant_id",
            "related_entity_type",
            "related_entity_id",
        ),
    )

    # Relationships
    tenant = relationship("Tenant", foreign_keys=[tenant_id])
    recipient_user = relationship("User", foreign_keys=[recipient_user_id])
    recipient_employee = relationship("Employee", foreign_keys=[recipient_employee_id])
    template = relationship("NotificationTemplate", foreign_keys=[template_id])

    def __repr__(self) -> str:
        return (
            f"<Notification id={self.id} tenant_id={self.tenant_id} event={self.event_type} "
            f"channel={self.channel} status={self.status} priority={self.priority}>"
        )


class DevicePushToken(Base):
    """FCM device registration token for mobile push notifications."""

    __tablename__ = "device_push_tokens"

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
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    platform: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    token: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    device_model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    os_version: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    app_version: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="ACTIVE",
        nullable=False,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "platform IN ('ANDROID', 'IOS', 'WEB')",
            name="chk_device_push_tokens_platform",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'REVOKED', 'EXPIRED')",
            name="chk_device_push_tokens_status",
        ),
        Index(
            "uq_device_push_tokens_active_token",
            "token_hash",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index(
            "ix_device_push_tokens_user_status",
            "tenant_id",
            "user_id",
            "status",
        ),
        Index(
            "ix_device_push_tokens_employee_status",
            "tenant_id",
            "employee_id",
            "status",
        ),
    )

    # Relationships
    tenant = relationship("Tenant", foreign_keys=[tenant_id])
    user = relationship("User", foreign_keys=[user_id])
    employee = relationship("Employee", foreign_keys=[employee_id])
    device = relationship("Device", foreign_keys=[device_id])

    def __repr__(self) -> str:
        return (
            f"<DevicePushToken id={self.id} tenant_id={self.tenant_id} user_id={self.user_id} "
            f"platform={self.platform} status={self.status}>"
        )
