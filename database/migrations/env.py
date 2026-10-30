import asyncio
from logging.config import fileConfig
import os
import sys

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

# Ensure root directory is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from services.api.config import settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import all domain models so Alembic registers them on Base.metadata
from services.api.auth.models import RefreshToken, User
from services.api.database import Base
from services.api.tenants.models import Tenant

target_metadata = Base.metadata

POSTGIS_SYSTEM_TABLES = {"spatial_ref_sys", "geography_columns", "geometry_columns"}


def include_object(object, name, type_, reflected, compare_to):
    """Exclude PostGIS and Supabase system metadata tables from autogenerate diffs."""
    if type_ == "table" and name in POSTGIS_SYSTEM_TABLES:
        return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = settings.DATABASE_URL or config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with asyncpg engine."""
    configuration = config.get_section(config.config_ini_section) or {}
    migration_url = settings.MIGRATION_DATABASE_URL or settings.DATABASE_URL
    configuration["sqlalchemy.url"] = migration_url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    if not settings.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set in environment. Cannot run online migrations.")
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
