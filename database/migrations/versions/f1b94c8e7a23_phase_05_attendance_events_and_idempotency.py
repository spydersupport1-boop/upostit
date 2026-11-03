"""Phase 5 Milestone 2: Attendance events ledger and idempotency records.

Revision ID: f1b94c8e7a23
Revises: e9f63b02a145
Create Date: 2026-11-03 08:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f1b94c8e7a23'
down_revision: str | None = 'e9f63b02a145'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create attendance_events table (Append-only Presence Ledger)
    op.create_table(
        'attendance_events',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('employee_id', sa.UUID(), nullable=False),
        sa.Column('event_type', sa.String(length=30), nullable=False),
        sa.Column('event_category', sa.String(length=30), server_default='STANDARD', nullable=False),
        sa.Column('supersedes_event_id', sa.UUID(), nullable=True),
        sa.Column('correction_reason', sa.Text(), nullable=True),
        sa.Column('server_received_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('device_reported_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('effective_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('clock_drift_seconds', sa.Numeric(precision=10, scale=3), server_default='0.000', nullable=True),
        sa.Column('source', sa.String(length=20), server_default='WEB', nullable=False),
        sa.Column('device_id', sa.String(length=128), nullable=True),
        sa.Column('timestamp_verification_status', sa.String(length=30), server_default='SERVER_AUTHORITATIVE', nullable=False),
        sa.Column('review_status', sa.String(length=30), server_default='NOT_REQUIRED', nullable=False),
        sa.Column('idempotency_key', sa.String(length=64), nullable=False),
        sa.Column('location_id', sa.UUID(), nullable=True),
        sa.Column('latitude', sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column('longitude', sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column('accuracy_meters', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('actor_user_id', sa.UUID(), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'id', name='uq_attendance_events_tenant_id'),
        sa.UniqueConstraint('tenant_id', 'idempotency_key', name='uq_attendance_events_tenant_idempotency'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'employee_id'],
            ['employees.tenant_id', 'employees.id'],
            name='fk_attendance_events_employee',
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'location_id'],
            ['locations.tenant_id', 'locations.id'],
            name='fk_attendance_events_location',
            ondelete='SET NULL (location_id)',
        ),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'actor_user_id'],
            ['users.tenant_id', 'users.id'],
            name='fk_attendance_events_actor',
            ondelete='SET NULL (actor_user_id)',
        ),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'supersedes_event_id'],
            ['attendance_events.tenant_id', 'attendance_events.id'],
            name='fk_attendance_events_supersedes',
            ondelete='RESTRICT',
        ),
        sa.CheckConstraint(
            "event_type IN ('CHECK_IN', 'CHECK_OUT', 'BREAK_START', 'BREAK_END')",
            name='chk_attendance_events_type',
        ),
        sa.CheckConstraint(
            "event_category IN ('STANDARD', 'CORRECTION_INSERT', 'CORRECTION_SUPERSEDE', 'CORRECTION_VOID')",
            name='chk_attendance_events_category',
        ),
        sa.CheckConstraint(
            "source IN ('WEB', 'MOBILE', 'BIOMETRIC', 'CCTV', 'ADMIN', 'DEVICE', 'API')",
            name='chk_attendance_events_source',
        ),
        sa.CheckConstraint(
            "timestamp_verification_status IN ('SERVER_AUTHORITATIVE', 'DEVICE_VERIFIED_NTP', 'SUSPICIOUS_CLOCK_DRIFT', 'UNVERIFIED_OFFLINE')",
            name='chk_attendance_events_verification',
        ),
        sa.CheckConstraint(
            "review_status IN ('NOT_REQUIRED', 'PENDING_REVIEW', 'FLAGGED', 'APPROVED', 'REJECTED')",
            name='chk_attendance_events_review',
        ),
        sa.CheckConstraint(
            "event_category = 'STANDARD' OR (correction_reason IS NOT NULL AND length(trim(correction_reason)) >= 5)",
            name='chk_attendance_events_correction_reason',
        ),
        sa.CheckConstraint(
            "(event_category IN ('CORRECTION_SUPERSEDE', 'CORRECTION_VOID') AND supersedes_event_id IS NOT NULL) OR "
            "(event_category IN ('STANDARD', 'CORRECTION_INSERT') AND supersedes_event_id IS NULL)",
            name='chk_attendance_events_supersedes_link',
        ),
    )

    op.create_index(
        'ix_attendance_events_tenant_emp_eff',
        'attendance_events',
        ['tenant_id', 'employee_id', 'effective_at'],
        unique=False,
    )
    op.create_index(
        'ix_attendance_events_tenant_superseded',
        'attendance_events',
        ['tenant_id', 'supersedes_event_id'],
        unique=False,
        postgresql_where=sa.text('supersedes_event_id IS NOT NULL'),
    )
    op.create_index(
        'ix_attendance_events_tenant_created',
        'attendance_events',
        ['tenant_id', 'created_at'],
        unique=False,
    )

    # Enable and force Row-Level Security on attendance_events
    op.execute("ALTER TABLE attendance_events ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE attendance_events FORCE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY tenant_isolation ON attendance_events
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
    """)

    # Immutability Trigger: Prohibit UPDATE and DELETE on attendance_events
    op.execute("""
        CREATE OR REPLACE FUNCTION trg_attendance_events_immutability()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'attendance_events is an append-only ledger. UPDATE and DELETE operations are strictly prohibited.'
                USING ERRCODE = 'integrity_constraint_violation';
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_prevent_attendance_events_mutation
            BEFORE UPDATE OR DELETE ON attendance_events
            FOR EACH ROW
            EXECUTE FUNCTION trg_attendance_events_immutability();
    """)

    # 2. Create attendance_idempotency_records table
    op.create_table(
        'attendance_idempotency_records',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('employee_id', sa.UUID(), nullable=False),
        sa.Column('idempotency_key', sa.String(length=64), nullable=False),
        sa.Column('request_fingerprint', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='IN_PROGRESS', nullable=False),
        sa.Column('response_code', sa.Integer(), nullable=True),
        sa.Column('response_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('event_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'id', name='uq_idempotency_tenant_id'),
        sa.UniqueConstraint('tenant_id', 'idempotency_key', name='uq_idempotency_tenant_key'),
        sa.UniqueConstraint('tenant_id', 'employee_id', 'idempotency_key', name='uq_idempotency_tenant_emp_key'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'employee_id'],
            ['employees.tenant_id', 'employees.id'],
            name='fk_idempotency_employee',
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'event_id'],
            ['attendance_events.tenant_id', 'attendance_events.id'],
            name='fk_idempotency_event',
            ondelete='SET NULL (event_id)',
        ),
        sa.CheckConstraint(
            "status IN ('IN_PROGRESS', 'COMPLETED', 'FAILED')",
            name='chk_idempotency_status',
        ),
    )

    op.create_index(
        'ix_idempotency_tenant_expires',
        'attendance_idempotency_records',
        ['tenant_id', 'expires_at'],
        unique=False,
        postgresql_where=sa.text('expires_at IS NOT NULL'),
    )
    op.create_index(
        'ix_idempotency_tenant_emp',
        'attendance_idempotency_records',
        ['tenant_id', 'employee_id'],
        unique=False,
    )

    # Enable and force Row-Level Security on attendance_idempotency_records
    op.execute("ALTER TABLE attendance_idempotency_records ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE attendance_idempotency_records FORCE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY tenant_isolation ON attendance_idempotency_records
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
    """)

    # Grant permissions: attendance_events is strictly append-only (SELECT, INSERT only)
    op.execute("GRANT SELECT, INSERT ON attendance_events TO authenticated, service_role;")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON attendance_idempotency_records TO authenticated, service_role;")


def downgrade() -> None:
    # 1. Drop attendance_idempotency_records
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON attendance_idempotency_records;")
    op.drop_table('attendance_idempotency_records')

    # 2. Drop attendance_events and immutability trigger
    op.execute("DROP TRIGGER IF EXISTS trg_prevent_attendance_events_mutation ON attendance_events;")
    op.execute("DROP FUNCTION IF EXISTS trg_attendance_events_immutability();")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON attendance_events;")
    op.drop_table('attendance_events')
