"""phase_04_workplace_locations_and_geofences

Revision ID: b7d41a89c204
Revises: e6331816d336
Create Date: 2026-11-02 13:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b7d41a89c204'
down_revision: Union[str, None] = 'e6331816d336'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create locations table
    op.create_table(
        'locations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('address_line1', sa.String(length=255), nullable=False),
        sa.Column('address_line2', sa.String(length=255), nullable=True),
        sa.Column('city', sa.String(length=100), nullable=False),
        sa.Column('state', sa.String(length=100), nullable=True),
        sa.Column('postal_code', sa.String(length=20), nullable=True),
        sa.Column('country_code', sa.String(length=2), nullable=False),
        sa.Column('latitude', sa.Numeric(precision=10, scale=7), nullable=False),
        sa.Column('longitude', sa.Numeric(precision=10, scale=7), nullable=False),
        sa.Column('radius_meters', sa.Integer(), server_default='100', nullable=False),
        sa.Column('timezone', sa.String(length=50), nullable=False),
        sa.Column('wifi_bssids', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('ip_ranges', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'code', name='uq_locations_tenant_code'),
        sa.UniqueConstraint('tenant_id', 'id', name='uq_locations_tenant_id'),
        sa.CheckConstraint('latitude >= -90.0000000 AND latitude <= 90.0000000', name='chk_locations_latitude_bounds'),
        sa.CheckConstraint('longitude >= -180.0000000 AND longitude <= 180.0000000', name='chk_locations_longitude_bounds'),
        sa.CheckConstraint('radius_meters >= 10 AND radius_meters <= 50000', name='chk_locations_radius_bounds'),
    )
    op.create_index(op.f('ix_locations_tenant_id'), 'locations', ['tenant_id'], unique=False)
    op.create_index('ix_locations_tenant_active', 'locations', ['tenant_id', 'is_active'], unique=False)

    # 2. Add PostGIS coordinates generated stored column and spatial GiST index
    op.execute(
        """
        ALTER TABLE locations ADD COLUMN coordinates geography(Point, 4326)
        GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography) STORED;
        """
    )
    op.execute("CREATE INDEX ix_locations_spatial ON locations USING GIST (coordinates);")

    # 3. Create employee_locations junction table with composite tenant foreign keys
    op.create_table(
        'employee_locations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('employee_id', sa.UUID(), nullable=False),
        sa.Column('location_id', sa.UUID(), nullable=False),
        sa.Column('is_primary', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('effective_from', sa.Date(), server_default=sa.text('CURRENT_DATE'), nullable=False),
        sa.Column('effective_to', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['tenant_id', 'employee_id'], ['employees.tenant_id', 'employees.id'], name='fk_emp_loc_employee', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id', 'location_id'], ['locations.tenant_id', 'locations.id'], name='fk_emp_loc_location', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'employee_id', 'location_id', 'effective_from', name='uq_emp_loc_assignment'),
        sa.CheckConstraint('effective_to IS NULL OR effective_to >= effective_from', name='chk_emp_loc_dates'),
    )
    op.create_index(op.f('ix_employee_locations_tenant_id'), 'employee_locations', ['tenant_id'], unique=False)
    op.create_index('ix_emp_loc_tenant_emp', 'employee_locations', ['tenant_id', 'employee_id'], unique=False)
    op.create_index('ix_emp_loc_tenant_loc', 'employee_locations', ['tenant_id', 'location_id'], unique=False)

    # 4. Partial unique index and temporal exclusion constraint enforcing at most one primary location per employee on any given date
    op.execute(
        """
        CREATE UNIQUE INDEX uq_emp_active_primary_location
        ON employee_locations (tenant_id, employee_id)
        WHERE is_primary = TRUE AND effective_to IS NULL;
        """
    )
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist;")
    op.execute(
        """
        ALTER TABLE employee_locations
        ADD CONSTRAINT excl_emp_primary_workplace_overlap
        EXCLUDE USING gist (
            tenant_id WITH =,
            employee_id WITH =,
            daterange(effective_from, COALESCE(effective_to, 'infinity'::date), '[]') WITH &&
        )
        WHERE (is_primary = TRUE);
        """
    )

    # 5. Row-Level Security (RLS) enforcement on locations and employee_locations
    op.execute("ALTER TABLE locations ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE locations FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON locations
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
        """
    )

    op.execute("ALTER TABLE employee_locations ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE employee_locations FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON employee_locations
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
        """
    )

    # 6. Grant permissions to authenticated and service_role
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON locations TO authenticated, service_role;")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON employee_locations TO authenticated, service_role;")


def downgrade() -> None:
    op.execute("ALTER TABLE employee_locations DROP CONSTRAINT IF EXISTS excl_emp_primary_workplace_overlap;")
    op.execute("DROP INDEX IF EXISTS uq_emp_active_primary_location;")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON employee_locations;")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON locations;")
    op.drop_table('employee_locations')
    op.drop_table('locations')
