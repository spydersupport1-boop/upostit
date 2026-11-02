"""Phase 4: Bulk employee import jobs table and RLS policies.

Revision ID: c8e52a91f034
Revises: b7d41a89c204
Create Date: 2026-11-02 14:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c8e52a91f034'
down_revision: Union[str, None] = 'b7d41a89c204'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create import_jobs table
    op.create_table(
        'import_jobs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('created_by_user_id', sa.UUID(), nullable=True),
        sa.Column('file_name', sa.String(length=255), nullable=False),
        sa.Column('file_format', sa.String(length=10), nullable=False),
        sa.Column('status', sa.String(length=30), server_default='queued', nullable=False),
        sa.Column('total_rows', sa.Integer(), server_default='0', nullable=False),
        sa.Column('processed_rows', sa.Integer(), server_default='0', nullable=False),
        sa.Column('succeeded_rows', sa.Integer(), server_default='0', nullable=False),
        sa.Column('failed_rows', sa.Integer(), server_default='0', nullable=False),
        sa.Column('last_processed_row_index', sa.Integer(), server_default='0', nullable=False),
        sa.Column('error_summary', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('s3_file_key', sa.String(length=500), nullable=False),
        sa.Column('s3_error_key', sa.String(length=500), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'created_by_user_id'],
            ['users.tenant_id', 'users.id'],
            name='fk_import_jobs_user',
            ondelete='SET NULL (created_by_user_id)',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_import_jobs_tenant_id'), 'import_jobs', ['tenant_id'], unique=False)
    op.create_index('ix_import_jobs_tenant_status', 'import_jobs', ['tenant_id', 'status'], unique=False)
    op.create_index('ix_import_jobs_tenant_created', 'import_jobs', ['tenant_id', 'created_at'], unique=False)

    # 2. Row-Level Security (RLS) enforcement
    op.execute("ALTER TABLE import_jobs ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE import_jobs FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON import_jobs
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
        """
    )

    # 3. Grant table permissions
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON import_jobs TO authenticated, service_role;")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON import_jobs;")
    op.drop_index('ix_import_jobs_tenant_created', table_name='import_jobs')
    op.drop_index('ix_import_jobs_tenant_status', table_name='import_jobs')
    op.drop_index(op.f('ix_import_jobs_tenant_id'), table_name='import_jobs')
    op.drop_table('import_jobs')
