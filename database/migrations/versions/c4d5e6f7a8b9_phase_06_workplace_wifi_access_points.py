"""Phase 6 Milestone 6.4.A: Workplace Wi-Fi Access Points and Attendance Verification.

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-11-05 23:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: str | None = "b3c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create workplace_wifi_access_points table
    op.create_table(
        "workplace_wifi_access_points",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("location_id", sa.UUID(), nullable=False),
        sa.Column("friendly_name", sa.String(length=100), nullable=False),
        sa.Column("bssid", sa.String(length=17), nullable=False),
        sa.Column("ssid", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("effective_from", sa.Date(), server_default=sa.text("CURRENT_DATE"), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
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
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "location_id"],
            ["locations.tenant_id", "locations.id"],
            name="fk_workplace_wifi_location",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_workplace_wifi_creator",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "tenant_id", "location_id", "bssid", name="uq_workplace_wifi_location_bssid"
        ),
        sa.CheckConstraint(
            "bssid ~ '^([0-9A-F]{2}:){5}[0-9A-F]{2}$'",
            name="chk_workplace_wifi_bssid_format",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="chk_workplace_wifi_dates",
        ),
    )

    op.create_index(
        "ix_workplace_wifi_tenant_location_active",
        "workplace_wifi_access_points",
        ["tenant_id", "location_id", "is_active"],
        unique=False,
    )
    op.create_index(
        "ix_workplace_wifi_tenant_bssid",
        "workplace_wifi_access_points",
        ["tenant_id", "bssid"],
        unique=False,
    )

    # 2. Add wifi_config_override to locations
    op.add_column(
        "locations",
        sa.Column(
            "wifi_config_override",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
    )

    # 3. Add wifi_bssid and wifi_ssid to attendance_events for audit traceability
    op.add_column(
        "attendance_events",
        sa.Column("wifi_bssid", sa.String(length=17), nullable=True),
    )
    op.add_column(
        "attendance_events",
        sa.Column("wifi_ssid", sa.String(length=64), nullable=True),
    )

    # 4. Enable and force Row-Level Security on workplace_wifi_access_points
    op.execute("ALTER TABLE workplace_wifi_access_points ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE workplace_wifi_access_points FORCE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY tenant_isolation ON workplace_wifi_access_points
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
    """)

    # 5. Grant DML permissions to authenticated and service_role
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON workplace_wifi_access_points TO authenticated, service_role;"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON workplace_wifi_access_points;")
    op.drop_table("workplace_wifi_access_points")
    op.drop_column("locations", "wifi_config_override")
    op.drop_column("attendance_events", "wifi_ssid")
    op.drop_column("attendance_events", "wifi_bssid")

