"""Phase 6 Milestone 6.3.A: Tenant attendance policies table and event policy tracking.

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-11-05 01:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b3c4d5e6f7a8"
down_revision: str | None = "a2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create tenant_attendance_policies table
    op.create_table(
        "tenant_attendance_policies",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("default_mode", sa.String(length=30), server_default="MANUAL", nullable=False),
        sa.Column(
            "allowed_methods",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default='["MANUAL"]',
            nullable=False,
        ),
        sa.Column(
            "required_methods",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default='["MANUAL"]',
            nullable=False,
        ),
        sa.Column("combination_rule", sa.String(length=20), server_default="OR", nullable=False),
        sa.Column(
            "fallback_policy",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "gps_config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default='{"max_accuracy_meters": 100, "max_location_age_seconds": 30, "enforce_assigned_workplace": true, "out_of_geofence_action": "REJECT"}',
            nullable=False,
        ),
        sa.Column(
            "wifi_config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "biometric_config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "face_config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "version", name="uq_tenant_attendance_policy_tenant_version"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_tenant_attendance_policy_tenant_id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_tenant_attendance_policy_creator",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "default_mode IN ('MANUAL', 'GPS_ONLY', 'WIFI_ONLY', 'BIOMETRIC_ONLY', 'FACE_RECOGNITION', 'COMBINED')",
            name="chk_tenant_attendance_policy_default_mode",
        ),
        sa.CheckConstraint(
            "combination_rule IN ('AND', 'OR', 'PRIMARY_WITH_FALLBACK')",
            name="chk_tenant_attendance_policy_combination_rule",
        ),
    )

    op.create_index(
        "ix_tenant_attendance_policies_tenant_active",
        "tenant_attendance_policies",
        ["tenant_id", "is_active"],
        unique=False,
    )

    # 2. Enforce only one active policy per tenant via partial unique index
    op.execute(
        "CREATE UNIQUE INDEX uq_tenant_attendance_policy_one_active "
        "ON tenant_attendance_policies (tenant_id) WHERE is_active = true;"
    )

    # 3. Add applied_policy_version to attendance_events for audit traceability
    op.add_column(
        "attendance_events",
        sa.Column("applied_policy_version", sa.Integer(), nullable=True),
    )

    # 4. Enable and force Row-Level Security on tenant_attendance_policies
    op.execute("ALTER TABLE tenant_attendance_policies ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE tenant_attendance_policies FORCE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY tenant_isolation ON tenant_attendance_policies
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
    """)

    # 5. Grant DML permissions to authenticated and service_role
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON tenant_attendance_policies TO authenticated, service_role;"
    )

    # 6. Seed initial active MANUAL policy for all existing tenants (zero disruption)
    op.execute("""
        INSERT INTO tenant_attendance_policies (
            id, tenant_id, version, is_active, default_mode,
            allowed_methods, required_methods, combination_rule,
            fallback_policy, gps_config, wifi_config, biometric_config, face_config,
            created_at, updated_at
        )
        SELECT
            gen_random_uuid(),
            id,
            1,
            true,
            'MANUAL',
            '["MANUAL"]'::jsonb,
            '["MANUAL"]'::jsonb,
            'OR',
            '{}'::jsonb,
            '{"max_accuracy_meters": 100, "max_location_age_seconds": 30, "enforce_assigned_workplace": true, "out_of_geofence_action": "REJECT"}'::jsonb,
            '{}'::jsonb,
            '{}'::jsonb,
            '{}'::jsonb,
            now(),
            now()
        FROM tenants
        ON CONFLICT DO NOTHING;
    """)


def downgrade() -> None:
    op.drop_column("attendance_events", "applied_policy_version")
    op.execute("DROP INDEX IF EXISTS uq_tenant_attendance_policy_one_active;")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON tenant_attendance_policies;")
    op.drop_table("tenant_attendance_policies")
