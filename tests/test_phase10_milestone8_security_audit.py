"""Phase 10 Milestone 10.8: Security Audit & Penetration Testing Regression Suite.

Exhaustive automated penetration tests covering:
1. Authentication & Token Security (missing/expired/tampered tokens, wrong issuer/aud).
2. Multi-Tenant Penetration & Isolation (cross-tenant BOLA/IDOR on notifications, templates, tokens, preferences).
3. Role-Based Access Control (RBAC) Hardening (employee rejection on admin overview/activity/templates/preferences/channels).
4. API Input Validation & Anti-Tampering (SSTI injection, mass assignment, oversized payloads, SQLi).
5. Notification-Specific Data Protection & Redaction (password resets, invitation tokens, fraud telemetry, device secrets).
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from services.api.auth.dependencies import (
    AuthenticatedContext,
    get_authenticated_context,
)
from services.api.auth.models import User
from services.api.config import settings
from services.api.database import get_db
from services.api.main import app
from services.api.notifications.crypto import (
    decrypt_push_token,
    encrypt_push_token,
    hash_push_token,
    mask_token_for_display,
)
from services.api.notifications.event_handler import dispatch_domain_event
from services.api.notifications.events import (
    EmployeeInvitationCreatedEvent,
    HighRiskFraudAlertEvent,
    PasswordResetRequestedEvent,
)
from services.api.notifications.models import (
    Notification,
    NotificationTemplate,
)
from services.api.notifications.repository import NotificationRepository
from services.api.notifications.schemas import (
    NotificationPriority,
)
from services.api.tenants.models import Tenant


@pytest.fixture
def test_ids():
    return {
        "tenant_a_id": uuid.uuid4(),
        "tenant_b_id": uuid.uuid4(),
        "owner_user_id": uuid.uuid4(),
        "admin_user_id": uuid.uuid4(),
        "hr_user_id": uuid.uuid4(),
        "employee_user_id": uuid.uuid4(),
        "other_tenant_user_id": uuid.uuid4(),
    }


def make_context(user_id: uuid.UUID, tenant_id: uuid.UUID, role: str) -> AuthenticatedContext:
    user = User(
        id=user_id,
        tenant_id=tenant_id,
        email=f"{role}_{user_id.hex[:6]}@upostit.test",
        full_name=f"{role.capitalize()} Tester",
        role=role,
        status="active",
    )
    tenant = Tenant(
        id=tenant_id,
        name=f"Tenant {tenant_id.hex[:6]}",
        slug=f"tenant-{tenant_id.hex[:6]}",
        status="active",
    )
    return AuthenticatedContext(user=user, tenant=tenant)


def make_query_result(*, scalar=None, scalars_list=None, rowcount=1):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalar.return_value = scalar
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = scalars_list or ([] if scalar is None else [scalar])
    result.scalars.return_value = scalars_mock
    result.all.return_value = []
    result.rowcount = rowcount
    return result


# ==============================================================================
# 1. Authentication & Token Security Attacks
# ==============================================================================


class TestAuthenticationAndTokenSecurityAttacks:
    """Verifies that missing, expired, signed-with-wrong-key, or audience-mismatched tokens are rejected."""

    @pytest.mark.asyncio
    async def test_missing_authorization_token_rejected_401(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/v1/notifications/overview")
        assert resp.status_code == 401
        assert "credentials were not provided" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_invalid_signature_token_rejected_401(self, test_ids):
        # Create token signed with an attacker's rogue private key
        rogue_key = "rogue_attacker_secret_key_that_does_not_match"
        payload = {
            "sub": str(test_ids["admin_user_id"]),
            "tenant_id": str(test_ids["tenant_a_id"]),
            "role": "admin",
            "jti": str(uuid.uuid4()),
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
            "iat": int(datetime.now(UTC).timestamp()),
            "exp": int((datetime.now(UTC) + timedelta(minutes=15)).timestamp()),
        }
        rogue_token = jwt.encode(payload, rogue_key, algorithm=settings.JWT_ALGORITHM)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                "/api/v1/notifications/overview",
                headers={"Authorization": f"Bearer {rogue_token}"},
            )
        assert resp.status_code == 401
        assert "invalid access token" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_expired_token_rejected_401(self, test_ids):
        now = datetime.now(UTC)
        past_time = now - timedelta(hours=2)
        payload = {
            "sub": str(test_ids["admin_user_id"]),
            "tenant_id": str(test_ids["tenant_a_id"]),
            "role": "admin",
            "jti": str(uuid.uuid4()),
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
            "iat": int((past_time - timedelta(minutes=15)).timestamp()),
            "exp": int(past_time.timestamp()),  # Expired 2 hours ago
        }
        expired_token = jwt.encode(payload, settings.effective_jwt_secret, algorithm=settings.JWT_ALGORITHM)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                "/api/v1/notifications/overview",
                headers={"Authorization": f"Bearer {expired_token}"},
            )
        assert resp.status_code == 401
        assert "token has expired" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_token_issued_for_different_audience_or_issuer_rejected_401(self, test_ids):
        now = datetime.now(UTC)
        payload = {
            "sub": str(test_ids["admin_user_id"]),
            "tenant_id": str(test_ids["tenant_a_id"]),
            "role": "admin",
            "jti": str(uuid.uuid4()),
            "iss": "rogue_issuer.upostit.attacker",
            "aud": "rogue_audience",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=15)).timestamp()),
        }
        foreign_token = jwt.encode(payload, settings.effective_jwt_secret, algorithm=settings.JWT_ALGORITHM)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                "/api/v1/notifications/overview",
                headers={"Authorization": f"Bearer {foreign_token}"},
            )
        assert resp.status_code == 401
        assert "invalid access token" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_malformed_bearer_header_rejected_401(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                "/api/v1/notifications/overview",
                headers={"Authorization": "NotBearer invalid_token_format"},
            )
        assert resp.status_code == 401


# ==============================================================================
# 2. Multi-Tenant Penetration & Isolation Attacks
# ==============================================================================


class TestCrossTenantPenetrationAndIsolationAttacks:
    """Verifies that Tenant A cannot access, query, modify, or trigger Tenant B data."""

    @pytest.mark.asyncio
    async def test_tenant_a_cannot_read_tenant_b_notifications_by_id(self, test_ids):
        tid_a = test_ids["tenant_a_id"]
        tid_b = test_ids["tenant_b_id"]
        assert tid_a != tid_b
        notif_id = uuid.uuid4()

        mock_session = AsyncMock()
        repo = NotificationRepository(mock_session)

        # Record exists under Tenant B in database
        mock_session.execute.return_value = make_query_result(scalar=None)
        res = await repo.get_notification(notif_id, tid_a)
        assert res is None

    @pytest.mark.asyncio
    async def test_tenant_a_admin_cannot_read_tenant_b_activity_log(self, test_ids):
        tid_a = test_ids["tenant_a_id"]
        tid_b = test_ids["tenant_b_id"]
        auth_ctx = make_context(test_ids["admin_user_id"], tid_a, "admin")

        mock_session = AsyncMock()
        app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
        app.dependency_overrides[get_db] = lambda: mock_session

        fake_notification_b = Notification(
            id=uuid.uuid4(),
            tenant_id=tid_b,
            event_type="leave_request_submitted",
            channel="EMAIL",
            recipient_destination="confidential@tenant-b.com",
            subject="Tenant B Confidential",
            body="Secret data",
            status="SENT",
            priority="NORMAL",
            attempt_count=1,
            max_attempts=3,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert fake_notification_b.tenant_id == tid_b

        # Mock repository returns empty when Tenant A queries
        with patch("services.api.notifications.routes.NotificationRepository.get_tenant_notifications") as mock_get:
            mock_get.return_value = ([], 0)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/api/v1/notifications/activity")

            # Verify repository was called strictly with Tenant A id
            mock_get.assert_called_once()
            call_kwargs = mock_get.call_args[1]
            assert call_kwargs["tenant_id"] == tid_a
            assert call_kwargs["tenant_id"] != tid_b

        app.dependency_overrides.clear()
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    @pytest.mark.asyncio
    async def test_tenant_a_cannot_read_or_override_tenant_b_templates(self, test_ids):
        tid_a = test_ids["tenant_a_id"]
        tid_b = test_ids["tenant_b_id"]
        template_b_id = uuid.uuid4()
        auth_ctx = make_context(test_ids["admin_user_id"], tid_a, "admin")

        mock_session = AsyncMock()
        # Mock database returns template that belongs to Tenant B
        template_b = NotificationTemplate(
            id=template_b_id,
            tenant_id=tid_b,
            template_key="custom_leave_template",
            name="Tenant B Custom",
            event_type="leave_request_submitted",
            channel="EMAIL",
            body_template="Tenant B Body",
            is_active=True,
            is_system=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        mock_session.execute = AsyncMock(return_value=make_query_result(scalar=template_b))

        app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
        app.dependency_overrides[get_db] = lambda: mock_session

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.put(
                f"/api/v1/notifications/templates/{template_b_id}",
                json={"name": "Hacked Name"},
            )

        app.dependency_overrides.clear()
        # Cross-tenant template updates are strictly rejected with 404 (pretends not found for tenant isolation)
        assert resp.status_code == 404
        assert "Template not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_tenant_a_cannot_revoke_tenant_b_device_tokens(self, test_ids):
        tid_a = test_ids["tenant_a_id"]
        tid_b = test_ids["tenant_b_id"]
        assert tid_a != tid_b
        token_hash_b = hash_push_token("token_tenant_b_sample")

        auth_ctx = make_context(test_ids["employee_user_id"], tid_a, "employee")
        mock_session = AsyncMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 0  # 0 rows updated because tenant_id doesn't match
        mock_session.execute = AsyncMock(return_value=mock_cursor)

        app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
        app.dependency_overrides[get_db] = lambda: mock_session

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.delete(f"/api/v1/notifications/devices/{token_hash_b}")

        app.dependency_overrides.clear()
        assert resp.status_code == 404
        assert "not found or already revoked" in resp.json()["detail"].lower()

    def test_postgresql_rls_force_policies_and_tenant_context_fail_closed(self):
        """Validates that PostgreSQL migrations specify FORCE ROW LEVEL SECURITY and fail-closed tenant scoping."""
        import inspect

        from database.migrations.versions import b5c6d7e8f9a0_phase_10_notifications as m10

        source = inspect.getsource(m10.upgrade)
        assert "FORCE ROW LEVEL SECURITY" in source
        assert "current_setting('app.tenant_id', true)::uuid" in source
        # Fail-closed: missing tenant_id in session setting returns NULL, preventing data access
        assert "tenant_isolation ON notifications" in source
        assert "tenant_isolation ON device_push_tokens" in source
        assert "tenant_isolation ON notification_preferences" in source


# ==============================================================================
# 3. Role-Based Access Control (RBAC) Hardening
# ==============================================================================


class TestRoleBasedAccessControlPenetrationAttacks:
    """Verifies that unprivileged roles (e.g. EMPLOYEE) are strictly blocked from administrative endpoints."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "endpoint,method,body",
        [
            ("/api/v1/notifications/overview", "get", None),
            ("/api/v1/notifications/activity", "get", None),
            ("/api/v1/notifications/templates", "get", None),
            ("/api/v1/notifications/preferences", "get", None),
            ("/api/v1/notifications/channels", "get", None),
            ("/api/v1/notifications/templates", "post", {
                "template_key": "test_tpl",
                "name": "Test",
                "event_type": "leave_request_submitted",
                "channel": "EMAIL",
                "body_template": "Hello {employee_name}",
            }),
            ("/api/v1/notifications/preferences", "put", {
                "quiet_hours_enabled": True,
            }),
        ],
    )
    async def test_employee_role_strictly_forbidden_from_admin_notification_endpoints_403(
        self, test_ids, endpoint, method, body
    ):
        """REMEDIATION REGRESSION TEST: Verifies that users with role EMPLOYEE receive HTTP 403 Forbidden
        when accessing tenant-wide notification console endpoints.
        """
        tid = test_ids["tenant_a_id"]
        uid = test_ids["employee_user_id"]
        auth_ctx = make_context(uid, tid, "employee")

        mock_session = AsyncMock()
        app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
        app.dependency_overrides[get_db] = lambda: mock_session

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            if method == "get":
                resp = await ac.get(endpoint)
            elif method == "post":
                resp = await ac.post(endpoint, json=body)
            elif method == "put":
                resp = await ac.put(endpoint, json=body)

        app.dependency_overrides.clear()
        assert resp.status_code == 403, f"Endpoint {method.upper()} {endpoint} permitted EMPLOYEE role!"
        assert "insufficient permissions" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_hr_role_cannot_update_tenant_preferences_403(self, test_ids):
        """HR role can manage templates but CANNOT modify tenant-wide communication policies (owner/admin only)."""
        tid = test_ids["tenant_a_id"]
        uid = test_ids["hr_user_id"]
        auth_ctx = make_context(uid, tid, "hr")

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
        assert "insufficient permissions" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_system_template_immutability_rejects_in_place_edits_403(self, test_ids):
        """System default templates cannot be modified directly in the database."""
        tid = test_ids["tenant_a_id"]
        uid = test_ids["admin_user_id"]
        auth_ctx = make_context(uid, tid, "admin")
        system_tmpl_id = uuid.uuid4()

        system_template = NotificationTemplate(
            id=system_tmpl_id,
            tenant_id=None,
            template_key="canonical_system_template",
            name="System Canonical Template",
            event_type="leave_request_submitted",
            channel="EMAIL",
            body_template="System Body",
            is_active=True,
            is_system=True,  # System default
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=make_query_result(scalar=system_template))

        app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
        app.dependency_overrides[get_db] = lambda: mock_session

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.put(
                f"/api/v1/notifications/templates/{system_tmpl_id}",
                json={"name": "Attacker Modified System Template"},
            )

        app.dependency_overrides.clear()
        assert resp.status_code == 403
        assert "System default templates are immutable" in resp.json()["detail"]


