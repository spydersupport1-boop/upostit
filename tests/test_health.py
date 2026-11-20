"""Unit tests for FastAPI health and readiness probes."""

import pytest
from httpx import ASGITransport, AsyncClient

from services.api.config import settings
from services.api.database import check_database_connection
from services.api.main import app


@pytest.mark.asyncio
async def test_health_check_returns_ok():
    """Verify that /health liveness probe returns 200 OK with proper metadata."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "attendance-api"
    assert data["version"] == "0.1.0"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_readiness_check_returns_valid_structure():
    """Verify that /ready probe returns expected structure with status and checks."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/ready")
    assert response.status_code in (200, 503)
    data = response.json()
    assert "status" in data
    assert "checks" in data
    assert "timestamp" in data
    assert "database" in data["checks"]


@pytest.mark.asyncio
async def test_check_database_connection_when_unconfigured():
    """Verify that check_database_connection handles empty DATABASE_URL safely."""
    # When DATABASE_URL is not set, it should safely return False with safe error message
    if not settings.DATABASE_URL or "[YOUR-PASSWORD]" in settings.DATABASE_URL:
        ok, msg = await check_database_connection()
        assert ok is False
        assert "not configured" in msg or "not fully configured" in msg


def test_openapi_docs_available():
    """Verify OpenAPI schema generation."""
    schema = app.openapi()
    assert schema["info"]["title"] == "Attendance SaaS API"
    assert schema["info"]["version"] == "0.1.0"
    assert "/health" in schema["paths"]
    assert "/ready" in schema["paths"]
