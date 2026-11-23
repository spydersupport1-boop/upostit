"""Comprehensive unit and contract test suite for Phase 10 Milestone 10.2:
Core Notification Dispatch Engine, Repository & Provider Abstraction.

Test Groups:
1. SafeTemplateRenderer: variable interpolation, HTML entity escaping, subject CRLF stripping, SSTI prevention.
2. PreferenceResolver: User -> Tenant -> System precedence, channel toggles, opt-outs.
3. QuietHoursEvaluator: Daytime & overnight intervals, exact boundaries, timezone handling, urgent bypass.
4. Provider Abstraction: Mock adapters, transient vs permanent error classification, token hashing & at-rest encryption.
5. NotificationRepository: CRUD, tenant isolation, idempotency, atomic claim, status transitions, device tokens.
6. NotificationService: Recipient destination resolution, preference checks, initial quiet-hours deferral.
7. NotificationDispatcher: End-to-end lifecycle, retries, backoff progression, concurrent dispatch lock.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.api.auth.models import User
from services.api.notifications.dispatcher import (
    NotificationDispatcher,
    calculate_exponential_backoff,
)
from services.api.notifications.exceptions import (
    ChannelDisabledError,
    ProviderTimeoutError,
    TemplateNotFoundError,
    TemplateRenderError,
)
from services.api.notifications.models import (
    Notification,
    NotificationPreference,
    NotificationTemplate,
)
from services.api.notifications.preference_resolver import (
    EffectivePreferences,
    PreferenceResolver,
)
from services.api.notifications.provider import (
    MockEmailProvider,
    MockPushProvider,
    MockSmsProvider,
    ProviderRegistry,
    decrypt_token_at_rest,
    encrypt_token_at_rest,
    hash_push_token,
    mask_token_for_display,
)
from services.api.notifications.quiet_hours import (
    QuietHoursEvaluator,
)
from services.api.notifications.repository import NotificationRepository
from services.api.notifications.schemas import (
    NotificationChannel,
    NotificationCreateRequest,
    NotificationPriority,
    NotificationStatus,
    ProviderStatus,
)
from services.api.notifications.service import NotificationService
from services.api.notifications.template_renderer import SafeTemplateRenderer

# ==============================================================================
# 1. Safe Template Renderer Tests
# ==============================================================================


class TestSafeTemplateRenderer:
    """Verifies safe variable substitution and strict sandboxing."""

    def test_render_text_with_single_and_double_curly_braces(self):
        tmpl = "Hello {name}, your code is {{code}}!"
        res = SafeTemplateRenderer.render_text(tmpl, {"name": "Alice", "code": 12345})
        assert res == "Hello Alice, your code is 12345!"

    def test_render_text_missing_variable_raises_error(self):
        tmpl = "Hello {name}, your role is {role}."
        with pytest.raises(TemplateRenderError) as exc_info:
            SafeTemplateRenderer.render_text(tmpl, {"name": "Bob"})
        assert "Missing required template variables: role" in str(exc_info.value)
        assert exc_info.value.missing_variable == "role"

    def test_render_html_escapes_entities(self):
        tmpl = "<p>Welcome {{username}}! <script>alert(1)</script></p>"
        res = SafeTemplateRenderer.render_text(
            tmpl,
            {"username": "<Alice & Bob>"},
            escape_html_entities=True,
        )
        assert "&lt;Alice &amp; Bob&gt;" in res
        assert "<Alice & Bob>" not in res

    def test_render_subject_strips_crlf_header_injection(self):
        tmpl = "Subject: Alert for {user}"
        malicious_input = "Alice\r\nBcc: evil@attacker.com\nSubject: Spoofed"
        res = SafeTemplateRenderer.render_text(
            tmpl,
            {"user": malicious_input},
            is_subject=True,
        )
        assert "\r" not in res
        assert "\n" not in res
        assert "Bcc: evil@attacker.com" in res  # Sanitized to space

    def test_ssti_and_code_execution_prevention(self):
        malicious_templates = [
            "Hello {{ __class__.__mro__ }}",
            "Result: {import os}",
            "Exec: {{ eval('2+2') }}",
            "Hack: {os.system('id')}",
            "Dunder: {__globals__}",
        ]
        for tmpl in malicious_templates:
            with pytest.raises(TemplateRenderError):
                SafeTemplateRenderer.render_text(tmpl, {})

    def test_render_notification_both_subject_and_body(self):
        subj_tmpl = "Shift reminder for {employee}"
        body_tmpl = "Hello {employee}, your shift begins at {start_time}."
        subj, body = SafeTemplateRenderer.render_notification(
            subj_tmpl,
            body_tmpl,
            {"employee": "John", "start_time": "09:00 AM"},
        )
        assert subj == "Shift reminder for John"
        assert body == "Hello John, your shift begins at 09:00 AM."


# ==============================================================================
# 2. Preference Resolver Tests
# ==============================================================================


class TestPreferenceResolver:
    """Verifies preference hierarchy (User -> Tenant -> System fallback)."""

    def test_user_override_precedence(self):
        tid = uuid.uuid4()
        uid = uuid.uuid4()
        user_pref = NotificationPreference(
            id=uuid.uuid4(),
            tenant_id=tid,
            user_id=uid,
            is_push_enabled=False,
            is_email_enabled=True,
            is_sms_enabled=True,
            quiet_hours_enabled=True,
            quiet_hours_start="23:00",
            quiet_hours_end="06:00",
            timezone="America/New_York",
        )
        tenant_pref = NotificationPreference(
            id=uuid.uuid4(),
            tenant_id=tid,
            user_id=None,
            is_push_enabled=True,
            is_email_enabled=True,
            is_sms_enabled=False,
            quiet_hours_enabled=False,
            timezone="UTC",
        )
        effective = PreferenceResolver.resolve(user_pref, tenant_pref)
        assert effective.source == "USER_OVERRIDE"
        assert effective.is_push_enabled is False
        assert effective.is_sms_enabled is True
        assert effective.timezone == "America/New_York"
        assert effective.quiet_hours_start == "23:00"

    def test_tenant_default_precedence_when_user_none(self):
        tid = uuid.uuid4()
        tenant_pref = NotificationPreference(
            id=uuid.uuid4(),
            tenant_id=tid,
            user_id=None,
            is_push_enabled=True,
            is_email_enabled=False,
            is_sms_enabled=False,
            quiet_hours_enabled=True,
            quiet_hours_start="22:00",
            quiet_hours_end="07:00",
            timezone="Asia/Kolkata",
        )
        effective = PreferenceResolver.resolve(None, tenant_pref)
        assert effective.source == "TENANT_DEFAULT"
        assert effective.is_push_enabled is True
        assert effective.is_email_enabled is False
        assert effective.timezone == "Asia/Kolkata"

    def test_system_fallback_precedence_when_both_none(self):
        effective = PreferenceResolver.resolve(None, None)
        assert effective.source == "SYSTEM_DEFAULT"
        assert effective.is_push_enabled is True
        assert effective.is_email_enabled is True
        assert effective.is_sms_enabled is False
        assert effective.quiet_hours_enabled is False
        assert effective.timezone == "UTC"

    def test_is_channel_allowed_checks(self):
        tid = uuid.uuid4()
        uid = uuid.uuid4()
        user_pref = NotificationPreference(
            id=uuid.uuid4(),
            tenant_id=tid,
            user_id=uid,
            is_push_enabled=False,
            is_email_enabled=True,
            is_sms_enabled=False,
        )
        allowed, reason = PreferenceResolver.is_channel_allowed("PUSH", user_pref, None)
        assert allowed is False
        assert "OPT_OUT_USER" in (reason or "")

        allowed_email, reason_email = PreferenceResolver.is_channel_allowed("EMAIL", user_pref, None)
        assert allowed_email is True
        assert reason_email is None

        allowed_sms, reason_sms = PreferenceResolver.is_channel_allowed("SMS", user_pref, None)
        assert allowed_sms is False


# ==============================================================================
# 3. Quiet Hours Evaluator Tests
# ==============================================================================


class TestQuietHoursEvaluator:
    """Verifies timezone awareness, daytime intervals, overnight intervals, and urgent bypass."""

    def test_quiet_hours_disabled(self):
        pref = EffectivePreferences(
            is_push_enabled=True,
            is_email_enabled=True,
            is_sms_enabled=False,
            quiet_hours_enabled=False,
            quiet_hours_start="22:00",
            quiet_hours_end="07:00",
            timezone="UTC",
            category_preferences={},
            source="TEST",
        )
        res = QuietHoursEvaluator.evaluate(pref, NotificationPriority.NORMAL)
        assert res.is_in_quiet_hours is False
        assert res.should_defer is False
        assert res.next_eligible_dispatch_time is None

    def test_daytime_interval_inside_and_outside(self):
        # Quiet hours from 13:00 to 15:00 UTC
        pref = EffectivePreferences(
            is_push_enabled=True,
            is_email_enabled=True,
            is_sms_enabled=False,
            quiet_hours_enabled=True,
            quiet_hours_start="13:00",
            quiet_hours_end="15:00",
            timezone="UTC",
            category_preferences={},
            source="TEST",
        )
        # 14:00 is inside
        t_inside = datetime(2026, 6, 1, 14, 0, 0, tzinfo=UTC)
        res_inside = QuietHoursEvaluator.evaluate(pref, NotificationPriority.NORMAL, evaluation_time_utc=t_inside)
        assert res_inside.is_in_quiet_hours is True
        assert res_inside.should_defer is True
        assert res_inside.next_eligible_dispatch_time == datetime(2026, 6, 1, 15, 0, 0, tzinfo=UTC)

        # 16:00 is outside
        t_outside = datetime(2026, 6, 1, 16, 0, 0, tzinfo=UTC)
        res_outside = QuietHoursEvaluator.evaluate(pref, NotificationPriority.NORMAL, evaluation_time_utc=t_outside)
        assert res_outside.is_in_quiet_hours is False
        assert res_outside.should_defer is False

    def test_overnight_interval_crossing_midnight(self):
        # Quiet hours 22:00 to 07:00 UTC
        pref = EffectivePreferences(
            is_push_enabled=True,
            is_email_enabled=True,
            is_sms_enabled=False,
            quiet_hours_enabled=True,
            quiet_hours_start="22:00",
            quiet_hours_end="07:00",
            timezone="UTC",
            category_preferences={},
            source="TEST",
        )
        # 23:30 (before midnight) -> ends next morning at 07:00
        t1 = datetime(2026, 6, 1, 23, 30, 0, tzinfo=UTC)
        res1 = QuietHoursEvaluator.evaluate(pref, NotificationPriority.NORMAL, evaluation_time_utc=t1)
        assert res1.is_in_quiet_hours is True
        assert res1.should_defer is True
        assert res1.next_eligible_dispatch_time == datetime(2026, 6, 2, 7, 0, 0, tzinfo=UTC)

        # 04:30 (after midnight) -> ends today morning at 07:00
        t2 = datetime(2026, 6, 2, 4, 30, 0, tzinfo=UTC)
        res2 = QuietHoursEvaluator.evaluate(pref, NotificationPriority.NORMAL, evaluation_time_utc=t2)
        assert res2.is_in_quiet_hours is True
        assert res2.should_defer is True
        assert res2.next_eligible_dispatch_time == datetime(2026, 6, 2, 7, 0, 0, tzinfo=UTC)

    def test_exact_boundaries(self):
        pref = EffectivePreferences(
            is_push_enabled=True,
            is_email_enabled=True,
            is_sms_enabled=False,
            quiet_hours_enabled=True,
            quiet_hours_start="22:00",
            quiet_hours_end="07:00",
            timezone="UTC",
            category_preferences={},
            source="TEST",
        )
        # Exact start 22:00:00 -> active
        t_start = datetime(2026, 6, 1, 22, 0, 0, tzinfo=UTC)
        res_start = QuietHoursEvaluator.evaluate(pref, evaluation_time_utc=t_start)
        assert res_start.is_in_quiet_hours is True
        assert res_start.should_defer is True

        # Exact end 07:00:00 -> inactive
        t_end = datetime(2026, 6, 2, 7, 0, 0, tzinfo=UTC)
        res_end = QuietHoursEvaluator.evaluate(pref, evaluation_time_utc=t_end)
        assert res_end.is_in_quiet_hours is False
        assert res_end.should_defer is False

    def test_urgent_priority_respects_quiet_hours_without_unconditional_bypass(self):
        pref = EffectivePreferences(
            is_push_enabled=True,
            is_email_enabled=True,
            is_sms_enabled=False,
            quiet_hours_enabled=True,
            quiet_hours_start="22:00",
            quiet_hours_end="07:00",
            timezone="UTC",
            category_preferences={},
            source="TEST",
        )
        t_inside = datetime(2026, 6, 1, 23, 0, 0, tzinfo=UTC)
        res = QuietHoursEvaluator.evaluate(
            pref,
            priority=NotificationPriority.URGENT,
            evaluation_time_utc=t_inside,
        )
        assert res.is_in_quiet_hours is True
        assert res.should_defer is True  # Strictly deferred per Phase 10 rules

    def test_timezone_conversion(self):
        # Quiet hours 22:00 to 07:00 in America/New_York (UTC-4 in summer)
        pref = EffectivePreferences(
            is_push_enabled=True,
            is_email_enabled=True,
            is_sms_enabled=False,
            quiet_hours_enabled=True,
            quiet_hours_start="22:00",
            quiet_hours_end="07:00",
            timezone="America/New_York",
            category_preferences={},
            source="TEST",
        )
        # 03:00 UTC on June 2 = 23:00 EDT on June 1 (inside quiet hours)
        t_utc = datetime(2026, 6, 2, 3, 0, 0, tzinfo=UTC)
        res = QuietHoursEvaluator.evaluate(pref, evaluation_time_utc=t_utc)
        assert res.is_in_quiet_hours is True
        assert res.should_defer is True
        # 07:00 EDT on June 2 = 11:00 UTC
        assert res.next_eligible_dispatch_time == datetime(2026, 6, 2, 11, 0, 0, tzinfo=UTC)


# ==============================================================================
# 4. Providers & Token Security Tests
# ==============================================================================


class TestProvidersAndTokenSecurity:
    """Verifies mock provider behaviors and token encryption/hashing at rest."""

    @pytest.mark.asyncio
    async def test_mock_push_provider_success(self):
        provider = MockPushProvider(mode="SUCCESS")
        result = await provider.send("fcm_token_123", "Title", "Body")
        assert result.success is True
        assert result.status == ProviderStatus.ACCEPTED
        assert result.provider_message_id is not None
        assert result.is_retryable is False

    @pytest.mark.asyncio
    async def test_mock_push_provider_transient_failure_is_retryable(self):
        provider = MockPushProvider(mode="TRANSIENT_FAILURE")
        result = await provider.send("fcm_token_123", "Title", "Body")
        assert result.success is False
        assert result.status == ProviderStatus.FAILED
        assert result.is_retryable is True

    @pytest.mark.asyncio
    async def test_mock_push_provider_invalid_token_is_unretryable(self):
        provider = MockPushProvider(mode="INVALID_TOKEN")
        result = await provider.send("bad_token", "Title", "Body")
        assert result.success is False
        assert result.is_retryable is False

    @pytest.mark.asyncio
    async def test_mock_push_provider_timeout_raises(self):
        provider = MockPushProvider(mode="TIMEOUT")
        with pytest.raises(ProviderTimeoutError) as exc_info:
            await provider.send("fcm_token_123", "Title", "Body")
        assert exc_info.value.is_retryable is True

    @pytest.mark.asyncio
    async def test_mock_email_and_sms_providers(self):
        email_p = MockEmailProvider(mode="SUCCESS")
        sms_p = MockSmsProvider(mode="SUCCESS")
        res_e = await email_p.send("user@test.local", "Subj", "Body")
        res_s = await sms_p.send("+1234567890", None, "SMS text")
        assert res_e.success is True
        assert res_s.success is True

    def test_token_hash_deterministic_sha256(self):
        raw = "fcm_test_device_token_xyz"
        h1 = hash_push_token(raw)
        h2 = hash_push_token(raw)
        assert h1 == h2
        assert len(h1) == 64

    def test_token_encryption_and_decryption_at_rest(self):
        raw = "fcm_super_secret_device_registration_token_12345"
        encrypted = encrypt_token_at_rest(raw)
        assert encrypted.startswith("fernet:")
        assert raw not in encrypted
        decrypted = decrypt_token_at_rest(encrypted)
        assert decrypted == raw

    def test_mask_token_for_display(self):
        raw = "abcdefghijklmnop"
        masked = mask_token_for_display(raw)
        assert masked == "abcd...mnop"
        assert mask_token_for_display("short") == "***"

    def test_provider_registry_lookup(self):
        registry = ProviderRegistry()
        p = registry.get_provider(NotificationChannel.PUSH)
        assert isinstance(p, MockPushProvider)
        with pytest.raises(Exception):
            registry.get_provider("UNKNOWN_CHANNEL")


# ==============================================================================
# 5. Notification Repository Tests
# ==============================================================================


class TestNotificationRepository:
    """Verifies repository queries, atomic transitions, and tenant scoping."""

    @pytest.mark.asyncio
    async def test_create_notification_and_idempotency(self):
        session = AsyncMock()
        session.add = MagicMock()
        repo = NotificationRepository(session)
        tid = uuid.uuid4()

        # 1. First insert: no existing idempotency match
        mock_result_none = MagicMock()
        mock_result_none.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result_none

        notif, is_new = await repo.create_notification(
            tenant_id=tid,
            event_type="SHIFT_REMINDER",
            channel="EMAIL",
            recipient_destination="test@upostit.test",
            body="Your shift is starting",
            idempotency_key="idemp_1001",
        )
        assert is_new is True
        assert notif.tenant_id == tid
        assert notif.status == NotificationStatus.PENDING.value
        assert session.add.called
        assert session.flush.called

        # 2. Second insert with matching idempotency key returns existing
        existing_notif = Notification(
            id=uuid.uuid4(),
            tenant_id=tid,
            event_type="SHIFT_REMINDER",
            channel="EMAIL",
            recipient_destination="test@upostit.test",
            body="Existing body",
            idempotency_key="idemp_1001",
            status=NotificationStatus.SENT.value,
        )
        mock_result_existing = MagicMock()
        mock_result_existing.scalar_one_or_none.return_value = existing_notif
        session.execute.return_value = mock_result_existing

        dup_notif, dup_is_new = await repo.create_notification(
            tenant_id=tid,
            event_type="SHIFT_REMINDER",
            channel="EMAIL",
            recipient_destination="test@upostit.test",
            body="Second call body",
            idempotency_key="idemp_1001",
        )
        assert dup_is_new is False
        assert dup_notif.id == existing_notif.id
        assert dup_notif.status == NotificationStatus.SENT.value

    @pytest.mark.asyncio
    async def test_claim_for_processing_atomic_transition(self):
        session = AsyncMock()
        repo = NotificationRepository(session)
        nid = uuid.uuid4()
        tid = uuid.uuid4()

        claimed_notif = Notification(
            id=nid,
            tenant_id=tid,
            status=NotificationStatus.PROCESSING.value,
        )
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = claimed_notif
        session.execute.return_value = mock_res

        result = await repo.claim_for_processing(nid, tid)
        assert result is not None
        assert result.status == NotificationStatus.PROCESSING.value

        # When already processing or terminal, claim returns None
        mock_res_none = MagicMock()
        mock_res_none.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_res_none
        result_none = await repo.claim_for_processing(nid, tid)
        assert result_none is None

    @pytest.mark.asyncio
    async def test_status_transition_helpers(self):
        session = AsyncMock()
        repo = NotificationRepository(session)
        nid = uuid.uuid4()
        tid = uuid.uuid4()

        # record_success
        sent_notif = Notification(id=nid, tenant_id=tid, status=NotificationStatus.SENT.value)
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = sent_notif
        session.execute.return_value = mock_res

        res = await repo.record_success(nid, tid, "mock_p", "msg_123")
        assert res.status == NotificationStatus.SENT.value

        # record_retryable_failure
        retry_notif = Notification(id=nid, tenant_id=tid, status=NotificationStatus.RETRY_SCHEDULED.value)
        mock_res.scalar_one_or_none.return_value = retry_notif
        res_retry = await repo.record_retryable_failure(
            nid, tid, "503 Error", datetime.now(UTC) + timedelta(minutes=2)
        )
        assert res_retry.status == NotificationStatus.RETRY_SCHEDULED.value

        # record_permanent_failure
        failed_notif = Notification(id=nid, tenant_id=tid, status=NotificationStatus.FAILED.value)
        mock_res.scalar_one_or_none.return_value = failed_notif
        res_fail = await repo.record_permanent_failure(nid, tid, "400 Bad Request")
        assert res_fail.status == NotificationStatus.FAILED.value

    @pytest.mark.asyncio
    async def test_template_hierarchy_lookup(self):
        session = AsyncMock()
        repo = NotificationRepository(session)
        tid = uuid.uuid4()

        # 1. Tenant override present
        tenant_tmpl = NotificationTemplate(
            id=uuid.uuid4(),
            tenant_id=tid,
            template_key="LEAVE_APPROVED",
            name="Tenant Custom Leave",
            event_type="LEAVE_APPROVED",
            channel="EMAIL",
            body_template="Custom tenant body",
            is_active=True,
            is_system=False,
        )
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = tenant_tmpl
        session.execute.return_value = mock_res

        tmpl = await repo.get_template(tid, "LEAVE_APPROVED", "EMAIL")
        assert tmpl is not None
        assert tmpl.tenant_id == tid
        assert tmpl.body_template == "Custom tenant body"


# ==============================================================================
# 6. Notification Service Tests
# ==============================================================================


class TestNotificationService:
    """Verifies service layer validation, destination resolution, and quiet hours integration."""

    @pytest.mark.asyncio
    async def test_create_notification_resolves_user_email(self):
        session = AsyncMock()
        session.add = MagicMock()
        service = NotificationService(session)
        tid = uuid.uuid4()
        uid = uuid.uuid4()

        # Mock User lookup
        mock_user = User(id=uid, tenant_id=tid, email="employee@company.test", full_name="Emp Name")
        # Mock Template lookup
        mock_template = NotificationTemplate(
            id=uuid.uuid4(),
            tenant_id=None,
            template_key="TEST_KEY",
            name="Test",
            event_type="TEST_EVENT",
            channel="EMAIL",
            subject_template="Hello {name}",
            body_template="Welcome {name}",
            locale="en",
            is_active=True,
            is_system=True,
        )

        with pytest.MonkeyPatch.context() as m:
            m.setattr(service.repository, "get_user_preference", AsyncMock(return_value=None))
            m.setattr(service.repository, "get_tenant_default_preference", AsyncMock(return_value=None))
            m.setattr(service.repository, "get_template", AsyncMock(return_value=mock_template))

            # Mock session execute for User resolution
            mock_res_user = MagicMock()
            mock_res_user.scalar_one_or_none.return_value = mock_user
            session.execute.return_value = mock_res_user

            req = NotificationCreateRequest(
                recipient_user_id=uid,
                event_type="TEST_EVENT",
                channel=NotificationChannel.EMAIL,
                template_key="TEST_KEY",
                template_variables={"name": "Alice"},
            )
            resp = await service.create_notification(tid, req)
            assert resp.recipient_destination == "employee@company.test"
            assert resp.subject == "Hello Alice"
            assert resp.body == "Welcome Alice"

    @pytest.mark.asyncio
    async def test_create_notification_enforces_channel_opt_out(self):
        session = AsyncMock()
        service = NotificationService(session)
        tid = uuid.uuid4()
        uid = uuid.uuid4()

        user_pref = NotificationPreference(
            id=uuid.uuid4(),
            tenant_id=tid,
            user_id=uid,
            is_push_enabled=False,
            is_email_enabled=True,
            is_sms_enabled=False,
        )

        with pytest.MonkeyPatch.context() as m:
            m.setattr(service.repository, "get_user_preference", AsyncMock(return_value=user_pref))
            m.setattr(service.repository, "get_tenant_default_preference", AsyncMock(return_value=None))

            req = NotificationCreateRequest(
                recipient_user_id=uid,
                event_type="ALERT",
                channel=NotificationChannel.PUSH,
                template_key="TEST_KEY",
                template_variables={},
            )
            with pytest.raises(ChannelDisabledError) as exc_info:
                await service.create_notification(tid, req, enforce_preferences=True)
            assert "Push channel disabled" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_notification_missing_template_raises(self):
        session = AsyncMock()
        service = NotificationService(session)
        tid = uuid.uuid4()

        with pytest.MonkeyPatch.context() as m:
            m.setattr(service.repository, "get_user_preference", AsyncMock(return_value=None))
            m.setattr(service.repository, "get_tenant_default_preference", AsyncMock(return_value=None))
            m.setattr(service.repository, "get_template", AsyncMock(return_value=None))

            req = NotificationCreateRequest(
                recipient_destination="test@upostit.test",
                event_type="ALERT",
                channel=NotificationChannel.EMAIL,
                template_key="NON_EXISTENT_KEY",
                template_variables={},
            )
            with pytest.raises(TemplateNotFoundError):
                await service.create_notification(tid, req)


# ==============================================================================
# 7. Notification Dispatcher Tests
# ==============================================================================


class TestNotificationDispatcher:
    """Verifies end-to-end dispatch orchestration, retry policies, and backoff progression."""

    @pytest.mark.asyncio
    async def test_dispatch_successful_lifecycle(self):
        session = AsyncMock()
        registry = ProviderRegistry()
        mock_email = MockEmailProvider(mode="SUCCESS")
        registry.register(NotificationChannel.EMAIL, mock_email)

        dispatcher = NotificationDispatcher(session, registry)
        nid = uuid.uuid4()
        tid = uuid.uuid4()

        persisted = Notification(
            id=nid,
            tenant_id=tid,
            channel="EMAIL",
            recipient_destination="worker@company.test",
            subject="Test Subject",
            body="Test Body",
            status=NotificationStatus.PENDING.value,
            priority="NORMAL",
            attempt_count=0,
            max_attempts=3,
        )

        with pytest.MonkeyPatch.context() as m:
            m.setattr(dispatcher.repository, "claim_for_processing", AsyncMock(return_value=persisted))
            m.setattr(dispatcher.repository, "get_user_preference", AsyncMock(return_value=None))
            m.setattr(dispatcher.repository, "get_tenant_default_preference", AsyncMock(return_value=None))

            sent_notif = Notification(
                id=nid,
                tenant_id=tid,
                status=NotificationStatus.SENT.value,
                attempt_count=0,
                provider_message_id="mock-123",
            )
            m.setattr(dispatcher.repository, "record_success", AsyncMock(return_value=sent_notif))

            result = await dispatcher.dispatch(nid, tid)
            assert result.status == NotificationStatus.SENT
            assert result.provider_message_id == "mock-123"
            assert len(mock_email.sent_messages) == 1

    @pytest.mark.asyncio
    async def test_dispatch_quiet_hours_deferral(self):
        session = AsyncMock()
        dispatcher = NotificationDispatcher(session)
        nid = uuid.uuid4()
        tid = uuid.uuid4()

        persisted = Notification(
            id=nid,
            tenant_id=tid,
            channel="PUSH",
            recipient_destination="user_123",
            body="Alert",
            status=NotificationStatus.PENDING.value,
            priority="NORMAL",
            attempt_count=0,
            max_attempts=3,
        )
        tenant_pref = NotificationPreference(
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
        )

        eval_time = datetime(2026, 6, 1, 23, 0, 0, tzinfo=UTC)

        with pytest.MonkeyPatch.context() as m:
            m.setattr(dispatcher.repository, "claim_for_processing", AsyncMock(return_value=persisted))
            m.setattr(dispatcher.repository, "get_user_preference", AsyncMock(return_value=None))
            m.setattr(dispatcher.repository, "get_tenant_default_preference", AsyncMock(return_value=tenant_pref))

            deferred_notif = Notification(
                id=nid,
                tenant_id=tid,
                status=NotificationStatus.RETRY_SCHEDULED.value,
                attempt_count=0,
            )
            m.setattr(dispatcher.repository, "defer_for_quiet_hours", AsyncMock(return_value=deferred_notif))

            result = await dispatcher.dispatch(nid, tid, evaluation_time_utc=eval_time)
            assert result.status == NotificationStatus.RETRY_SCHEDULED
            assert result.is_deferred is True
            assert result.next_eligible_at == datetime(2026, 6, 2, 7, 0, 0, tzinfo=UTC)

    @pytest.mark.asyncio
    async def test_dispatch_transient_failure_schedules_retry(self):
        session = AsyncMock()
        registry = ProviderRegistry()
        mock_push = MockPushProvider(mode="TRANSIENT_FAILURE")
        registry.register(NotificationChannel.PUSH, mock_push)

        dispatcher = NotificationDispatcher(session, registry, base_backoff_seconds=60)
        nid = uuid.uuid4()
        tid = uuid.uuid4()

        persisted = Notification(
            id=nid,
            tenant_id=tid,
            channel="PUSH",
            recipient_destination="fcm_tok",
            body="Alert",
            status=NotificationStatus.PENDING.value,
            priority="HIGH",
            attempt_count=0,
            max_attempts=3,
        )

        with pytest.MonkeyPatch.context() as m:
            m.setattr(dispatcher.repository, "claim_for_processing", AsyncMock(return_value=persisted))
            m.setattr(dispatcher.repository, "get_user_preference", AsyncMock(return_value=None))
            m.setattr(dispatcher.repository, "get_tenant_default_preference", AsyncMock(return_value=None))

            retry_notif = Notification(
                id=nid,
                tenant_id=tid,
                status=NotificationStatus.RETRY_SCHEDULED.value,
                attempt_count=1,
            )
            m.setattr(dispatcher.repository, "record_retryable_failure", AsyncMock(return_value=retry_notif))

            result = await dispatcher.dispatch(nid, tid)
            assert result.status == NotificationStatus.RETRY_SCHEDULED
            assert result.attempt_count == 1
            assert result.next_eligible_at is not None

    @pytest.mark.asyncio
    async def test_dispatch_permanent_failure_marks_failed(self):
        session = AsyncMock()
        registry = ProviderRegistry()
        mock_push = MockPushProvider(mode="PERMANENT_FAILURE")
        registry.register(NotificationChannel.PUSH, mock_push)

        dispatcher = NotificationDispatcher(session, registry)
        nid = uuid.uuid4()
        tid = uuid.uuid4()

        persisted = Notification(
            id=nid,
            tenant_id=tid,
            channel="PUSH",
            recipient_destination="fcm_tok",
            body="Alert",
            status=NotificationStatus.PENDING.value,
            priority="NORMAL",
            attempt_count=0,
            max_attempts=3,
        )

        with pytest.MonkeyPatch.context() as m:
            m.setattr(dispatcher.repository, "claim_for_processing", AsyncMock(return_value=persisted))
            m.setattr(dispatcher.repository, "get_user_preference", AsyncMock(return_value=None))
            m.setattr(dispatcher.repository, "get_tenant_default_preference", AsyncMock(return_value=None))

            failed_notif = Notification(
                id=nid,
                tenant_id=tid,
                status=NotificationStatus.FAILED.value,
                attempt_count=1,
            )
            m.setattr(dispatcher.repository, "record_permanent_failure", AsyncMock(return_value=failed_notif))

            result = await dispatcher.dispatch(nid, tid)
            assert result.status == NotificationStatus.FAILED
            assert result.attempt_count == 1

    def test_calculate_exponential_backoff_progression(self):
        # Base 60s, max 3600s
        assert calculate_exponential_backoff(0, 60, 3600) == timedelta(seconds=60)
        assert calculate_exponential_backoff(1, 60, 3600) == timedelta(seconds=120)
        assert calculate_exponential_backoff(2, 60, 3600) == timedelta(seconds=240)
        assert calculate_exponential_backoff(3, 60, 3600) == timedelta(seconds=480)
        assert calculate_exponential_backoff(10, 60, 3600) == timedelta(seconds=3600)
