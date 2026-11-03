"""Phase 5 Milestone 3: Attendance days projection table.

Revision ID: a2b3c4d5e6f7
Revises: f1b94c8e7a23
Create Date: 2026-11-03 14:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a2b3c4d5e6f7"
down_revision: str | None = "f1b94c8e7a23"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create attendance_days table (Derived Projection Table)
    op.create_table(
        "attendance_days",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("attendance_date", sa.Date(), nullable=False),
        sa.Column("shift_template_id", sa.UUID(), nullable=True),
        sa.Column("shift_version_id", sa.UUID(), nullable=True),
        sa.Column("first_check_in", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_check_out", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_working_minutes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_break_minutes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("net_working_minutes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("actual_late_minutes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("late_arrival_minutes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("actual_early_minutes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("early_departure_minutes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("overtime_minutes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=30), server_default="ABSENT", nullable=False),
        sa.Column(
            "calculation_status", sa.String(length=30), server_default="CALCULATED", nullable=False
        ),
        sa.Column("calculation_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("is_incomplete", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("missing_punch", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "last_calculated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "source_event_ids",
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_attendance_days_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "employee_id", "attendance_date", name="uq_attendance_days_tenant_emp_date"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            name="fk_attendance_days_employee",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "shift_template_id"],
            ["shift_templates.tenant_id", "shift_templates.id"],
            name="fk_attendance_days_shift",
            ondelete="SET NULL (shift_template_id)",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "shift_version_id"],
            ["shift_template_versions.tenant_id", "shift_template_versions.id"],
            name="fk_attendance_days_shift_version",
            ondelete="SET NULL (shift_version_id)",
        ),
        sa.CheckConstraint(
            "status IN ('PRESENT', 'LATE', 'HALF_DAY', 'ABSENT', 'INCOMPLETE', 'WEEK_OFF', 'ON_LEAVE', 'HOLIDAY', 'PENDING_REVIEW')",
            name="chk_attendance_days_status",
        ),
        sa.CheckConstraint(
            "calculation_status IN ('CALCULATED', 'INCOMPLETE', 'FLAGGED')",
            name="chk_attendance_days_calc_status",
        ),
    )

    op.create_index(
        "ix_attendance_days_tenant_date",
        "attendance_days",
        ["tenant_id", "attendance_date"],
        unique=False,
    )
    op.create_index(
        "ix_attendance_days_tenant_status",
        "attendance_days",
        ["tenant_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_attendance_days_tenant_emp_date",
        "attendance_days",
        ["tenant_id", "employee_id", "attendance_date"],
        unique=False,
    )

    # Enable and force Row-Level Security on attendance_days
    op.execute("ALTER TABLE attendance_days ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE attendance_days FORCE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY tenant_isolation ON attendance_days
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
    """)

    # Grant permissions: projection table supports full DML for service_role and authenticated
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON attendance_days TO authenticated, service_role;"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON attendance_days;")
    op.drop_table("attendance_days")
