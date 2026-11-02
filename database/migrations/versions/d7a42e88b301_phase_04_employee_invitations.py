"""Phase 4: Employee invitations table, composite foreign keys, and RLS policies.

Revision ID: d7a42e88b301
Revises: c8e52a91f034
Create Date: 2026-11-02 16:30:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7a42e88b301'
down_revision: str | None = 'c8e52a91f034'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create employee_invitations table
    op.create_table(
        'employee_invitations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('employee_id', sa.UUID(), nullable=False),
        sa.Column('invited_by_user_id', sa.UUID(), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='pending', nullable=False),
        sa.Column('delivery_status', sa.String(length=30), server_default='pending', nullable=False),
        sa.Column('delivery_error', sa.Text(), nullable=True),
        sa.Column('attempt_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'id', name='uq_employee_invitations_tenant_id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'employee_id'],
            ['employees.tenant_id', 'employees.id'],
            name='fk_invitations_employee',
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'invited_by_user_id'],
            ['users.tenant_id', 'users.id'],
            name='fk_invitations_user',
            ondelete='SET NULL (invited_by_user_id)',
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'expired', 'revoked')",
            name='chk_invitations_status',
        ),
    )

    # 2. Indexes
    op.create_index(
        op.f('ix_employee_invitations_tenant_id'),
        'employee_invitations',
        ['tenant_id'],
        unique=False,
    )
    op.create_index(
        'ix_invitations_tenant_employee',
        'employee_invitations',
        ['tenant_id', 'employee_id'],
        unique=False,
    )
    op.create_index(
        'ix_invitations_tenant_status',
        'employee_invitations',
        ['tenant_id', 'status'],
        unique=False,
    )
    op.create_index(
        'uq_employee_invitations_token_hash',
        'employee_invitations',
        ['token_hash'],
        unique=True,
    )
    # Partial unique index enforcing at most one pending invitation per employee
    op.create_index(
        'uq_invitations_active_employee',
        'employee_invitations',
        ['tenant_id', 'employee_id'],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )

    # 3. Row-Level Security (RLS) enforcement
    op.execute("ALTER TABLE employee_invitations ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE employee_invitations FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON employee_invitations
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
        """
    )

    # 4. Grant table permissions
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON employee_invitations TO authenticated, service_role;"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON employee_invitations;")
    op.drop_index(
        'uq_invitations_active_employee',
        table_name='employee_invitations',
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.drop_index('uq_employee_invitations_token_hash', table_name='employee_invitations')
    op.drop_index('ix_invitations_tenant_status', table_name='employee_invitations')
    op.drop_index('ix_invitations_tenant_employee', table_name='employee_invitations')
    op.drop_index(op.f('ix_employee_invitations_tenant_id'), table_name='employee_invitations')
    op.drop_table('employee_invitations')