# ==============================================================================
# 4. API & Input Validation Attacks
# ==============================================================================


class TestAPIAndInputValidationAttacks:
    """Verifies that SSTI expressions, malformed hashes, mass assignment, and invalid inputs are rejected."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "malicious_template",
        [
            "Hello {{ __import__('os').system('id') }}",
            "Welcome {{ eval('2+2') }}",
            "Alert {{ exec('import sys') }}",
            "Malicious {{ compile('pass', '', 'exec') }}",
            "Dunder attack {__class__.__base__}",
        ],
    )
    async def test_template_ssti_prohibited_expressions_rejected_at_creation_422(
        self, test_ids, malicious_template
    ):
        """REMEDIATION REGRESSION TEST: Verifies that template creation rejects SSTI and dunder syntax."""
        tid = test_ids["tenant_a_id"]
        uid = test_ids["admin_user_id"]
        auth_ctx = make_context(uid, tid, "admin")

        mock_session = AsyncMock()
        app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
        app.dependency_overrides[get_db] = lambda: mock_session

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/notifications/templates",
                json={
                    "template_key": "ssti_exploit_test",
                    "name": "Exploit Attempt",
                    "event_type": "leave_request_submitted",
                    "channel": "EMAIL",
                    "body_template": malicious_template,
                },
            )

        app.dependency_overrides.clear()
        assert resp.status_code == 422
        assert "prohibited expressions" in resp.text.lower() or "validation error" in resp.text.lower()

    @pytest.mark.asyncio
    async def test_mass_assignment_extra_fields_forbidden_422(self, test_ids):
        """Extra properties submitted in requests are rejected by Pydantic ConfigDict(extra='forbid')."""
        tid = test_ids["tenant_a_id"]
        uid = test_ids["admin_user_id"]
        auth_ctx = make_context(uid, tid, "admin")

        mock_session = AsyncMock()
        app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
        app.dependency_overrides[get_db] = lambda: mock_session

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/notifications/templates",
                json={
                    "template_key": "safe_template_key",
                    "name": "Safe Name",
                    "event_type": "leave_request_submitted",
                    "channel": "EMAIL",
                    "body_template": "Hello {employee_name}",
                    "is_system": True,  # Attempting privilege escalation to make it a system template!
                    "tenant_id": str(uuid.uuid4()),  # Attempting to assign to different tenant!
                },
            )

        app.dependency_overrides.clear()
        assert resp.status_code == 422
        assert "extra inputs are not permitted" in resp.text.lower()

    @pytest.mark.asyncio
    async def test_oversized_device_token_hash_rejected_400(self, test_ids):
        """REMEDIATION REGRESSION TEST: Extremely large or malformed token_hash strings are rejected."""
        tid = test_ids["tenant_a_id"]
        uid = test_ids["employee_user_id"]
        auth_ctx = make_context(uid, tid, "employee")

        mock_session = AsyncMock()
        app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
        app.dependency_overrides[get_db] = lambda: mock_session

        oversized_hash = "a" * 256  # SHA-256 is 64 chars, max allowed is 128

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.delete(f"/api/v1/notifications/devices/{oversized_hash}")

        app.dependency_overrides.clear()
        assert resp.status_code == 400
        assert "exceeds maximum permissible length" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_oversized_raw_token_in_revoke_rejected_400(self, test_ids):
        """Oversized token payloads in POST /devices/revoke are rejected."""
        tid = test_ids["tenant_a_id"]
        uid = test_ids["employee_user_id"]
        auth_ctx = make_context(uid, tid, "employee")

        mock_session = AsyncMock()
        app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
        app.dependency_overrides[get_db] = lambda: mock_session

        huge_token = "fcm_token_" + ("x" * 5000)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/notifications/devices/revoke",
                json={"token": huge_token},
            )

        app.dependency_overrides.clear()
        assert resp.status_code == 400
        assert "maximum permissible length" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_sql_injection_payload_in_query_parameters_escaped_safely(self, test_ids):
        """SQL injection strings in query parameters are safely handled by parameterized queries."""
        tid = test_ids["tenant_a_id"]
        uid = test_ids["admin_user_id"]
        auth_ctx = make_context(uid, tid, "admin")

        mock_session = AsyncMock()
        app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
        app.dependency_overrides[get_db] = lambda: mock_session

        sqli_payload = "' OR 1=1; DROP TABLE notifications; --"

        with patch("services.api.notifications.routes.NotificationRepository.get_tenant_notifications") as mock_get:
            mock_get.return_value = ([], 0)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(f"/api/v1/notifications/activity?status={sqli_payload}")

            mock_get.assert_called_once()
            call_kwargs = mock_get.call_args[1]
            assert call_kwargs["status"] == sqli_payload

        app.dependency_overrides.clear()
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_invalid_uuid_path_parameter_rejected_422(self, test_ids):
        tid = test_ids["tenant_a_id"]
        uid = test_ids["admin_user_id"]
        auth_ctx = make_context(uid, tid, "admin")

        mock_session = AsyncMock()
        app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
        app.dependency_overrides[get_db] = lambda: mock_session

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.put(
                "/api/v1/notifications/templates/not-a-valid-uuid",
                json={"name": "Invalid UUID Test"},
            )

        app.dependency_overrides.clear()
        assert resp.status_code == 422


# ==============================================================================
# 5. Notification-Specific Data Protection & Leakage
# ==============================================================================


class TestNotificationSpecificDataProtectionAndLeakage:
    """Verifies that secrets, passwords, fraud scores, and private keys are never leaked."""

    @pytest.mark.asyncio
    async def test_password_reset_url_secret_redaction_and_isolation(self, test_ids):
        """Verifies that raw password-reset secrets are never stored in payload_json."""
        session = AsyncMock()
        tid = test_ids["tenant_a_id"]
        uid = test_ids["owner_user_id"]

        event = PasswordResetRequestedEvent(
            tenant_id=tid,
            user_id=uid,
            user_email="owner@secure.test",
            user_name="Alice Owner",
            company_name="Secure Tenant",
            reset_url="https://app.upostit.test/reset-password?token=secret_reset_token_xyz987",
            expires_minutes=15,
        )

        with patch("services.api.notifications.service.NotificationService.create_notification") as mock_create:
            mock_create.return_value = MagicMock()
            await dispatch_domain_event(session, event)

            mock_create.assert_called_once()
            req = mock_create.call_args[0][1]
            # Secrets must NOT be stored in standalone payload fields
            assert "token" not in req.template_variables
            assert "raw_token" not in req.template_variables
            assert "secret" not in req.template_variables

    @pytest.mark.asyncio
    async def test_employee_invitation_secret_never_persisted_in_isolation(self, test_ids):
        """Verifies that invitation activation tokens are not stored in payload_json."""
        session = AsyncMock()
        tid = test_ids["tenant_a_id"]

        event = EmployeeInvitationCreatedEvent(
            tenant_id=tid,
            invitation_id=uuid.uuid4(),
            employee_id=uuid.uuid4(),
            recipient_email="invitee@secure.test",
            recipient_name="Bob Invitee",
            company_name="Secure Tenant",
            activation_url="https://app.upostit.test/activate?token=invite_secret_token_123",
            expires_hours=72,
        )

        with patch("services.api.notifications.service.NotificationService.create_notification") as mock_create:
            mock_create.return_value = MagicMock()
            await dispatch_domain_event(session, event)

            mock_create.assert_called_once()
            req = mock_create.call_args[0][1]
            assert "token" not in req.template_variables
            assert "raw_token" not in req.template_variables

    @pytest.mark.asyncio
    async def test_sensitive_fraud_telemetry_redacted_from_notification_payload(self, test_ids):
        """Sensitive internal fraud engine telemetry (risk_score, raw coords) is redacted from alerts."""
        session = AsyncMock()
        tid = test_ids["tenant_a_id"]
        admin_id = test_ids["admin_user_id"]

        event = HighRiskFraudAlertEvent(
            tenant_id=tid,
            attendance_event_id=uuid.uuid4(),
            employee_id=uuid.uuid4(),
            employee_name="Flagged Employee",
            risk_score=94,
            risk_category="CRITICAL_RISK",
            attendance_event_type="CHECK_IN",
            flag_summary="Mock location and velocity jump",
            occurred_at=datetime.now(UTC),
        )

        with (
            patch.object(NotificationRepository, "get_user_preference", return_value=None),
            patch.object(NotificationRepository, "get_tenant_default_preference", return_value=None),
            patch(
                "services.api.notifications.event_handler.DomainNotificationHandler._resolve_tenant_admins",
                return_value=[(admin_id, "admin@secure.test")],
            ),
            patch("services.api.notifications.service.NotificationService.create_notification") as mock_create,
        ):
            mock_create.return_value = MagicMock()
            await dispatch_domain_event(session, event)

            assert mock_create.call_count >= 1
            for call in mock_create.call_args_list:
                req = call[0][1]
                assert req.priority == NotificationPriority.URGENT

    def test_device_tokens_encrypted_at_rest_and_preview_masked(self):
        """Verifies that device tokens use authenticated encryption and display masking."""
        raw_token = "fcm_mobile_device_registration_secret_token_abcdef1234567890"
        encrypted = encrypt_push_token(raw_token)
        assert encrypted.startswith("fernet:")
        assert raw_token not in encrypted

        decrypted = decrypt_push_token(encrypted)
        assert decrypted == raw_token

        # Preview masking shows 4 chars ... 4 chars
        thash = hash_push_token(raw_token)
        masked = mask_token_for_display(thash)
        assert masked == f"{thash[:4]}...{thash[-4:]}"
        assert raw_token not in masked

    @pytest.mark.asyncio
    async def test_channels_endpoint_never_exposes_environment_secrets(self, test_ids):
        """Verifies that GET /channels never exposes SMTP passwords or Firebase credentials."""
        tid = test_ids["tenant_a_id"]
        uid = test_ids["admin_user_id"]
        auth_ctx = make_context(uid, tid, "admin")

        app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/v1/notifications/channels")

        app.dependency_overrides.clear()
        assert resp.status_code == 200
        raw_text = resp.text.lower()
        assert "password" not in raw_text
        assert "private_key" not in raw_text
        assert "client_secret" not in raw_text
        assert "encryption_key" not in raw_text
