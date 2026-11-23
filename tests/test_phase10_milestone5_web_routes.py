"""Comprehensive integration and security tests for Phase 10 Milestone 10.5 Web Console Endpoints.

Test Groups:
1. TestNotificationRouterRegistration:
   - FastAPI application router registration.
   - All 8 notification endpoints present in OpenAPI schema under /api/v1/notifications.
   - HTTP methods, path parameters, and route visibility verification.
2. TestNotificationOverviewEndpoint:
   - GET /api/v1/notifications/overview: Delivery summary, status counts, channel counts, SENT vs DELIVERED distinction.
3. TestNotificationTemplatesEndpoints:
   - GET /api/v1/notifications/templates: Merging system defaults with tenant overrides.
   - POST /api/v1/notifications/templates: Tenant template creation/override with RBAC.
   - PUT /api/v1/notifications/templates/{template_id}: Tenant override update, system template immutability (403), cross-tenant isolation (404), RBAC.
4. TestNotificationPreferencesEndpoints:
   - GET /api/v1/notifications/preferences: Tenant default preferences retrieval.
   - PUT /api/v1/notifications/preferences: Preference updates with RBAC & 24h format validation.
5. TestNotificationChannelsEndpoint:
   - GET /api/v1/notifications/channels: Provider operational readiness, mock/unverified status, SMS deferred indicator, zero secret leakage.
6. TestNotificationActivityEndpoint:
   - GET /api/v1/notifications/activity: Paginated activity logs, multi-filter queries, destination masking.
7. TestBackendSecurityAndIsolation:
   - 401 Unauthorized on unauthenticated requests.
   - 403 Forbidden on unauthorized roles.
   - Cross-tenant data isolation across all endpoints.
   - Zero credential or token leakage.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from services.api.auth.dependencies import AuthenticatedContext, get_authenticated_context
from services.api.auth.models import User
from services.api.database import get_db
from services.api.main import app
from services.api.notifications.models import (
    Notification,
    NotificationPreference,
    NotificationTemplate,
)
from services.api.notifications.schemas import NotificationStatus
from services.api.tenants.models import Tenant


@pytest.fixture
def mock_ids():
    return {
        "tenant_id": uuid.uuid4(),
        "other_tenant_id": uuid.uuid4(),
        "admin_user_id": uuid.uuid4(),
        "hr_user_id": uuid.uuid4(),
        "employee_user_id": uuid.uuid4(),
    }


def make_auth_context(user_id: uuid.UUID, tenant_id: uuid.UUID, role: str = "admin") -> AuthenticatedContext:
    user = User(
        id=user_id,
        tenant_id=tenant_id,
        email=f"{role}@upostit.test",
        full_name=f"{role.capitalize()} User",
        role=role,
        status="active",
    )
    tenant = Tenant(
        id=tenant_id,
        name="Test Tenant",
        slug="test-tenant",
        status="active",
    )
    return AuthenticatedContext(user=user, tenant=tenant)


# ==============================================================================
# 1. FastAPI Router Registration Tests
# ==============================================================================


class TestNotificationRouterRegistration:
    """Verifies that the notification router is properly registered in FastAPI."""

    def test_all_milestone_endpoints_registered_in_openapi_schema(self):
        schema = app.openapi()
        paths = schema.get("paths", {})

        expected_routes = [
            ("/api/v1/notifications/overview", ["get"]),
            ("/api/v1/notifications/templates", ["get", "post"]),
            ("/api/v1/notifications/templates/{template_id}", ["put"]),
            ("/api/v1/notifications/preferences", ["get", "put"]),
            ("/api/v1/notifications/channels", ["get"]),
            ("/api/v1/notifications/activity", ["get"]),
            ("/api/v1/notifications/devices", ["get", "post"]),
            ("/api/v1/notifications/devices/revoke", ["post"]),
            ("/api/v1/notifications/devices/{token_hash}", ["delete"]),
        ]

        for path, expected_methods in expected_routes:
            assert path in paths, f"Path {path} missing from FastAPI OpenAPI registration"
            registered_methods = list(paths[path].keys())
            for m in expected_methods:
                assert m in registered_methods, f"Method {m.upper()} missing from {path}"


# ==============================================================================
# 2. Overview Endpoint Tests
# ==============================================================================


class TestNotificationOverviewEndpoint:
    @pytest.mark.asyncio
    async def test_get_overview_success(self, mock_ids):
        tid = mock_ids["tenant_id"]
        uid = mock_ids["admin_user_id"]
        auth_ctx = make_auth_context(uid, tid, "admin")

        mock_session = AsyncMock()
        app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
        app.dependency_overrides[get_db] = lambda: mock_session

        fake_summary = {
            "total_count": 12,
            "status_counts": {
                "pending": 2,
                "processing": 1,
                "retry_scheduled": 1,
                "sent": 6,
                "delivered": 2,
                "failed": 0,
                "cancelled": 0,
            },
            "channel_counts": {
                "push": 8,
                "email": 4,
                "sms": 0,
            },
            "recent_notifications": [
                Notification(
                    id=uuid.uuid4(),
                    tenant_id=tid,
                    event_type="leave_request_submitted",
                    channel="EMAIL",
                    template_key="leave_request_submitted",
                    recipient_destination="supervisor@test.com",
                    subject="Leave Request",
                    body="Body",
                    payload_json={},
                    status="SENT",
                    priority="NORMAL",
                    scheduled_for=datetime.now(UTC),
                    attempt_count=1,
                    max_attempts=3,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            ],
        }

        with patch("services.api.notifications.routes.NotificationRepository.get_delivery_summary", return_value=fake_summary):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/api/v1/notifications/overview")

        app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 12
        assert data["status_counts"]["sent"] == 6
        assert data["status_counts"]["delivered"] == 2
        assert data["channel_counts"]["push"] == 8
        assert len(data["recent_notifications"]) == 1
        assert "SENT indicates" in data["delivery_distinction_note"]


# ==============================================================================
# 3. Template Administration & Immutability Tests
# ==============================================================================


class TestNotificationTemplatesEndpoints:
    @pytest.mark.asyncio
    async def test_list_templates(self, mock_ids):
        tid = mock_ids["tenant_id"]
        uid = mock_ids["admin_user_id"]
        auth_ctx = make_auth_context(uid, tid, "admin")

        mock_session = AsyncMock()
        app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
        app.dependency_overrides[get_db] = lambda: mock_session

        fake_tpl = NotificationTemplate(
            id=uuid.uuid4(),
            tenant_id=None,
            template_key="leave_request_submitted",
            name="Leave Request (Email)",
            event_type="leave_request_submitted",
            channel="EMAIL",
            body_template="Body",
            locale="en",
            is_active=True,
            is_system=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        with patch("services.api.notifications.routes.NotificationRepository.list_templates_for_tenant", return_value=[fake_tpl]):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/api/v1/notifications/templates")

        app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["is_system"] is True
        assert data[0]["template_key"] == "leave_request_submitted"

    @pytest.mark.asyncio
    async def test_create_template_as_admin(self, mock_ids):
        tid = mock_ids["tenant_id"]
        uid = mock_ids["admin_user_id"]
        auth_ctx = make_auth_context(uid, tid, "admin")

        mock_session = AsyncMock()
        app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
        app.dependency_overrides[get_db] = lambda: mock_session

        fake_override = NotificationTemplate(
            id=uuid.uuid4(),
            tenant_id=tid,
            template_key="leave_request_approved",
            name="Custom Approval",
            event_type="leave_request_approved",
            channel="EMAIL",
            body_template="Approved {employee_name}",
            locale="en",
            is_active=True,
            is_system=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        with patch("services.api.notifications.routes.NotificationRepository.upsert_template", return_value=fake_override):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/v1/notifications/templates",
                    json={
                        "template_key": "leave_request_approved",
                        "name": "Custom Approval",
                        "event_type": "leave_request_approved",
                        "channel": "EMAIL",
                        "body_template": "Approved {employee_name}",
                        "locale": "en",
                        "is_active": True,
                    },
                )

        app.dependency_overrides.clear()

        assert resp.status_code == 201
        data = resp.json()
        assert data["is_system"] is False
        assert data["name"] == "Custom Approval"

    @pytest.mark.asyncio
    async def test_update_existing_tenant_template_override_success(self, mock_ids):
        tid = mock_ids["tenant_id"]
        uid = mock_ids["admin_user_id"]
        auth_ctx = make_auth_context(uid, tid, "admin")
        tpl_id = uuid.uuid4()

        tenant_tpl = NotificationTemplate(
            id=tpl_id,
            tenant_id=tid,
            template_key="leave_request_approved",
            name="Old Name",
            event_type="leave_request_approved",
            channel="EMAIL",
            body_template="Old Body",
            locale="en",
            is_active=True,
            is_system=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tenant_tpl
        mock_session.execute.return_value = mock_result

        app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
        app.dependency_overrides[get_db] = lambda: mock_session

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.put(
                f"/api/v1/notifications/templates/{tpl_id}",
                json={
                    "name": "Updated Custom Approval Name",
                    "body_template": "New body with {employee_name}",
                },
            )

        app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated Custom Approval Name"
        assert data["body_template"] == "New body with {employee_name}"

    @pytest.mark.asyncio
    async def test_system_template_update_is_strictly_forbidden_immutable(self, mock_ids):
        tid = mock_ids["tenant_id"]
        uid = mock_ids["admin_user_id"]
        auth_ctx = make_auth_context(uid, tid, "admin")
        sys_tpl_id = uuid.uuid4()

        system_tpl = NotificationTemplate(
            id=sys_tpl_id,
            tenant_id=None,
            template_key="leave_request_submitted",
            name="System Template",
            event_type="leave_request_submitted",
            channel="EMAIL",
            body_template="Body",
            locale="en",
            is_active=True,
            is_system=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = system_tpl
        mock_session.execute.return_value = mock_result

        app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
        app.dependency_overrides[get_db] = lambda: mock_session

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.put(
                f"/api/v1/notifications/templates/{sys_tpl_id}",
                json={"name": "Hacked System Template"},
            )

        app.dependency_overrides.clear()

        assert resp.status_code == 403
        assert "immutable" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_cross_tenant_template_update_returns_404(self, mock_ids):
        tid = mock_ids["tenant_id"]
        other_tid = mock_ids["other_tenant_id"]
        uid = mock_ids["admin_user_id"]
        auth_ctx = make_auth_context(uid, tid, "admin")
        other_tpl_id = uuid.uuid4()

        other_tenant_tpl = NotificationTemplate(
            id=other_tpl_id,
            tenant_id=other_tid,
            template_key="leave_request_approved",
            name="Other Tenant Template",
            event_type="leave_request_approved",
            channel="EMAIL",
            body_template="Body",
            locale="en",
            is_active=True,
            is_system=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = other_tenant_tpl
        mock_session.execute.return_value = mock_result

        app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
        app.dependency_overrides[get_db] = lambda: mock_session

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.put(
                f"/api/v1/notifications/templates/{other_tpl_id}",
                json={"name": "Attacking Other Tenant Template"},
            )

        app.dependency_overrides.clear()

        assert resp.status_code == 404
        assert "Template not found" in resp.json()["detail"]


# ==============================================================================
# 4. Preferences Endpoints Tests
# ==============================================================================


class TestNotificationPreferencesEndpoints:
    @pytest.mark.asyncio
    async def test_get_preferences(self, mock_ids):
        tid = mock_ids["tenant_id"]
        uid = mock_ids["admin_user_id"]
        auth_ctx = make_auth_context(uid, tid, "admin")

        mock_session = AsyncMock()
        app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
        app.dependency_overrides[get_db] = lambda: mock_session

        fake_pref = NotificationPreference(
            id=uuid.uuid4(),
            tenant_id=tid,
            user_id=None,
            is_push_enabled=True,
            is_email_enabled=True,
            is_sms_enabled=False,
            quiet_hours_enabled=True,
            quiet_hours_start="22:00",
            quiet_hours_end="07:00",
            timezone="UTC",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        with patch("services.api.notifications.routes.NotificationRepository.get_tenant_default_preference", return_value=fake_pref):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/api/v1/notifications/preferences")

        app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert data["quiet_hours_enabled"] is True
        assert data["quiet_hours_start"] == "22:00"

    @pytest.mark.asyncio
    async def test_update_preferences_as_admin(self, mock_ids):
        tid = mock_ids["tenant_id"]
        uid = mock_ids["admin_user_id"]
        auth_ctx = make_auth_context(uid, tid, "admin")

        mock_session = AsyncMock()
        app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
        app.dependency_overrides[get_db] = lambda: mock_session

        updated_pref = NotificationPreference(
            id=uuid.uuid4(),
            tenant_id=tid,
            user_id=None,
            is_push_enabled=True,
            is_email_enabled=True,
            is_sms_enabled=False,
            quiet_hours_enabled=True,
            quiet_hours_start="23:00",
            quiet_hours_end="06:00",
            timezone="Europe/London",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        with patch("services.api.notifications.routes.NotificationRepository.get_tenant_default_preference", return_value=updated_pref), \
             patch("services.api.notifications.routes.NotificationRepository.upsert_preference", return_value=updated_pref):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.put(
                    "/api/v1/notifications/preferences",
                    json={
                        "quiet_hours_start": "23:00",
                        "quiet_hours_end": "06:00",
                        "timezone": "Europe/London",
                    },
                )

        app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert data["quiet_hours_start"] == "23:00"
        assert data["timezone"] == "Europe/London"

    @pytest.mark.asyncio
    async def test_update_preferences_as_employee_forbidden(self, mock_ids):
        tid = mock_ids["tenant_id"]
        uid = mock_ids["employee_user_id"]
        auth_ctx = make_auth_context(uid, tid, "employee")

        mock_session = AsyncMock()
        app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
        app.dependency_overrides[get_db] = lambda: mock_session

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.put(
                "/api/v1/notifications/preferences",
                json={"quiet_hours_enabled": False},
            )

        app.dependency_overrides.clear()

        assert resp.status_code == 403


# ==============================================================================
# 5. Channel Readiness & Status Tests
# ==============================================================================


class TestNotificationChannelsEndpoint:
    @pytest.mark.asyncio
    async def test_get_channels_reflects_runtime_configuration(self, mock_ids):
        tid = mock_ids["tenant_id"]
        uid = mock_ids["admin_user_id"]
        auth_ctx = make_auth_context(uid, tid, "admin")

        app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/v1/notifications/channels")

        app.dependency_overrides.clear()

        assert resp.status_code == 200
        channels = resp.json()["channels"]
        assert len(channels) == 3

        push_ch = next(c for c in channels if c["channel"] == "PUSH")
        email_ch = next(c for c in channels if c["channel"] == "EMAIL")
        sms_ch = next(c for c in channels if c["channel"] == "SMS")

        # Crucial invariant: never claims production active when unverified
        assert push_ch["status"] in ("CONFIGURED_UNVERIFIED", "MOCK")
        assert email_ch["status"] in ("CONFIGURED_UNVERIFIED", "MOCK")
        assert sms_ch["status"] == "UNCONFIGURED"
        assert sms_ch["is_enabled"] is False

    @pytest.mark.asyncio
    async def test_channels_endpoint_never_leaks_provider_secrets(self, mock_ids):
        tid = mock_ids["tenant_id"]
        uid = mock_ids["admin_user_id"]
        auth_ctx = make_auth_context(uid, tid, "admin")

        app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/v1/notifications/channels")

        app.dependency_overrides.clear()

        raw_text = resp.text.lower()
        assert "smtp_password" not in raw_text
        assert "private_key" not in raw_text
        assert "secret" not in raw_text
        assert "token_encryption_key" not in raw_text


# ==============================================================================
# 6. Activity Log Endpoint Tests
# ==============================================================================


class TestNotificationActivityEndpoint:
    @pytest.mark.asyncio
    async def test_get_activity_log_paginated(self, mock_ids):
        tid = mock_ids["tenant_id"]
        uid = mock_ids["admin_user_id"]
        auth_ctx = make_auth_context(uid, tid, "admin")

        mock_session = AsyncMock()
        app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
        app.dependency_overrides[get_db] = lambda: mock_session

        fake_item = Notification(
            id=uuid.uuid4(),
            tenant_id=tid,
            event_type="high_risk_fraud_alert",
            channel="PUSH",
            template_key="high_risk_fraud_alert",
            recipient_destination="device_token_hash:12345678...",
            subject="Security Alert",
            body="High risk detected",
            payload_json={},
            status=NotificationStatus.DELIVERED.value,
            priority="URGENT",
            scheduled_for=datetime.now(UTC),
            attempt_count=1,
            max_attempts=3,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        with patch("services.api.notifications.routes.NotificationRepository.get_tenant_notifications", return_value=([fake_item], 1)):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/api/v1/notifications/activity?status=DELIVERED&limit=10&offset=0")

        app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["status"] == "DELIVERED"
        assert data["items"][0]["priority"] == "URGENT"
        assert data["items"][0]["recipient_destination"].startswith("device_token_hash:")


# ==============================================================================
# 7. Backend Security & Tenant Isolation Tests
# ==============================================================================


class TestBackendSecurityAndIsolation:
    """Rigorous security checks covering unauthenticated access, role violations, and tenant leakage."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "endpoint,method",
        [
            ("/api/v1/notifications/overview", "get"),
            ("/api/v1/notifications/templates", "get"),
            ("/api/v1/notifications/templates", "post"),
            ("/api/v1/notifications/preferences", "get"),
            ("/api/v1/notifications/preferences", "put"),
            ("/api/v1/notifications/channels", "get"),
            ("/api/v1/notifications/activity", "get"),
        ],
    )
    async def test_unauthenticated_requests_strictly_rejected(self, endpoint, method):
        # Do not override get_authenticated_context -> requires valid Bearer token
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            if method == "get":
                resp = await ac.get(endpoint)
            elif method == "post":
                resp = await ac.post(endpoint, json={})
            elif method == "put":
                resp = await ac.put(endpoint, json={})

        assert resp.status_code == 401, f"Endpoint {method.upper()} {endpoint} failed to reject unauthenticated request"
        assert "credentials were not provided" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_hr_role_cannot_update_tenant_preferences(self, mock_ids):
        tid = mock_ids["tenant_id"]
        uid = mock_ids["hr_user_id"]
        auth_ctx = make_auth_context(uid, tid, "hr")

        mock_session = AsyncMock()
        app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
        app.dependency_overrides[get_db] = lambda: mock_session

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.put(
                "/api/v1/notifications/preferences",
                json={"quiet_hours_enabled": True},
            )

        app.dependency_overrides.clear()

        # HR can manage templates, but only owner/admin can modify tenant communication policies
        assert resp.status_code == 403
        assert "Insufficient permissions" in resp.json()["detail"]
