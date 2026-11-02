"""Integration tests for Phase 4 workplace locations API endpoints, auth, and RBAC."""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from services.api.auth.dependencies import AuthenticatedContext, get_authenticated_context
from services.api.auth.models import User
from services.api.database import get_db
from services.api.locations.models import Location
from services.api.main import app
from services.api.tenants.models import Tenant


def _mock_context(role: str, tenant_id: uuid.UUID | None = None) -> AuthenticatedContext:
    tid = tenant_id or uuid.uuid4()
    user = User(
        id=uuid.uuid4(),
        tenant_id=tid,
        email=f"test_{role}@corp.test",
        password_hash="argon2id$mock",
        role=role,
        status="active",
    )
    tenant = Tenant(
        id=tid,
        name="Test Corp",
        slug=f"test-{tid.hex[:6]}",
        company_email="admin@corp.test",
        country_code="IN",
        status="active",
    )
    return AuthenticatedContext(user=user, tenant=tenant)


@pytest.mark.asyncio
async def test_locations_endpoints_require_authentication():
    """Verify all /locations endpoints return 401 when no auth token is provided."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res1 = await client.get("/api/v1/locations")
        assert res1.status_code == 401

        res2 = await client.post("/api/v1/locations", json={})
        assert res2.status_code == 401

        res3 = await client.get(f"/api/v1/locations/{uuid.uuid4()}")
        assert res3.status_code == 401

        res4 = await client.put(f"/api/v1/locations/{uuid.uuid4()}", json={})
        assert res4.status_code == 401

        res5 = await client.delete(f"/api/v1/locations/{uuid.uuid4()}")
        assert res5.status_code == 401

        res6 = await client.post("/api/v1/locations/verify-coordinates", json={})
        assert res6.status_code == 401


@pytest.mark.asyncio
async def test_employee_role_forbidden_from_locations():
    """Verify EMPLOYEE role is forbidden from viewing or managing organizational locations."""
    auth_ctx = _mock_context("employee")
    app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # GET /locations -> 403 Forbidden
        res = await client.get("/api/v1/locations")
        assert res.status_code == 403

        # POST /locations -> 403 Forbidden
        res2 = await client.post("/api/v1/locations", json={"name": "Test"})
        assert res2.status_code == 403

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_hr_role_cannot_manage_locations():
    """Verify HR role has view-only access to locations and cannot mutate them."""
    auth_ctx = _mock_context("hr")
    mock_db = AsyncMock()

    app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
    app.dependency_overrides[get_db] = lambda: mock_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # POST /locations -> 403 Forbidden for HR
        res = await client.post(
            "/api/v1/locations",
            json={
                "name": "Branch",
                "code": "BR-01",
                "address_line1": "Street 1",
                "city": "City",
                "country_code": "IN",
                "latitude": 12.92,
                "longitude": 77.67,
                "timezone": "Asia/Kolkata",
            },
        )
        assert res.status_code == 403

        # DELETE /locations/{id} -> 403 Forbidden for HR
        res_del = await client.delete(f"/api/v1/locations/{uuid.uuid4()}")
        assert res_del.status_code == 403

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_create_location_success():
    """Verify ADMIN role can create a workplace location successfully."""
    auth_ctx = _mock_context("admin")
    mock_db = AsyncMock()
    mock_db.add = MagicMock()

    # Mock duplicate check -> None
    res_none = MagicMock()
    res_none.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = res_none

    app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
    app.dependency_overrides[get_db] = lambda: mock_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "name": "Bengaluru Development Hub",
            "code": "BLR-DEV-01",
            "address_line1": "Outer Ring Road",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postal_code": "560103",
            "country_code": "IN",
            "latitude": 12.9249000,
            "longitude": 77.6744000,
            "radius_meters": 150,
            "timezone": "Asia/Kolkata",
            "wifi_bssids": ["00:1A:2B:3C:4D:5E"],
            "ip_ranges": ["198.51.100.0/24"],
        }
        res = await client.post("/api/v1/locations", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["name"] == "Bengaluru Development Hub"
        assert data["code"] == "BLR-DEV-01"
        assert data["country_code"] == "IN"
        assert data["timezone"] == "Asia/Kolkata"
        assert data["radius_meters"] == 150
        assert data["is_active"] is True

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_verify_geofence_coordinates_endpoint():
    """Verify POST /locations/verify-coordinates endpoint returns spatial distance calculation."""
    auth_ctx = _mock_context("admin")
    mock_db = AsyncMock()

    loc_id = uuid.uuid4()
    loc = Location(
        id=loc_id,
        tenant_id=auth_ctx.tenant.id,
        name="Campus",
        code="CAMP-01",
        address_line1="1 Campus Way",
        city="Pune",
        country_code="IN",
        latitude=Decimal("18.5204000"),
        longitude=Decimal("73.8567000"),
        radius_meters=100,
        timezone="Asia/Kolkata",
        is_active=True,
    )
    res_loc = MagicMock()
    res_loc.scalar_one_or_none.return_value = loc
    mock_db.execute.return_value = res_loc

    app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
    app.dependency_overrides[get_db] = lambda: mock_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "location_id": str(loc_id),
            "latitude": 18.5205000,
            "longitude": 73.8567000,
        }
        res = await client.post("/api/v1/locations/verify-coordinates", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["location_id"] == str(loc_id)
        assert data["within_geofence"] is True
        assert data["distance_meters"] <= 100
        assert "ST_DWithin verifies mathematical proximity" in data["threat_boundary_notice"]

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_validation_errors_return_422():
    """Verify schema validation failures return structured HTTP 422 with actionable messages."""
    auth_ctx = _mock_context("admin")
    app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Invalid country code, invalid timezone, radius too large
        payload = {
            "name": "Office",
            "code": "OFF-01",
            "address_line1": "Street",
            "city": "City",
            "country_code": "INVALID",
            "latitude": 12.0,
            "longitude": 77.0,
            "radius_meters": 999999,
            "timezone": "Fake/Timezone",
        }
        res = await client.post("/api/v1/locations", json=payload)
        assert res.status_code == 422
        body = res.json()
        errors = str(body["detail"])
        assert "country_code" in errors or "Invalid country code" in errors

    app.dependency_overrides.clear()
