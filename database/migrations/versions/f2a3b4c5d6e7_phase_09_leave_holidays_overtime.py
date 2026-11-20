"""Phase 9 Milestone 9.1: Leave, Holidays and Overtime Multipliers.

Revision ID: f2a3b4c5d6e7
Revises: e7f8a9b0c1d2
Create Date: 2026-11-20 13:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2a3b4c5d6e7"
down_revision: str | None = "e7f8a9b0c1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # =========================================================================
    # 1. Create leave_types table
    # =========================================================================
    op.create_table(
        "leave_types",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_paid", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("requires_approval", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("allow_half_day", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("max_consecutive_days", sa.Integer(), nullable=True),
        sa.Column(
            "carry_forward_limit",
            sa.Numeric(precision=4, scale=1),
            server_default="0.0",
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_leave_types_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_leave_types_tenant_code"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("carry_forward_limit >= 0", name="chk_leave_types_carry_forward"),
        sa.CheckConstraint(
            "max_consecutive_days IS NULL OR max_consecutive_days > 0",
            name="chk_leave_types_max_consecutive",
        ),
    )
    op.create_index(
        "ix_leave_types_tenant_active",
        "leave_types",
        ["tenant_id", "is_active"],
        unique=False,
    )

    # =========================================================================
    # 2. Create holiday_calendars table
    # =========================================================================
    op.create_table(
        "holiday_calendars",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("location_id", sa.UUID(), nullable=True),
        sa.Column("department_id", sa.UUID(), nullable=True),
        sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False),
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_holiday_calendars_tenant_id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "location_id"],
            ["locations.tenant_id", "locations.id"],
            name="fk_holiday_calendars_location",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "department_id"],
            ["departments.tenant_id", "departments.id"],
            name="fk_holiday_calendars_department",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_holiday_calendars_tenant_year",
        "holiday_calendars",
        ["tenant_id", "year"],
        unique=False,
    )
    op.create_index(
        "ix_holiday_calendars_tenant_location",
        "holiday_calendars",
        ["tenant_id", "location_id"],
        unique=False,
    )

    # =========================================================================
    # 3. Create holidays table
    # =========================================================================
    op.create_table(
        "holidays",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("calendar_id", sa.UUID(), nullable=False),
        sa.Column("holiday_date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "holiday_type",
            sa.String(length=30),
            server_default="PUBLIC",
            nullable=False,
        ),
        sa.Column("is_optional", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_holidays_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "calendar_id",
            "holiday_date",
            name="uq_holidays_tenant_calendar_date",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "calendar_id"],
            ["holiday_calendars.tenant_id", "holiday_calendars.id"],
            name="fk_holidays_calendar",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "holiday_type IN ('PUBLIC', 'COMPANY', 'OPTIONAL')",
            name="chk_holidays_type",
        ),
    )
    op.create_index(
        "ix_holidays_tenant_date",
        "holidays",
        ["tenant_id", "holiday_date"],
        unique=False,
    )
    op.create_index(
        "ix_holidays_tenant_calendar",
        "holidays",
        ["tenant_id", "calendar_id"],
        unique=False,
    )

    # =========================================================================
    # 4. Create leave_balances table
    # =========================================================================
    op.create_table(
        "leave_balances",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("leave_type_id", sa.UUID(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column(
            "annual_allocation",
            sa.Numeric(precision=5, scale=2),
            server_default="0.00",
            nullable=False,
        ),
        sa.Column(
            "carried_forward",
            sa.Numeric(precision=5, scale=2),
            server_default="0.00",
            nullable=False,
        ),
        sa.Column(
            "accrued",
            sa.Numeric(precision=5, scale=2),
            server_default="0.00",
            nullable=False,
        ),
        sa.Column(
            "used",
            sa.Numeric(precision=5, scale=2),
            server_default="0.00",
            nullable=False,
        ),
        sa.Column(
            "pending_approval",
            sa.Numeric(precision=5, scale=2),
            server_default="0.00",
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_leave_balances_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "employee_id",
            "leave_type_id",
            "year",
            name="uq_leave_balances_tenant_emp_type_year",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            name="fk_leave_balances_employee",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "leave_type_id"],
            ["leave_types.tenant_id", "leave_types.id"],
            name="fk_leave_balances_leave_type",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "annual_allocation >= 0 AND carried_forward >= 0 AND accrued >= 0 AND used >= 0 AND pending_approval >= 0",
            name="chk_leave_balances_non_negative",
        ),
    )
    op.create_index(
        "ix_leave_balances_tenant_emp_year",
        "leave_balances",
        ["tenant_id", "employee_id", "year"],
        unique=False,
    )

    # =========================================================================
    # 5. Create leave_requests table
    # =========================================================================
    op.create_table(
        "leave_requests",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("leave_type_id", sa.UUID(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("is_half_day", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("half_day_period", sa.String(length=20), nullable=True),
        sa.Column("total_days", sa.Numeric(precision=4, scale=2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default="PENDING_APPROVAL",
            nullable=False,
        ),
        sa.Column("reviewer_user_id", sa.UUID(), nullable=True),
        sa.Column("reviewer_notes", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_leave_requests_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            name="fk_leave_requests_employee",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "leave_type_id"],
            ["leave_types.tenant_id", "leave_types.id"],
            name="fk_leave_requests_leave_type",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "reviewer_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_leave_requests_reviewer",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint("end_date >= start_date", name="chk_leave_requests_date_range"),
        sa.CheckConstraint("total_days > 0", name="chk_leave_requests_total_days"),
        sa.CheckConstraint(
            "status IN ('PENDING_APPROVAL', 'APPROVED', 'REJECTED', 'CANCELLED')",
            name="chk_leave_requests_status",
        ),
        sa.CheckConstraint(
            "(is_half_day = FALSE AND half_day_period IS NULL) OR "
            "(is_half_day = TRUE AND half_day_period IN ('FIRST_HALF', 'SECOND_HALF') AND start_date = end_date AND total_days = 0.50)",
            name="chk_leave_requests_half_day",
        ),
        sa.CheckConstraint(
            "(status = 'PENDING_APPROVAL' AND decided_at IS NULL AND reviewer_user_id IS NULL) OR "
            "(status IN ('APPROVED', 'REJECTED') AND decided_at IS NOT NULL AND reviewer_user_id IS NOT NULL) OR "
            "(status = 'CANCELLED')",
            name="chk_leave_requests_decision",
        ),
    )
    op.create_index(
        "ix_leave_requests_tenant_emp_status",
        "leave_requests",
        ["tenant_id", "employee_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_leave_requests_tenant_dates",
        "leave_requests",
        ["tenant_id", "start_date", "end_date"],
        unique=False,
    )
    op.create_index(
        "ix_leave_requests_tenant_status",
        "leave_requests",
        ["tenant_id", "status"],
        unique=False,
    )

    # =========================================================================
    # 6. Create overtime_rules table
    # =========================================================================
    op.create_table(
        "overtime_rules",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "min_overtime_threshold_minutes",
            sa.Integer(),
            server_default="30",
            nullable=False,
        ),
        sa.Column(
            "max_daily_overtime_minutes",
            sa.Integer(),
            server_default="240",
            nullable=True,
        ),
        sa.Column(
            "max_weekly_overtime_minutes",
            sa.Integer(),
            server_default="720",
            nullable=True,
        ),
        sa.Column(
            "workday_multiplier",
            sa.Numeric(precision=3, scale=2),
            server_default="1.50",
            nullable=False,
        ),
        sa.Column(
            "weekend_multiplier",
            sa.Numeric(precision=3, scale=2),
            server_default="2.00",
            nullable=False,
        ),
        sa.Column(
            "holiday_multiplier",
            sa.Numeric(precision=3, scale=2),
            server_default="2.00",
            nullable=False,
        ),
        sa.Column(
            "requires_manager_approval",
            sa.Boolean(),
            server_default="true",
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_overtime_rules_tenant_id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "min_overtime_threshold_minutes >= 0",
            name="chk_overtime_rules_min_threshold",
        ),
        sa.CheckConstraint(
            "max_daily_overtime_minutes IS NULL OR max_daily_overtime_minutes >= min_overtime_threshold_minutes",
            name="chk_overtime_rules_max_daily",
        ),
        sa.CheckConstraint(
            "workday_multiplier >= 1.00 AND weekend_multiplier >= 1.00 AND holiday_multiplier >= 1.00",
            name="chk_overtime_rules_multipliers",
        ),
    )
    op.create_index(
        "ix_overtime_rules_tenant_active",
        "overtime_rules",
        ["tenant_id", "is_active"],
        unique=False,
    )

    # =========================================================================
    # 7. Create overtime_records table
    # =========================================================================
    op.create_table(
        "overtime_records",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("attendance_day_id", sa.UUID(), nullable=False),
        sa.Column("attendance_date", sa.Date(), nullable=False),
        sa.Column("raw_overtime_minutes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("approved_overtime_minutes", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "multiplier",
            sa.Numeric(precision=3, scale=2),
            server_default="1.00",
            nullable=False,
        ),
        sa.Column("payable_overtime_minutes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("overtime_type", sa.String(length=20), nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default="PENDING_APPROVAL",
            nullable=False,
        ),
        sa.Column("reviewer_user_id", sa.UUID(), nullable=True),
        sa.Column("reviewer_notes", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_overtime_records_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "employee_id",
            "attendance_date",
            name="uq_overtime_records_tenant_emp_date",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            name="fk_overtime_records_employee",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "attendance_day_id"],
            ["attendance_days.tenant_id", "attendance_days.id"],
            name="fk_overtime_records_attendance_day",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "reviewer_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_overtime_records_reviewer",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "raw_overtime_minutes >= 0 AND approved_overtime_minutes >= 0 AND payable_overtime_minutes >= 0",
            name="chk_overtime_records_minutes_positive",
        ),
        sa.CheckConstraint(
            "multiplier >= 1.00",
            name="chk_overtime_records_multiplier",
        ),
        sa.CheckConstraint(
            "overtime_type IN ('WORKDAY', 'WEEK_OFF', 'HOLIDAY')",
            name="chk_overtime_records_type",
        ),
        sa.CheckConstraint(
            "status IN ('AUTO_APPROVED', 'PENDING_APPROVAL', 'APPROVED', 'REJECTED')",
            name="chk_overtime_records_status",
        ),
        sa.CheckConstraint(
            "(status = 'PENDING_APPROVAL' AND decided_at IS NULL AND reviewer_user_id IS NULL) OR "
            "(status IN ('APPROVED', 'REJECTED') AND decided_at IS NOT NULL AND reviewer_user_id IS NOT NULL) OR "
            "(status = 'AUTO_APPROVED')",
            name="chk_overtime_records_decision",
        ),
    )
    op.create_index(
        "ix_overtime_records_tenant_status",
        "overtime_records",
        ["tenant_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_overtime_records_tenant_emp_status",
        "overtime_records",
        ["tenant_id", "employee_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_overtime_records_tenant_date",
        "overtime_records",
        ["tenant_id", "attendance_date"],
        unique=False,
    )

    # =========================================================================
    # 8. Row Level Security (RLS) Enablement & Tenant Isolation Policies
    # =========================================================================
    phase9_tables = [
        "leave_types",
        "holiday_calendars",
        "holidays",
        "leave_balances",
        "leave_requests",
        "overtime_rules",
        "overtime_records",
    ]

    for table in phase9_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(f"""
            CREATE POLICY tenant_isolation ON {table}
                USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
                WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
        """)
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO authenticated, service_role;")


def downgrade() -> None:
    phase9_tables_reversed = [
        "overtime_records",
        "overtime_rules",
        "leave_requests",
        "leave_balances",
        "holidays",
        "holiday_calendars",
        "leave_types",
    ]

    for table in phase9_tables_reversed:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table};")
        op.drop_table(table)

