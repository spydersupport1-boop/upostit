"""phase_03_org_structure_and_employees

Revision ID: e6331816d336
Revises: 4f61a7dd311e
Create Date: 2026-10-30 12:32:49.322160

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6331816d336'
down_revision: Union[str, None] = '4f61a7dd311e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add tenant-aware composite unique constraint to Phase 2 users table
    op.create_unique_constraint('uq_users_tenant_id', 'users', ['tenant_id', 'id'])

    # 2. Create departments table with composite unique constraint (tenant_id, id)
    op.create_table(
        'departments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('manager_id', sa.UUID(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'code', name='uq_departments_tenant_code'),
        sa.UniqueConstraint('tenant_id', 'name', name='uq_departments_tenant_name'),
        sa.UniqueConstraint('tenant_id', 'id', name='uq_departments_tenant_id')
    )
    op.create_index(op.f('ix_departments_manager_id'), 'departments', ['manager_id'], unique=False)
    op.create_index('ix_departments_tenant_active', 'departments', ['tenant_id', 'is_active'], unique=False)
    op.create_index(op.f('ix_departments_tenant_id'), 'departments', ['tenant_id'], unique=False)

    # 3. Create designations table with composite unique constraint (tenant_id, id)
    op.create_table(
        'designations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(length=100), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'code', name='uq_designations_tenant_code'),
        sa.UniqueConstraint('tenant_id', 'title', name='uq_designations_tenant_title'),
        sa.UniqueConstraint('tenant_id', 'id', name='uq_designations_tenant_id')
    )
    op.create_index('ix_designations_tenant_active', 'designations', ['tenant_id', 'is_active'], unique=False)
    op.create_index(op.f('ix_designations_tenant_id'), 'designations', ['tenant_id'], unique=False)

    # 4. Create employees table with composite tenant-aware foreign keys
    op.create_table(
        'employees',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('employee_id', sa.String(length=50), nullable=False),
        sa.Column('first_name', sa.String(length=100), nullable=False),
        sa.Column('last_name', sa.String(length=100), nullable=False),
        sa.Column('work_email', sa.String(length=255), nullable=False),
        sa.Column('phone_number', sa.String(length=50), nullable=True),
        sa.Column('department_id', sa.UUID(), nullable=True),
        sa.Column('designation_id', sa.UUID(), nullable=True),
        sa.Column('reporting_manager_id', sa.UUID(), nullable=True),
        sa.Column('employment_type', sa.String(length=30), nullable=False),
        sa.Column('joining_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('work_location', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'department_id'],
            ['departments.tenant_id', 'departments.id'],
            name='fk_employees_tenant_department_id',
            ondelete='SET NULL'
        ),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'designation_id'],
            ['designations.tenant_id', 'designations.id'],
            name='fk_employees_tenant_designation_id',
            ondelete='SET NULL'
        ),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'reporting_manager_id'],
            ['employees.tenant_id', 'employees.id'],
            name='fk_employees_tenant_reporting_manager_id',
            ondelete='SET NULL'
        ),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'user_id'],
            ['users.tenant_id', 'users.id'],
            name='fk_employees_tenant_user_id',
            ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'employee_id', name='uq_employees_tenant_employee_id'),
        sa.UniqueConstraint('tenant_id', 'work_email', name='uq_employees_tenant_work_email'),
        sa.UniqueConstraint('tenant_id', 'id', name='uq_employees_tenant_id'),
        sa.UniqueConstraint('tenant_id', 'user_id', name='uq_employees_tenant_user_id')
    )
    op.create_index(op.f('ix_employees_department_id'), 'employees', ['department_id'], unique=False)
    op.create_index(op.f('ix_employees_designation_id'), 'employees', ['designation_id'], unique=False)
    op.create_index(op.f('ix_employees_reporting_manager_id'), 'employees', ['reporting_manager_id'], unique=False)
    op.create_index(op.f('ix_employees_status'), 'employees', ['status'], unique=False)
    op.create_index('ix_employees_tenant_dept', 'employees', ['tenant_id', 'department_id'], unique=False)
    op.create_index(op.f('ix_employees_tenant_id'), 'employees', ['tenant_id'], unique=False)
    op.create_index('ix_employees_tenant_status', 'employees', ['tenant_id', 'status'], unique=False)
    op.create_index(op.f('ix_employees_user_id'), 'employees', ['user_id'], unique=False)
    op.create_index(op.f('ix_employees_work_email'), 'employees', ['work_email'], unique=False)

    # 5. Add composite foreign key from departments.manager_id to employees(tenant_id, id)
    op.create_foreign_key(
        'fk_departments_tenant_manager_id',
        'departments',
        'employees',
        ['tenant_id', 'manager_id'],
        ['tenant_id', 'id'],
        ondelete='SET NULL',
    )

    # 6. Enable and force Row-Level Security on all tenant-scoped tables
    op.execute("ALTER TABLE departments ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE departments FORCE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY tenant_isolation_departments ON departments
        FOR ALL
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
        WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
    """)

    op.execute("ALTER TABLE designations ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE designations FORCE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY tenant_isolation_designations ON designations
        FOR ALL
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
        WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
    """)

    op.execute("ALTER TABLE employees ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE employees FORCE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY tenant_isolation_employees ON employees
        FOR ALL
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
        WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
    """)

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON departments, designations, employees TO authenticated, service_role;")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_employees ON employees;")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_designations ON designations;")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_departments ON departments;")

    op.drop_constraint('fk_departments_tenant_manager_id', 'departments', type_='foreignkey')

    op.drop_index(op.f('ix_employees_work_email'), table_name='employees')
    op.drop_index(op.f('ix_employees_user_id'), table_name='employees')
    op.drop_index('ix_employees_tenant_status', table_name='employees')
    op.drop_index(op.f('ix_employees_tenant_id'), table_name='employees')
    op.drop_index('ix_employees_tenant_dept', table_name='employees')
    op.drop_index(op.f('ix_employees_status'), table_name='employees')
    op.drop_index(op.f('ix_employees_reporting_manager_id'), table_name='employees')
    op.drop_index(op.f('ix_employees_designation_id'), table_name='employees')
    op.drop_index(op.f('ix_employees_department_id'), table_name='employees')
    op.drop_table('employees')

    op.drop_index(op.f('ix_designations_tenant_id'), table_name='designations')
    op.drop_index('ix_designations_tenant_active', table_name='designations')
    op.drop_table('designations')

    op.drop_index(op.f('ix_departments_tenant_id'), table_name='departments')
    op.drop_index('ix_departments_tenant_active', table_name='departments')
    op.drop_index(op.f('ix_departments_manager_id'), table_name='departments')
    op.drop_table('departments')

    op.drop_constraint('uq_users_tenant_id', 'users', type_='unique')
