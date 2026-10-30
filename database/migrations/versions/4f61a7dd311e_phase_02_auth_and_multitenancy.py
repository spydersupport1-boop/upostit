"""phase_02_auth_and_multitenancy

Revision ID: 4f61a7dd311e
Revises: 
Create Date: 2026-10-30 11:45:30.991973

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4f61a7dd311e'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create 'tenants' table
    op.create_table(
        'tenants',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('legal_name', sa.String(length=255), nullable=True),
        sa.Column('industry', sa.String(length=100), nullable=True),
        sa.Column('company_email', sa.String(length=255), nullable=False),
        sa.Column('company_phone', sa.String(length=50), nullable=True),
        sa.Column('country_code', sa.String(length=2), nullable=False),
        sa.Column('timezone', sa.String(length=50), nullable=False, server_default='UTC'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tenants_company_email'), 'tenants', ['company_email'], unique=False)
    op.create_index(op.f('ix_tenants_slug'), 'tenants', ['slug'], unique=True)
    op.create_index(op.f('ix_tenants_status'), 'tenants', ['status'], unique=False)

    # 2. Create 'users' table
    op.create_table(
        'users',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False, server_default='employee'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
        sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'email', name='uq_users_tenant_email')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=False)
    op.create_index(op.f('ix_users_status'), 'users', ['status'], unique=False)
    op.create_index(op.f('ix_users_tenant_id'), 'users', ['tenant_id'], unique=False)
    op.create_index('ix_users_tenant_role', 'users', ['tenant_id', 'role'], unique=False)

    # 3. Create 'refresh_tokens' table
    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('family_id', sa.UUID(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('replaced_by_token_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['replaced_by_token_id'], ['refresh_tokens.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_refresh_tokens_family_id'), 'refresh_tokens', ['family_id'], unique=False)
    op.create_index(op.f('ix_refresh_tokens_revoked_at'), 'refresh_tokens', ['revoked_at'], unique=False)
    op.create_index(op.f('ix_refresh_tokens_tenant_id'), 'refresh_tokens', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_refresh_tokens_token_hash'), 'refresh_tokens', ['token_hash'], unique=True)
    op.create_index(op.f('ix_refresh_tokens_user_id'), 'refresh_tokens', ['user_id'], unique=False)
    op.create_index('ix_refresh_tokens_user_revoked', 'refresh_tokens', ['user_id', 'revoked_at'], unique=False)

    # 4. Enable PostgreSQL Row-Level Security (RLS) on all tenant-scoped tables
    op.execute("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE tenants FORCE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY tenant_isolation_tenants ON tenants
            FOR ALL
            USING (
                id = current_setting('app.tenant_id', true)::uuid
                OR status = 'active'
            )
            WITH CHECK (
                id = current_setting('app.tenant_id', true)::uuid
            );
    """)

    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE users FORCE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY tenant_isolation_users ON users
            FOR ALL
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
    """)

    op.execute("ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE refresh_tokens FORCE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY tenant_isolation_refresh_tokens ON refresh_tokens
            FOR ALL
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
    """)

    # 5. Create SECURITY DEFINER registration bootstrap function
    op.execute("""
        CREATE OR REPLACE FUNCTION register_tenant_bootstrap(
            p_company_name VARCHAR(255),
            p_slug VARCHAR(100),
            p_company_email VARCHAR(255),
            p_country_code VARCHAR(2),
            p_timezone VARCHAR(50),
            p_owner_name VARCHAR(255),
            p_owner_email VARCHAR(255),
            p_password_hash VARCHAR(255),
            p_refresh_token_hash VARCHAR(64),
            p_family_id UUID,
            p_refresh_expires_at TIMESTAMPTZ
        )
        RETURNS JSONB
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
        DECLARE
            v_tenant_id UUID := gen_random_uuid();
            v_user_id UUID := gen_random_uuid();
            v_refresh_id UUID := gen_random_uuid();
            v_now TIMESTAMPTZ := timezone('utc', now());
            v_result JSONB;
        BEGIN
            IF length(trim(p_company_name)) < 2 THEN
                RAISE EXCEPTION 'Company name must be at least 2 characters';
            END IF;
            IF length(trim(p_slug)) < 2 THEN
                RAISE EXCEPTION 'Company slug must be at least 2 characters';
            END IF;

            INSERT INTO tenants (
                id, name, slug, company_email, country_code, timezone, status, created_at, updated_at
            ) VALUES (
                v_tenant_id, p_company_name, p_slug, p_company_email, p_country_code, p_timezone, 'active', v_now, v_now
            );

            INSERT INTO users (
                id, tenant_id, full_name, email, password_hash, role, status, created_at, updated_at
            ) VALUES (
                v_user_id, v_tenant_id, p_owner_name, p_owner_email, p_password_hash, 'owner', 'active', v_now, v_now
            );

            INSERT INTO refresh_tokens (
                id, tenant_id, user_id, token_hash, family_id, expires_at, created_at
            ) VALUES (
                v_refresh_id, v_tenant_id, v_user_id, p_refresh_token_hash, p_family_id, p_refresh_expires_at, v_now
            );

            v_result := jsonb_build_object(
                'tenant_id', v_tenant_id,
                'user_id', v_user_id,
                'refresh_token_id', v_refresh_id,
                'slug', p_slug
            );
            RETURN v_result;
        END;
        $$;
    """)

    # Grant appropriate execution permissions
    op.execute("GRANT EXECUTE ON FUNCTION register_tenant_bootstrap TO authenticated, anon, service_role;")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON tenants, users, refresh_tokens TO authenticated, service_role;")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS register_tenant_bootstrap(VARCHAR, VARCHAR, VARCHAR, VARCHAR, VARCHAR, VARCHAR, VARCHAR, VARCHAR, VARCHAR, UUID, TIMESTAMPTZ);")

    op.execute("DROP POLICY IF EXISTS tenant_isolation_refresh_tokens ON refresh_tokens;")
    op.drop_index('ix_refresh_tokens_user_revoked', table_name='refresh_tokens')
    op.drop_index(op.f('ix_refresh_tokens_user_id'), table_name='refresh_tokens')
    op.drop_index(op.f('ix_refresh_tokens_token_hash'), table_name='refresh_tokens')
    op.drop_index(op.f('ix_refresh_tokens_tenant_id'), table_name='refresh_tokens')
    op.drop_index(op.f('ix_refresh_tokens_revoked_at'), table_name='refresh_tokens')
    op.drop_index(op.f('ix_refresh_tokens_family_id'), table_name='refresh_tokens')
    op.drop_table('refresh_tokens')

    op.execute("DROP POLICY IF EXISTS tenant_isolation_users ON users;")
    op.drop_index('ix_users_tenant_role', table_name='users')
    op.drop_index(op.f('ix_users_tenant_id'), table_name='users')
    op.drop_index(op.f('ix_users_status'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')

    op.execute("DROP POLICY IF EXISTS tenant_isolation_tenants ON tenants;")
    op.drop_index(op.f('ix_tenants_status'), table_name='tenants')
    op.drop_index(op.f('ix_tenants_slug'), table_name='tenants')
    op.drop_index(op.f('ix_tenants_company_email'), table_name='tenants')
    op.drop_table('tenants')
