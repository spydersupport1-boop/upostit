"""Phase 5: Shift templates, immutable versions, and employee shift assignments.

Revision ID: e9f63b02a145
Revises: d7a42e88b301
Create Date: 2026-11-03 03:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e9f63b02a145'
down_revision: str | None = 'd7a42e88b301'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Ensure btree_gist extension exists for exclusion constraints
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist;")

    # 1. Create shift_templates table (Master container)
    op.create_table(
        'shift_templates',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'id', name='uq_shift_templates_tenant_id'),
        sa.UniqueConstraint('tenant_id', 'code', name='uq_shift_templates_tenant_code'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='RESTRICT'),
    )

    op.create_index(
        'ix_shift_templates_tenant_active',
        'shift_templates',
        ['tenant_id', 'is_active'],
        unique=False,
    )

    # Enable and force Row-Level Security on shift_templates
    op.execute("ALTER TABLE shift_templates ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE shift_templates FORCE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY tenant_isolation ON shift_templates
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
    """)

    # 2. Create shift_template_versions table (Immutable historical snapshots)
    op.create_table(
        'shift_template_versions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('shift_template_id', sa.UUID(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('version_effective_from', sa.Date(), nullable=False),
        sa.Column('start_time', sa.Time(timezone=False), nullable=False),
        sa.Column('end_time', sa.Time(timezone=False), nullable=False),
        sa.Column('grace_period_minutes', sa.Integer(), server_default='15', nullable=False),
        sa.Column('early_exit_grace_minutes', sa.Integer(), server_default='15', nullable=False),
        sa.Column('early_arrival_allowance_minutes', sa.Integer(), server_default='120', nullable=False),
        sa.Column('late_departure_allowance_minutes', sa.Integer(), server_default='180', nullable=False),
        sa.Column('half_day_threshold_minutes', sa.Integer(), server_default='240', nullable=False),
        sa.Column('full_day_threshold_minutes', sa.Integer(), server_default='480', nullable=False),
        sa.Column('break_duration_minutes', sa.Integer(), server_default='60', nullable=False),
        sa.Column('is_overnight', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('is_flexible', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('weekly_off_days', postgresql.JSONB(astext_type=sa.Text()), server_default='[6, 0]', nullable=False),
        sa.Column('created_by_user_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'id', name='uq_shift_versions_tenant_id'),
        sa.UniqueConstraint('tenant_id', 'shift_template_id', 'version_number', name='uq_shift_versions_tenant_template_vnum'),
        sa.UniqueConstraint('tenant_id', 'shift_template_id', 'version_effective_from', name='uq_shift_versions_tenant_template_date'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'shift_template_id'],
            ['shift_templates.tenant_id', 'shift_templates.id'],
            name='fk_shift_versions_template',
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'created_by_user_id'],
            ['users.tenant_id', 'users.id'],
            name='fk_shift_versions_user',
            ondelete='SET NULL (created_by_user_id)',
        ),
        sa.CheckConstraint(
            'half_day_threshold_minutes > 0 AND full_day_threshold_minutes >= half_day_threshold_minutes',
            name='chk_shift_versions_thresholds',
        ),
        sa.CheckConstraint(
            'grace_period_minutes >= 0 AND early_exit_grace_minutes >= 0 AND '
            'early_arrival_allowance_minutes >= 0 AND late_departure_allowance_minutes >= 0',
            name='chk_shift_versions_graces',
        ),
    )

    op.create_index(
        'ix_shift_versions_tenant_tmpl_date',
        'shift_template_versions',
        ['tenant_id', 'shift_template_id', 'version_effective_from'],
        unique=False,
    )

    # Enable and force Row-Level Security on shift_template_versions
    op.execute("ALTER TABLE shift_template_versions ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE shift_template_versions FORCE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY tenant_isolation ON shift_template_versions
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
    """)

    # 3. Create shift_assignments table (Employee Rostering with exclusion constraint)
    op.create_table(
        'shift_assignments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('employee_id', sa.UUID(), nullable=False),
        sa.Column('shift_template_id', sa.UUID(), nullable=False),
        sa.Column('effective_from', sa.Date(), server_default=sa.text('CURRENT_DATE'), nullable=False),
        sa.Column('effective_to', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'id', name='uq_shift_assignments_tenant_id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'employee_id'],
            ['employees.tenant_id', 'employees.id'],
            name='fk_shift_assignments_employee',
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'shift_template_id'],
            ['shift_templates.tenant_id', 'shift_templates.id'],
            name='fk_shift_assignments_template',
            ondelete='RESTRICT',
        ),
        sa.CheckConstraint(
            'effective_to IS NULL OR effective_to >= effective_from',
            name='chk_shift_assignments_dates',
        ),
    )

    # Add temporal exclusion constraint preventing overlapping assignments for the same employee
    op.execute("""
        ALTER TABLE shift_assignments ADD CONSTRAINT excl_shift_assignments_overlap
        EXCLUDE USING gist (
            tenant_id WITH =,
            employee_id WITH =,
            daterange(effective_from, COALESCE(effective_to, 'infinity'::date), '[]') WITH &&
        );
    """)

    op.create_index(
        'ix_shift_assignments_tenant_emp',
        'shift_assignments',
        ['tenant_id', 'employee_id'],
        unique=False,
    )
    op.create_index(
        'ix_shift_assignments_tenant_shift',
        'shift_assignments',
        ['tenant_id', 'shift_template_id'],
        unique=False,
    )

    # Enable and force Row-Level Security on shift_assignments
    op.execute("ALTER TABLE shift_assignments ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE shift_assignments FORCE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY tenant_isolation ON shift_assignments
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
    """)

    # Grant permissions to standard application roles
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON shift_templates TO authenticated, service_role;")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON shift_template_versions TO authenticated, service_role;")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON shift_assignments TO authenticated, service_role;")


def downgrade() -> None:
    # 1. Drop shift_assignments
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON shift_assignments;")
    op.drop_table('shift_assignments')

    # 2. Drop shift_template_versions
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON shift_template_versions;")
    op.drop_table('shift_template_versions')

    # 3. Drop shift_templates
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON shift_templates;")
    op.drop_table('shift_templates')
