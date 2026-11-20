"""Phase 8 Milestone 8.1: Attendance Conflict Incidents & Review Subsystem.

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-11-20 01:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e7f8a9b0c1d2"
down_revision: str | None = "d6e7f8a9b0c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create attendance_conflict_incidents table
    op.create_table(
        "attendance_conflict_incidents",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("bundle_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="PENDING_REVIEW",
            nullable=False,
        ),
        sa.Column(
            "primary_rejected_event",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "dependent_events",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "total_events_count",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        sa.Column("rejection_summary", sa.String(length=255), nullable=True),
        sa.Column("employee_notes", sa.Text(), nullable=True),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("assigned_reviewer_id", sa.UUID(), nullable=True),
        sa.Column("decision", sa.String(length=32), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("reviewer_user_id", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "resolved_correction_event_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_conflict_incidents_tenant_id"),
        sa.UniqueConstraint("tenant_id", "bundle_id", name="uq_conflict_incidents_tenant_bundle"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            name="fk_conflict_incidents_employee",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_conflict_incidents_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "assigned_reviewer_id"],
            ["users.tenant_id", "users.id"],
            name="fk_conflict_incidents_assigned_reviewer",
            ondelete="SET NULL (assigned_reviewer_id)",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "reviewer_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_conflict_incidents_reviewer",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING_REVIEW', 'APPROVED', 'REJECTED')",
            name="chk_conflict_incidents_status",
        ),
        sa.CheckConstraint(
            "decision IS NULL OR decision IN ('APPROVED', 'REJECTED')",
            name="chk_conflict_incidents_decision",
        ),
        sa.CheckConstraint(
            "decision IS NULL OR length(trim(decision_reason)) >= 3",
            name="chk_conflict_incidents_reason",
        ),
        sa.CheckConstraint(
            "(status = 'PENDING_REVIEW' AND decision IS NULL AND decided_at IS NULL AND reviewer_user_id IS NULL) OR "
            "(status = 'APPROVED' AND decision = 'APPROVED' AND decided_at IS NOT NULL AND reviewer_user_id IS NOT NULL) OR "
            "(status = 'REJECTED' AND decision = 'REJECTED' AND decided_at IS NOT NULL AND reviewer_user_id IS NOT NULL)",
            name="chk_conflict_incidents_status_decision",
        ),
    )

    # 2. Performance & scoping indexes
    op.create_index(
        "ix_conflict_incidents_tenant_status",
        "attendance_conflict_incidents",
        ["tenant_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_conflict_incidents_tenant_employee",
        "attendance_conflict_incidents",
        ["tenant_id", "employee_id"],
        unique=False,
    )
    op.create_index(
        "ix_conflict_incidents_tenant_submitted",
        "attendance_conflict_incidents",
        ["tenant_id", "submitted_at"],
        unique=False,
    )
    op.create_index(
        "ix_conflict_incidents_tenant_decided",
        "attendance_conflict_incidents",
        ["tenant_id", "decided_at"],
        unique=False,
    )
    op.create_index(
        "ix_conflict_incidents_tenant_assigned_reviewer",
        "attendance_conflict_incidents",
        ["tenant_id", "assigned_reviewer_id"],
        unique=False,
    )

    # 3. Enable and force Row-Level Security
    op.execute("ALTER TABLE attendance_conflict_incidents ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE attendance_conflict_incidents FORCE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY tenant_isolation ON attendance_conflict_incidents
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
    """)
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON attendance_conflict_incidents TO authenticated, service_role;"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON attendance_conflict_incidents;")
    op.drop_table("attendance_conflict_incidents")

