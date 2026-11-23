"""Comprehensive unit and contract test suite for Phase 10 Milestone 10.3:
FCM Push Integration, Device Token Registration APIs & Celery Dispatch Workers.

Test Groups:
1. TestFirebasePushProvider: Mocked Firebase Admin SDK, error classifications, Android/iOS configurations, unconfigured credentials handling.
2. TestDevicePushTokenAPIs: FastAPI endpoints (/api/v1/notifications/devices), user scoping, token rotation, revocation, masked previews.
3. TestNotificationCeleryTasks: Asynchronous task execution, batch processing, stuck PROCESSING reconciliation, dead-letter preservation.
4. TestTokenAuthenticatedEncryption: Fernet AEAD security, PBKDF2 key derivation, rejection of plaintext fallback, tampering detection.
"""

import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from firebase_admin import exceptions, messaging
from httpx import ASGITransport, AsyncClient

from services.api.auth.dependencies import AuthenticatedContext, get_authenticated_context
from services.api.auth.models import User
from services.api.database import get_db
from services.api.main import app
from services.api.notifications.crypto import (
    EncryptionConfigError,
    TokenEncryptionError,
    decrypt_push_token,
    derive_fernet_key_from_secret,
    encrypt_push_token,
    hash_push_token,
    mask_token_for_display,
)
from services.api.notifications.exceptions import (
    ProviderPermanentError,
    ProviderTimeoutError,
)
from services.api.notifications.fcm_provider import FirebasePushProvider
from services.api.notifications.models import DevicePushToken, Notification
from services.api.notifications.schemas import (
    NotificationStatus,
    ProviderStatus,
)
from services.api.tenants.models import Tenant
from services.workers.notification_tasks import (
    cleanup_revoked_tokens_task,
    dispatch_batch_notifications_task,
    dispatch_single_notification_task,
    reconcile_stuck_processing_task,
)

# ==============================================================================
# 1. FCM Provider Adapter Tests
# ==============================================================================


