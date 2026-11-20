"""SQLAlchemy models for tenant fraud rules and immutable fraud evidence flags."""

import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from services.api.database import Base


class FraudRule(Base):
    """Tenant-configurable fraud detection rule and risk-weight assignment."""

    __tablename__ = "fraud_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    rule_code: Mapped[str] = mapped_column(
        sa.String(64),
        nullable=False,
    )
    rule_name: Mapped[str] = mapped_column(
        sa.String(128),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        sa.Text,
        nullable=True,
    )
    enabled: Mapped[bool] = mapped_column(
        sa.Boolean,
        default=True,
        nullable=False,
    )
    severity: Mapped[str] = mapped_column(
        sa.String(20),
        default="HIGH",
        nullable=False,
    )
    risk_weight: Mapped[int] = mapped_column(
        sa.Integer,
        default=25,
        nullable=False,
    )
    threshold_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )
    review_required: Mapped[bool] = mapped_column(
        sa.Boolean,
        default=False,
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
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "rule_code", name="uq_fraud_rules_tenant_rule_code"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fraud_rules_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by"],
            ["users.tenant_id", "users.id"],
            name="fk_fraud_rules_created_by",
            ondelete="SET NULL (created_by)",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "updated_by"],
            ["users.tenant_id", "users.id"],
            name="fk_fraud_rules_updated_by",
            ondelete="SET NULL (updated_by)",
        ),
        sa.CheckConstraint(
            "severity IN ('INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="chk_fraud_rules_severity",
        ),
        sa.CheckConstraint(
            "risk_weight >= 0 AND risk_weight <= 100",
            name="chk_fraud_rules_risk_weight",
        ),
        sa.Index("ix_fraud_rules_tenant_enabled", "tenant_id", "enabled"),
    )


class FraudFlag(Base):
    """Immutable forensic evidence flag linked to an attendance punch event."""

    __tablename__ = "fraud_flags"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    attendance_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    signal_code: Mapped[str] = mapped_column(
        sa.String(64),
        nullable=False,
        index=True,
    )
    severity: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        index=True,
    )
    risk_weight: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
    )
    evidence_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )
    detected_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "id", name="uq_fraud_flags_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "attendance_event_id",
            "signal_code",
            name="uq_fraud_flags_tenant_event_signal",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "attendance_event_id"],
            ["attendance_events.tenant_id", "attendance_events.id"],
            name="fk_fraud_flags_event",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            name="fk_fraud_flags_employee",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "device_id"],
            ["devices.tenant_id", "devices.id"],
            name="fk_fraud_flags_device",
            ondelete="SET NULL (device_id)",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "rule_id"],
            ["fraud_rules.tenant_id", "fraud_rules.id"],
            name="fk_fraud_flags_rule",
            ondelete="SET NULL (rule_id)",
        ),
        sa.CheckConstraint(
            "severity IN ('INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="chk_fraud_flags_severity",
        ),
        sa.CheckConstraint(
            "risk_weight >= 0 AND risk_weight <= 100",
            name="chk_fraud_flags_risk_weight",
        ),
        sa.Index("ix_fraud_flags_tenant_emp", "tenant_id", "employee_id"),
        sa.Index("ix_fraud_flags_tenant_event", "tenant_id", "attendance_event_id"),
        sa.Index("ix_fraud_flags_tenant_severity", "tenant_id", "severity"),
        sa.Index("ix_fraud_flags_tenant_detected", "tenant_id", "detected_at"),
    )


class FraudReview(Base):
    """Immutable audit record of human HR/Admin adjudication for a flagged attendance event."""

    __tablename__ = "fraud_reviews"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    attendance_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    reviewer_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    reviewer_role: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(
        sa.Text,
        nullable=True,
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )
    decided_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "id", name="uq_fraud_reviews_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "attendance_event_id"],
            ["attendance_events.tenant_id", "attendance_events.id"],
            name="fk_fraud_reviews_event",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "reviewer_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_fraud_reviews_reviewer",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "decision IN ('APPROVED', 'REJECTED')",
            name="chk_fraud_reviews_decision",
        ),
        sa.CheckConstraint(
            "length(trim(reason)) >= 3",
            name="chk_fraud_reviews_reason",
        ),
        sa.Index("ix_fraud_reviews_tenant_event", "tenant_id", "attendance_event_id"),
        sa.Index("ix_fraud_reviews_tenant_reviewer", "tenant_id", "reviewer_user_id"),
        sa.Index("ix_fraud_reviews_tenant_decision", "tenant_id", "decision"),
        sa.Index("ix_fraud_reviews_tenant_decided", "tenant_id", "decided_at"),
    )


