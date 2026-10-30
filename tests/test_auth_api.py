"""API integration tests for Phase 2 authentication and tenant endpoints."""

import uuid
from datetime import UTC

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from services.api.main import app


@pytest.mark.asyncio
async def test_auth_me_requires_token():
    """Verify GET /api/v1/auth/me returns 401 when Authorization header is absent."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/auth/me")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert "not provided" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_auth_me_rejects_invalid_token():
    """Verify GET /api/v1/auth/me returns 401 when token is invalid or malformed."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid-garbage-token"},
        )
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_auth_me_rejects_expired_token():
    """Verify GET /api/v1/auth/me returns 401 when token is expired."""
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    # Create expired token
    from datetime import datetime, timedelta

    import jwt

    from services.api.config import settings

    now = datetime.now(UTC)
    expired_payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": "owner",
        "jti": str(uuid.uuid4()),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": int((now - timedelta(minutes=20)).timestamp()),
        "exp": int((now - timedelta(minutes=5)).timestamp()),
    }
    expired_token = jwt.encode(expired_payload, settings.effective_jwt_secret, algorithm="HS256")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert "expired" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_tenant_validation_failure():
    """Verify POST /api/v1/auth/register-tenant rejects invalid password and missing fields."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Weak password (valid length, but missing uppercase and special character) -> 400 Bad Request
        res = await ac.post(
            "/api/v1/auth/register-tenant",
            json={
                "company_name": "Test Company",
                "company_email": "company@test.com",
                "owner_name": "John Doe",
                "owner_email": "john@test.com",
                "password": "weakpassword123",
                "country_code": "US",
                "timezone": "UTC",
            },
        )
    assert res.status_code == status.HTTP_400_BAD_REQUEST

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Too short password (<8 chars) -> 422 Unprocessable Entity
        res_short = await ac.post(
            "/api/v1/auth/register-tenant",
            json={
                "company_name": "Test Company",
                "company_email": "company@test.com",
                "owner_name": "John Doe",
                "owner_email": "john@test.com",
                "password": "weak",
                "country_code": "US",
                "timezone": "UTC",
            },
        )
    assert res_short.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Missing required fields -> 422 Unprocessable Entity
        res2 = await ac.post(
            "/api/v1/auth/register-tenant",
            json={
                "company_name": "Test Company",
            },
        )
    assert res2.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_login_validation_failure():
    """Verify POST /api/v1/auth/login rejects malformed payload."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/api/v1/auth/login",
            json={
                "email": "not-an-email",
                "password": "",
                "tenant_slug": "",
            },
        )
    assert res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_refresh_token_missing():
    """Verify POST /api/v1/auth/refresh returns 401 when no token is provided."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/api/v1/auth/refresh", json={})
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