class TestFirebasePushProvider:
    """Verifies Firebase Cloud Messaging adapter behavior, error classification, and platform configs."""

    def test_unconfigured_credentials_raises_permanent_error(self):
        with patch.object(FirebasePushProvider, "_initialize_app", return_value=None):
            provider = FirebasePushProvider()
            provider._is_configured = False
            provider._app = None

            with pytest.raises(ProviderPermanentError) as exc_info:
                import asyncio

                asyncio.run(provider.send("valid_token_1234567890", "Title", "Body"))
            assert "FCM provider credentials unconfigured" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_invalid_destination_token_returns_failure(self):
        provider = FirebasePushProvider.__new__(FirebasePushProvider)
        provider.name = "fcm"
        provider._is_configured = True
        provider._app = MagicMock()

        # Placeholder user token
        result = await provider.send("user:12345", "Title", "Body")
        assert result.success is False
        assert result.status == ProviderStatus.FAILED
        assert result.is_retryable is False
        assert "Invalid or placeholder destination token" in (result.error_message or "")

    @pytest.mark.asyncio
    async def test_successful_provider_acceptance(self):
        provider = FirebasePushProvider.__new__(FirebasePushProvider)
        provider.name = "fcm"
        provider._is_configured = True
        provider._app = MagicMock()

        mock_send = MagicMock(return_value="projects/test-project/messages/msg-123456")

        with patch("services.api.notifications.fcm_provider.messaging.send", mock_send):
            result = await provider.send(
                recipient_destination="valid_fcm_device_token_abcdef1234567890",
                subject="Shift Notice",
                body="Your shift begins in 15 minutes",
                payload={"event_type": "SHIFT_ALERT", "shift_id": "100"},
            )

            assert result.success is True
            assert result.status == ProviderStatus.ACCEPTED
            assert result.provider_name == "fcm"
            assert result.provider_message_id == "projects/test-project/messages/msg-123456"
            assert result.is_retryable is False

            # Verify Android & iOS APNs configs were created
            assert mock_send.called
            message_arg = mock_send.call_args[0][0]
            assert isinstance(message_arg, messaging.Message)
            assert message_arg.notification.title == "Shift Notice"
            assert message_arg.notification.body == "Your shift begins in 15 minutes"
            assert message_arg.android.priority == "high"
            assert message_arg.apns.headers["apns-priority"] == "10"
            assert message_arg.data == {"event_type": "SHIFT_ALERT", "shift_id": "100"}

    @pytest.mark.asyncio
    async def test_unregistered_token_is_unretryable(self):
        provider = FirebasePushProvider.__new__(FirebasePushProvider)
        provider.name = "fcm"
        provider._is_configured = True
        provider._app = MagicMock()

        def _raise_unregistered(*args, **kwargs):
            raise messaging.UnregisteredError("App instance unregistered")

        with patch("services.api.notifications.fcm_provider.messaging.send", side_effect=_raise_unregistered):
            result = await provider.send(
                recipient_destination="unregistered_device_token_abcdef12345",
                subject="Title",
                body="Body",
            )
            assert result.success is False
            assert result.status == ProviderStatus.FAILED
            assert result.is_retryable is False
            assert "unregistered or expired" in (result.error_message or "")

    @pytest.mark.asyncio
    async def test_quota_exceeded_or_unavailable_is_retryable(self):
        provider = FirebasePushProvider.__new__(FirebasePushProvider)
        provider.name = "fcm"
        provider._is_configured = True
        provider._app = MagicMock()

        def _raise_unavailable(*args, **kwargs):
            raise exceptions.UnavailableError("FCM service temporarily unavailable")

        with patch("services.api.notifications.fcm_provider.messaging.send", side_effect=_raise_unavailable):
            result = await provider.send(
                recipient_destination="valid_device_token_abcdef1234567890",
                subject="Title",
                body="Body",
            )
            assert result.success is False
            assert result.status == ProviderStatus.FAILED
            assert result.is_retryable is True
            assert "throttled or unavailable" in (result.error_message or "")

    @pytest.mark.asyncio
    async def test_fcm_timeout_raises_provider_timeout(self):
        provider = FirebasePushProvider.__new__(FirebasePushProvider)
        provider.name = "fcm"
        provider._is_configured = True
        provider._app = MagicMock()

        def _raise_timeout(*args, **kwargs):
            raise TimeoutError("Socket connection timed out")

        with patch("services.api.notifications.fcm_provider.messaging.send", side_effect=_raise_timeout):
            with pytest.raises(ProviderTimeoutError) as exc_info:
                await provider.send(
                    recipient_destination="valid_device_token_abcdef1234567890",
                    subject="Title",
                    body="Body",
                )
            assert exc_info.value.is_retryable is True


# ==============================================================================
# 2. Device Token Registration API Tests
# ==============================================================================


