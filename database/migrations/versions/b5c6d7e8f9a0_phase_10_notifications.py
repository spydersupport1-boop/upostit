"""Phase 10 Milestone 10.1: Notification Database Architecture, Models & RLS.

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-11-21 14:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "b5c6d7e8f9a0"
down_revision: str | None = "a4b5c6d7e8f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # =========================================================================
    # 1. Create notification_templates table
    # =========================================================================
    op.create_table(
        "notification_templates",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=True),
        sa.Column("template_key", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("channel", sa.String(length=30), nullable=False),
        sa.Column("subject_template", sa.String(length=255), nullable=True),
        sa.Column("body_template", sa.Text(), nullable=False),
        sa.Column("locale", sa.String(length=10), server_default="en", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_system", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_by_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by_user_id", UUID(as_uuid=True), nullable=True),
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
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "channel IN ('PUSH', 'EMAIL', 'SMS')",
            name="chk_notification_templates_channel",
        ),
        sa.CheckConstraint(
            "(is_system = true AND tenant_id IS NULL) OR (is_system = false AND tenant_id IS NOT NULL)",
            name="chk_notification_templates_system_tenant",
        ),
    )

    op.create_index(
        "ix_notification_templates_tenant_id",
        "notification_templates",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_notification_templates_key",
        "notification_templates",
        ["template_key"],
        unique=False,
    )
    op.create_index(
        "ix_notification_templates_event_type",
        "notification_templates",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        "ix_notification_templates_lookup",
        "notification_templates",
        ["tenant_id", "event_type", "channel", "is_active"],
        unique=False,
    )
    op.create_index(
        "uq_notification_templates_tenant",
        "notification_templates",
        ["tenant_id", "template_key", "channel", "locale"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NOT NULL"),
    )
    op.create_index(
        "uq_notification_templates_system",
        "notification_templates",
        ["template_key", "channel", "locale"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NULL"),
    )

    # =========================================================================
    # 2. Create notification_preferences table
    # =========================================================================
    op.create_table(
        "notification_preferences",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("is_push_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_email_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_sms_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("quiet_hours_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("quiet_hours_start", sa.String(length=5), nullable=True),
        sa.Column("quiet_hours_end", sa.String(length=5), nullable=True),
        sa.Column("timezone", sa.String(length=50), server_default="UTC", nullable=False),
        sa.Column("category_preferences", JSONB, server_default="{}", nullable=True),
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
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_index(
        "ix_notification_preferences_tenant_id",
        "notification_preferences",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_notification_preferences_user_id",
        "notification_preferences",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "uq_notification_preferences_user",
        "notification_preferences",
        ["tenant_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.create_index(
        "uq_notification_preferences_tenant_default",
        "notification_preferences",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NULL"),
    )

    # =========================================================================
    # 3. Create notifications table
    # =========================================================================
    op.create_table(
        "notifications",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("recipient_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("recipient_employee_id", UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("channel", sa.String(length=30), nullable=False),
        sa.Column("template_id", UUID(as_uuid=True), nullable=True),
        sa.Column("template_key", sa.String(length=100), nullable=True),
        sa.Column("recipient_destination", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("payload_json", JSONB, server_default="{}", nullable=True),
        sa.Column("status", sa.String(length=30), server_default="PENDING", nullable=False),
        sa.Column("priority", sa.String(length=20), server_default="NORMAL", nullable=False),
        sa.Column(
            "scheduled_for",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_name", sa.String(length=50), nullable=True),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("provider_response", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("related_entity_type", sa.String(length=50), nullable=True),
        sa.Column("related_entity_id", UUID(as_uuid=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recipient_employee_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["template_id"], ["notification_templates.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "channel IN ('PUSH', 'EMAIL', 'SMS')",
            name="chk_notifications_channel",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'RETRY_SCHEDULED', 'SENT', 'DELIVERED', 'FAILED', 'CANCELLED')",
            name="chk_notifications_status",
        ),
        sa.CheckConstraint(
            "priority IN ('LOW', 'NORMAL', 'HIGH', 'URGENT')",
            name="chk_notifications_priority",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="chk_notifications_attempt_count",
        ),
        sa.CheckConstraint(
            "max_attempts > 0",
            name="chk_notifications_max_attempts",
        ),
    )

    op.create_index("ix_notifications_tenant_id", "notifications", ["tenant_id"], unique=False)
    op.create_index("ix_notifications_tenant_status", "notifications", ["tenant_id", "status"], unique=False)
    op.create_index(
        "ix_notifications_worker_queue",
        "notifications",
        ["status", "scheduled_for", "priority"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_recipient_user",
        "notifications",
        ["tenant_id", "recipient_user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_recipient_employee",
        "notifications",
        ["tenant_id", "recipient_employee_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_related_entity",
        "notifications",
        ["tenant_id", "related_entity_type", "related_entity_id"],
        unique=False,
    )
    op.create_index(
        "uq_notifications_tenant_idempotency",
        "notifications",
        ["tenant_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    # =========================================================================
    # 4. Create device_push_tokens table
    # =========================================================================
    op.create_table(
        "device_push_tokens",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", UUID(as_uuid=True), nullable=True),
        sa.Column("device_id", UUID(as_uuid=True), nullable=True),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("token", sa.String(length=512), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("device_model", sa.String(length=100), nullable=True),
        sa.Column("os_version", sa.String(length=50), nullable=True),
        sa.Column("app_version", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="ACTIVE", nullable=False),
        sa.Column(
            "last_seen_at",
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "platform IN ('ANDROID', 'IOS', 'WEB')",
            name="chk_device_push_tokens_platform",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'REVOKED', 'EXPIRED')",
            name="chk_device_push_tokens_status",
        ),
    )

    op.create_index("ix_device_push_tokens_tenant_id", "device_push_tokens", ["tenant_id"], unique=False)
    op.create_index("ix_device_push_tokens_token_hash", "device_push_tokens", ["token_hash"], unique=False)
    op.create_index(
        "ix_device_push_tokens_user_status",
        "device_push_tokens",
        ["tenant_id", "user_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_device_push_tokens_employee_status",
        "device_push_tokens",
        ["tenant_id", "employee_id", "status"],
        unique=False,
    )
    op.create_index(
        "uq_device_push_tokens_active_token",
        "device_push_tokens",
        ["token_hash"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    # =========================================================================
    # 5. Row-Level Security (RLS) Policies
    # =========================================================================
    # 5.1 notification_templates RLS
    op.execute("ALTER TABLE notification_templates ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE notification_templates FORCE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY tenant_isolation_read ON notification_templates
            FOR SELECT
            USING (
                tenant_id IS NULL
                OR tenant_id = current_setting('app.tenant_id', true)::uuid
            );
    """)
    op.execute("""
        CREATE POLICY tenant_isolation_write ON notification_templates
            FOR ALL
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
    """)
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON notification_templates TO authenticated, service_role;")

    # 5.2 notification_preferences RLS
    op.execute("ALTER TABLE notification_preferences ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE notification_preferences FORCE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY tenant_isolation ON notification_preferences
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
    """)
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON notification_preferences TO authenticated, service_role;")

    # 5.3 notifications RLS
    op.execute("ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE notifications FORCE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY tenant_isolation ON notifications
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
    """)
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON notifications TO authenticated, service_role;")

    # 5.4 device_push_tokens RLS
    op.execute("ALTER TABLE device_push_tokens ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE device_push_tokens FORCE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY tenant_isolation ON device_push_tokens
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
    """)
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON device_push_tokens TO authenticated, service_role;")


def downgrade() -> None:
    phase10_tables_reversed = [
        "device_push_tokens",
        "notifications",
        "notification_preferences",
        "notification_templates",
    ]

    for table in phase10_tables_reversed:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_read ON {table};")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_write ON {table};")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table};")
        op.drop_table(table)
