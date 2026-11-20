"""Phase 7 Milestone 7.3: Fraud Rule Engine & Immutable Fraud Flags Subsystem.

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-11-19 04:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c5d6e7f8a9b0"
down_revision: str | None = "b4c5d6e7f8a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create fraud_rules table
    op.create_table(
        "fraud_rules",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("rule_code", sa.String(length=64), nullable=False),
        sa.Column("rule_name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("severity", sa.String(length=20), server_default="HIGH", nullable=False),
        sa.Column("risk_weight", sa.Integer(), server_default="25", nullable=False),
        sa.Column(
            "threshold_config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("review_required", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "rule_code", name="uq_fraud_rules_tenant_rule_code"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fraud_rules_tenant_id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
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
    )

    op.create_index(
        "ix_fraud_rules_tenant_id",
        "fraud_rules",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_fraud_rules_tenant_enabled",
        "fraud_rules",
        ["tenant_id", "enabled"],
        unique=False,
    )

    # Enable and force Row-Level Security on fraud_rules
    op.execute("ALTER TABLE fraud_rules ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE fraud_rules FORCE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY tenant_isolation ON fraud_rules
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
    """)
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON fraud_rules TO authenticated, service_role;"
    )

    # 2. Create fraud_flags table
    op.create_table(
        "fraud_flags",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("attendance_event_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("device_id", sa.UUID(), nullable=True),
        sa.Column("rule_id", sa.UUID(), nullable=True),
        sa.Column("signal_code", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("risk_weight", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "evidence_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fraud_flags_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "attendance_event_id",
            "signal_code",
            name="uq_fraud_flags_tenant_event_signal",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
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
    )

    op.create_index(
        "ix_fraud_flags_tenant_emp",
        "fraud_flags",
        ["tenant_id", "employee_id"],
        unique=False,
    )
    op.create_index(
        "ix_fraud_flags_tenant_event",
        "fraud_flags",
        ["tenant_id", "attendance_event_id"],
        unique=False,
    )
    op.create_index(
        "ix_fraud_flags_tenant_severity",
        "fraud_flags",
        ["tenant_id", "severity"],
        unique=False,
    )
    op.create_index(
        "ix_fraud_flags_tenant_detected",
        "fraud_flags",
        ["tenant_id", "detected_at"],
        unique=False,
    )
    op.create_index(
        "ix_fraud_flags_tenant_signal",
        "fraud_flags",
        ["tenant_id", "signal_code"],
        unique=False,
    )

    # Enable and force Row-Level Security on fraud_flags
    op.execute("ALTER TABLE fraud_flags ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE fraud_flags FORCE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY tenant_isolation ON fraud_flags
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
    """)
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON fraud_flags TO authenticated, service_role;"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON fraud_flags;")
    op.drop_table("fraud_flags")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON fraud_rules;")
    op.drop_table("fraud_rules")