class TestDevicePushTokenAPIs:
    """Verifies FastAPI endpoints for device token registration, rotation, and revocation."""

    def _make_auth_context(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> AuthenticatedContext:
        user = User(
            id=user_id,
            tenant_id=tenant_id,
            email="worker@upostit.test",
            full_name="Worker User",
            role="employee",
            status="active",
        )
        tenant = Tenant(
            id=tenant_id,
            name="Test Tenant",
            slug="test-tenant",
            status="active",
        )
        return AuthenticatedContext(user=user, tenant=tenant)

    @pytest.mark.asyncio
    async def test_register_device_token_success_and_masked_preview(self):
        uid = uuid.uuid4()
        tid = uuid.uuid4()
        auth_ctx = self._make_auth_context(uid, tid)

        raw_fcm_token = "fcm_mobile_device_registration_token_1234567890_xyz"
        thash = hash_push_token(raw_fcm_token)

        mock_token_record = DevicePushToken(
            id=uuid.uuid4(),
            tenant_id=tid,
            user_id=uid,
            platform="ANDROID",
            token=encrypt_push_token(raw_fcm_token),
            token_hash=thash,
            device_model="Pixel 8",
            os_version="Android 14",
            app_version="1.0.0",
            status="ACTIVE",
            last_seen_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        with patch("services.api.notifications.routes.NotificationRepository") as mock_repo_cls:
            mock_repo = MagicMock()
            mock_repo.register_device_token = AsyncMock(return_value=mock_token_record)
            mock_repo_cls.return_value = mock_repo

            # Mock employee resolution query
            mock_emp_res = MagicMock()
            mock_emp_res.scalar_one_or_none.return_value = None
            mock_session.execute = AsyncMock(return_value=mock_emp_res)

            app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
            app.dependency_overrides[get_db] = lambda: mock_session

            try:
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.post(
                        "/api/v1/notifications/devices",
                        json={
                            "platform": "ANDROID",
                            "token": raw_fcm_token,
                            "device_model": "Pixel 8",
                            "os_version": "Android 14",
                            "app_version": "1.0.0",
                        },
                    )

                    assert resp.status_code == 201
                    data = resp.json()
                    assert data["platform"] == "ANDROID"
                    assert data["device_model"] == "Pixel 8"
                    # Invariant: raw token is NEVER returned
                    assert raw_fcm_token not in json.dumps(data)
                    assert "token_preview" in data
                    assert data["token_preview"] == mask_token_for_display(thash)
            finally:
                app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_list_user_device_tokens(self):
        uid = uuid.uuid4()
        tid = uuid.uuid4()
        auth_ctx = self._make_auth_context(uid, tid)

        token1 = DevicePushToken(
            id=uuid.uuid4(),
            tenant_id=tid,
            user_id=uid,
            platform="IOS",
            token=encrypt_push_token("token_1"),
            token_hash=hash_push_token("token_1"),
            device_model="iPhone 15",
            status="ACTIVE",
            last_seen_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )

        mock_session = AsyncMock()

        with patch("services.api.notifications.routes.NotificationRepository") as mock_repo_cls:
            mock_repo = MagicMock()
            mock_repo.get_active_tokens_for_user = AsyncMock(return_value=[token1])
            mock_repo_cls.return_value = mock_repo

            app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
            app.dependency_overrides[get_db] = lambda: mock_session

            try:
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.get("/api/v1/notifications/devices")
                    assert resp.status_code == 200
                    items = resp.json()
                    assert len(items) == 1
                    assert items[0]["platform"] == "IOS"
                    assert items[0]["device_model"] == "iPhone 15"
                    assert "token" not in items[0]
            finally:
                app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_revoke_device_token_by_hash_not_found(self):
        uid = uuid.uuid4()
        tid = uuid.uuid4()
        auth_ctx = self._make_auth_context(uid, tid)

        mock_session = AsyncMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 0  # No rows updated
        mock_session.execute = AsyncMock(return_value=mock_cursor)

        app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx
        app.dependency_overrides[get_db] = lambda: mock_session

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.delete("/api/v1/notifications/devices/non_existent_hash_123")
                assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


# ==============================================================================
# 3. Celery Notification Dispatch Worker Tests
# ==============================================================================


class TestNotificationCeleryTasks:
    """Verifies Celery worker task execution, recovery of stuck PROCESSING records, and retry scheduling."""

    def test_dispatch_single_notification_task_success(self):
        nid = uuid.uuid4()
        tid = uuid.uuid4()

        mock_dispatcher_res = MagicMock()
        mock_dispatcher_res.status = NotificationStatus.SENT
        mock_dispatcher_res.model_dump.return_value = {
            "notification_id": str(nid),
            "status": "SENT",
            "provider_name": "fcm",
            "provider_message_id": "mock-fcm-123",
            "attempt_count": 1,
        }

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        with patch("services.workers.notification_tasks.AsyncSessionLocal") as mock_sessionmaker:
            mock_sessionmaker.return_value.__aenter__.return_value = mock_session
            with patch("services.workers.notification_tasks.set_tenant_context", AsyncMock()):
                with patch("services.workers.notification_tasks.NotificationDispatcher") as mock_disp_cls:
                    mock_disp = MagicMock()
                    mock_disp.dispatch = AsyncMock(return_value=mock_dispatcher_res)
                    mock_disp_cls.return_value = mock_disp

                    result = dispatch_single_notification_task(str(nid), str(tid))
                    assert result["status"] == "SENT"
                    assert result["provider_message_id"] == "mock-fcm-123"

    def test_dispatch_batch_notifications_task(self):
        tid = uuid.uuid4()

        mock_r1 = MagicMock(status=NotificationStatus.SENT)
        mock_r2 = MagicMock(status=NotificationStatus.RETRY_SCHEDULED)
        mock_r3 = MagicMock(status=NotificationStatus.FAILED)

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        with patch("services.workers.notification_tasks.AsyncSessionLocal") as mock_sessionmaker:
            mock_sessionmaker.return_value.__aenter__.return_value = mock_session
            with patch("services.workers.notification_tasks.set_tenant_context", AsyncMock()):
                with patch("services.workers.notification_tasks.NotificationDispatcher") as mock_disp_cls:
                    mock_disp = MagicMock()
                    mock_disp.dispatch_pending_batch = AsyncMock(return_value=[mock_r1, mock_r2, mock_r3])
                    mock_disp_cls.return_value = mock_disp

                    summary = dispatch_batch_notifications_task(str(tid), limit=25)
                    assert summary["processed"] == 3
                    assert summary["sent"] == 1
                    assert summary["retried"] == 1
                    assert summary["failed"] == 1

    def test_reconcile_stuck_processing_task(self):
        # Two stuck notifications: one can retry, one has reached max attempts
        n_retry = Notification(
            id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            status=NotificationStatus.PROCESSING.value,
            attempt_count=1,
            max_attempts=3,
            updated_at=datetime.now(UTC) - timedelta(minutes=30),
        )
        n_fail = Notification(
            id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            status=NotificationStatus.PROCESSING.value,
            attempt_count=2,
            max_attempts=3,
            updated_at=datetime.now(UTC) - timedelta(minutes=30),
        )

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_query_res = MagicMock()
        mock_query_res.scalars.return_value.all.return_value = [n_retry, n_fail]
        mock_session.execute = AsyncMock(return_value=mock_query_res)

        with patch("services.workers.notification_tasks.AsyncSessionLocal") as mock_sessionmaker:
            mock_sessionmaker.return_value.__aenter__.return_value = mock_session

            res = reconcile_stuck_processing_task(timeout_minutes=15)
            assert res["total_stuck_found"] == 2
            assert res["recovered_to_retry"] == 1
            assert res["marked_failed"] == 1

            assert n_retry.status == NotificationStatus.RETRY_SCHEDULED.value
            assert n_fail.status == NotificationStatus.FAILED.value
            assert "Recovered from stuck PROCESSING" in (n_retry.error_message or "")
            assert "Terminal failure" in (n_fail.error_message or "")

    def test_cleanup_revoked_tokens_task(self):
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 5
        mock_session.execute = AsyncMock(return_value=mock_cursor)

        with patch("services.workers.notification_tasks.AsyncSessionLocal") as mock_sessionmaker:
            mock_sessionmaker.return_value.__aenter__.return_value = mock_session

            res = cleanup_revoked_tokens_task(older_than_days=90)
            assert res["deleted_tokens"] == 5


# ==============================================================================
# 4. Token Cryptography & Security Tests
# ==============================================================================


class TestTokenAuthenticatedEncryption:
    """Verifies Fernet AEAD security, PBKDF2 key derivation, and zero plaintext fallback."""

    def test_fernet_roundtrip_with_derived_key(self):
        token = "fcm_device_token_sensitive_credential_999"
        encrypted = encrypt_push_token(token)
        assert encrypted.startswith("fernet:")
        assert token not in encrypted

        decrypted = decrypt_push_token(encrypted)
        assert decrypted == token

    def test_plaintext_fallback_is_strictly_rejected(self):
        # Attempting to decrypt a raw plaintext token without fernet: prefix must raise
        with pytest.raises(TokenEncryptionError) as exc_info:
            decrypt_push_token("raw_plaintext_fcm_token_without_encryption_header")
        assert "plaintext fallback is prohibited" in str(exc_info.value)

    def test_tampered_ciphertext_fails_mac_verification(self):
        token = "fcm_test_device_token_abc"
        encrypted = encrypt_push_token(token)
        # Flip a character in the ciphertext to simulate data tampering
        tampered = encrypted[:-5] + ("A" if encrypted[-5] != "A" else "B") + encrypted[-4:]

        with pytest.raises(TokenEncryptionError) as exc_info:
            decrypt_push_token(tampered)
        assert "Invalid or corrupt token authentication tag" in str(exc_info.value)

    def test_empty_token_encryption_rejected(self):
        with pytest.raises(TokenEncryptionError):
            encrypt_push_token("   ")

    def test_derive_key_from_short_secret_raises(self):
        with pytest.raises(EncryptionConfigError):
            derive_fernet_key_from_secret("short")

    def test_mask_token_display_format(self):
        assert mask_token_for_display("abcdefghijklmnop") == "abcd...mnop"
        assert mask_token_for_display("fernet:abcdefghijklmnop") == "abcd...mnop"
        assert mask_token_for_display("short") == "***"
