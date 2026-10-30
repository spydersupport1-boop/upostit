"""Database connection and session management module."""

import logging
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from services.api.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy 2 domain models."""

    pass


engine: AsyncEngine | None = None
AsyncSessionLocal: async_sessionmaker[AsyncSession] | None = None

if settings.DATABASE_URL and "[YOUR-PASSWORD]" not in settings.DATABASE_URL:
    try:
        engine = create_async_engine(
            settings.DATABASE_URL,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_timeout=settings.DB_POOL_TIMEOUT,
            echo=settings.DB_ECHO,
            pool_pre_ping=True,
        )
        AsyncSessionLocal = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    except Exception as e:
        logger.warning("Could not initialize database engine: %s", type(e).__name__)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that yields an async database session."""
    if AsyncSessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured. Database session unavailable.")
    async with AsyncSessionLocal() as session:
        yield session


async def set_tenant_context(
    session: AsyncSession,
    tenant_id: str,
    enforce_rls_role: bool = True,
) -> None:
    """
    Sets transaction-local tenant context for PostgreSQL Row-Level Security.
    Uses parameterized `set_config('app.tenant_id', :tenant_id, true)` (is_local=True).
    Optionally sets `SET LOCAL ROLE <role>` (e.g. 'authenticated') to ensure roles with
    `rolbypassrls` cannot bypass RLS policies during tenant queries.
    """
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )
    if enforce_rls_role and settings.RUNTIME_DATABASE_ROLE:
        safe_role = settings.RUNTIME_DATABASE_ROLE.strip().replace(";", "")
        await session.execute(text(f"SET LOCAL ROLE {safe_role}"))


async def check_database_connection() -> tuple[bool, str]:
    """
    Executes a safe read-only SELECT 1 query to verify database connectivity.
    Never exposes passwords, tokens, or connection strings in responses.
    """
    if not settings.DATABASE_URL or "[YOUR-PASSWORD]" in settings.DATABASE_URL:
        return False, "DATABASE_URL is not fully configured (contains placeholder [YOUR-PASSWORD])"

    if engine is None:
        return False, "Database engine is not initialized"

    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            val = result.scalar()
            if val == 1:
                return True, "connected"
            return False, "unexpected query result"
    except Exception as e:
        logger.error(f"Database connection error: {type(e).__name__}")
        # Categorize safe error category without leaking secrets
        err_type = type(e).__name__
        err_msg = str(e).lower()
        if "authentication" in err_msg or "password" in err_msg:
            return False, "authentication failed (invalid credentials)"
        elif "connection refused" in err_msg or "cannot connect" in err_msg:
            return False, "connection refused (host unreachable)"
        elif "timeout" in err_msg:
            return False, "connection timed out"
        return False, f"database connectivity error ({err_type})"


async def check_postgis_capability() -> tuple[bool, str]:
    """
    Executes a safe read-only capability check for PostGIS.
    """
    if engine is None:
        return False, "database engine not initialized"

    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT postgis_full_version();"))
            version_str = result.scalar()
            if version_str:
                return True, "PostGIS available"
            return False, "PostGIS extension query returned empty"
    except Exception as e:
        err_msg = str(e).lower()
        if "does not exist" in err_msg or "undefined_function" in err_msg:
            return False, "PostGIS extension not installed in database"
        return False, f"PostGIS check failed ({type(e).__name__})"
