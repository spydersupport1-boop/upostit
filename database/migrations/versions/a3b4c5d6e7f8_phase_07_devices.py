"""Phase 7 Milestone 7.1: Employee Device Registration and Hardware Binding Subsystem.

Revision ID: a3b4c5d6e7f8
Revises: c4d5e6f7a8b9
Create Date: 2026-11-19 03:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a3b4c5d6e7f8"
down_revision: str | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create devices table
    op.create_table(
        "devices",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("device_id_hash", sa.String(length=128), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("device_model", sa.String(length=100), nullable=True),
        sa.Column("os_name", sa.String(length=50), nullable=True),
        sa.Column("os_version", sa.String(length=50), nullable=True),
        sa.Column("app_version", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", sa.UUID(), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.Column("replacement_for_device_id", sa.UUID(), nullable=True),
        sa.Column("replacement_approved_by_user_id", sa.UUID(), nullable=True),
        sa.Column("replacement_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_devices_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "device_id_hash", name="uq_devices_tenant_device_hash"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="RESTRICT"
        ),
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
        sa.CheckConstraint(
            "platform IN ('ANDROID', 'IOS', 'WEB', 'OTHER')",
            name="chk_devices_platform",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING_APPROVAL', 'ACTIVE', 'REVOKED', 'REPLACED')",
            name="chk_devices_status",
        ),
    )

    # 2. Enforce single active device per employee under tenant policy
    op.create_index(
        "ix_devices_tenant_emp_active",
        "devices",
        ["tenant_id", "employee_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    # 3. Fast lookup indexes for administrative and punch evaluation queries
    op.create_index(
        "ix_devices_tenant_status",
        "devices",
        ["tenant_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_devices_tenant_employee",
        "devices",
        ["tenant_id", "employee_id"],
        unique=False,
    )

    # 4. Enable and enforce Row-Level Security
    op.execute("ALTER TABLE devices ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE devices FORCE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY tenant_isolation ON devices
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
    """)

    # 5. Grant permissions to application roles
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON devices TO authenticated, service_role;"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON devices;")
    op.drop_table("devices")

