"""FastAPI application entrypoint for Attendance SaaS modular monolith."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from services.api.auth.routes import router as auth_router
from services.api.config import settings
from services.api.database import check_database_connection, check_postgis_capability
from services.api.employees.routes import router as employees_router
from services.api.organization.routes import (
    departments_router,
    designations_router,
)
from services.api.tenants.routes import router as tenants_router

app = FastAPI(
    title="Attendance SaaS API",
    description="High-performance modular monolith backend for multi-tenant attendance management with fraud prevention.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS
    if settings.ENVIRONMENT != "production"
    else ["https://app.upostit.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API v1 Router
api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(auth_router)
api_v1_router.include_router(tenants_router)
api_v1_router.include_router(departments_router)
api_v1_router.include_router(designations_router)
api_v1_router.include_router(employees_router)

app.include_router(api_v1_router)


@app.get(
    "/health",
    tags=["System"],
    summary="Liveness Probe",
    status_code=status.HTTP_200_OK,
)
async def health_check() -> dict[str, Any]:
    """Lightweight liveness probe indicating that the FastAPI process is active."""
    return {
        "status": "ok",
        "timestamp": datetime.now(UTC).isoformat(),
        "service": "attendance-api",
        "version": "0.1.0",
        "environment": settings.ENVIRONMENT,
    }


@app.get(
    "/ready",
    tags=["System"],
    summary="Readiness Probe",
    status_code=status.HTTP_200_OK,
)
async def readiness_check() -> JSONResponse:
    """
    Deep readiness probe verifying that required subsystems (Supabase PostgreSQL, Redis)
    are reachable and operational.
    """
    checks: dict[str, str] = {}
    is_ready = True

    # 1. Check Supabase Database
    if not settings.DATABASE_URL:
        checks["database"] = "unconfigured (DATABASE_URL missing)"
        checks["postgis"] = "unconfigured"
        is_ready = False
    else:
        db_ok, db_msg = await check_database_connection()
        checks["database"] = db_msg
        if not db_ok:
            is_ready = False

        # PostGIS check
        if db_ok:
            gis_ok, gis_msg = await check_postgis_capability()
            checks["postgis"] = gis_msg
            if not gis_ok:
                is_ready = False
        else:
            checks["postgis"] = "skipped (db unreachable)"

    # 2. Check Redis (graceful probe)
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.REDIS_URL, socket_timeout=2)
        await r.ping()
        await r.aclose()
        checks["redis"] = "connected"
    except Exception as e:
        checks["redis"] = f"unreachable ({type(e).__name__})"
        # In dev/test when Docker isn't up, don't fail ready unless db is also checked
        if settings.ENVIRONMENT != "development":
            is_ready = False

    http_status = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=http_status,
        content={
            "status": "ready" if is_ready else "not_ready",
            "timestamp": datetime.now(UTC).isoformat(),
            "checks": checks,
        },
    )
