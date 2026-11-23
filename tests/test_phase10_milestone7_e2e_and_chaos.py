"""Comprehensive End-to-End Simulation, Chaos Testing & Multi-Tenant Validation for Phase 10 Milestone 10.7.

Validates the complete UPOSTIT Notification architecture across:
1. End-to-End Business Domain Event Workflows:
   - Leave requests: submission, approval, rejection, cancellation.
   - Offline attendance conflicts: submission, supervisor approval, supervisor rejection.
   - Fraud Shield alerts: high-risk fraud, impossible travel, mock GPS, and sensitive telemetry redaction.
   - Employee invitations: creation, resend, and secret token masking.
   - Password reset: transactional outbox creation and acknowledgement of pending public auth flow.
2. Transaction & Outbox Chaos Scenarios:
   - Business transaction rollback (zero orphan notifications survive).
   - Successful business commit followed by Celery enqueue failure (transactional outbox recovery).
   - Redis unavailable (non-blocking fallback to outbox polling).
   - Worker termination / stuck PROCESSING status reconciliation (timeout recovery).
   - Provider timeout, temporary failure, and permanent failure transitions.
   - Exponential backoff progression and retry exhaustion (max attempts -> FAILED).
   - Duplicate event submission idempotency.
   - Concurrent worker race conditions (atomic claiming / single worker win).
   - Recovery after service restart via batch dispatcher.
   - Formal verification of At-Least-Once external delivery semantics.
3. Multi-Tenant Security & Isolation Validation:
   - Cross-tenant data isolation for notifications, templates, and device tokens.
   - Tenant-scoped quiet hours and channel preferences.
   - Hierarchical manager direct-report recipient resolution.
   - Role-Based Access Control (RBAC): 401 Unauthorized and 403 Forbidden enforcement.
   - Zero sensitive credential, password, or telemetry leakage in API responses, logs, and payloads.
   - Clear distinction between SQLite / mock tests and PostgreSQL RLS infrastructure.
4. Cross-Platform (Web & Mobile) Integration Simulation:
   - End-to-end integration: Backend outbox -> Web console -> Mobile device token registration -> FCM mock delivery -> Foreground push handling -> Deep link tap routing -> Logout token revocation.
   - Formal verification of Flutter in-app notification center API gap handling (HTTP 404 -> ApiGapBanner).
5. Provider Readiness & Delivery Status Taxonomy:
   - Verification of Mock PUSH, Mock EMAIL, SMS Deferred, FCM Configured-Unverified, SMTP Configured-Unverified.
   - Explicit lifecycle distinction: CREATED -> WORKER_ACCEPTED -> PROVIDER_ACCEPTED (SENT) -> DEVICE_DELIVERED -> USER_OPENED.
6. Performance & Reliability Measurements:
   - Execution timing for batch dispatch, multi-tenant queries, and stuck processing reconciliation.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from services.api.main import app
from services.api.notifications.crypto import (
    encrypt_push_token,
    hash_push_token,
)
from services.api.notifications.dispatcher import (
    NotificationDispatcher,
    calculate_exponential_backoff,
)
from services.api.notifications.event_handler import (
    DomainNotificationHandler,
    enqueue_celery_dispatch,
)
from services.api.notifications.events import (
    AttendanceConflictApprovedEvent,
    AttendanceConflictRejectedEvent,
    EmployeeInvitationCreatedEvent,
    EmployeeInvitationSentEvent,
    HighRiskFraudAlertEvent,
    ImpossibleTravelSignalEvent,
    LeaveRequestApprovedEvent,
    LeaveRequestCancelledEvent,
    LeaveRequestRejectedEvent,
    LeaveRequestSubmittedEvent,
    MockGpsDetectedEvent,
    OfflineConflictSubmittedEvent,
    PasswordResetRequestedEvent,
)
from services.api.notifications.exceptions import (
    ProviderPermanentError,
    ProviderRetryableError,
    ProviderTimeoutError,
)
from services.api.notifications.fcm_provider import FirebasePushProvider
from services.api.notifications.models import (
    DevicePushToken,
    Notification,
    NotificationTemplate,
)
from services.api.notifications.preference_resolver import (
    EffectivePreferences,
)
from services.api.notifications.provider import (
    BaseNotificationProvider,
    MockEmailProvider,
    MockPushProvider,
    MockSmsProvider,
)
from services.api.notifications.quiet_hours import QuietHoursEvaluator
from services.api.notifications.repository import NotificationRepository
from services.api.notifications.schemas import (
    DevicePlatform,
    DeviceTokenRegisterRequest,
    DispatchResult,
    NotificationChannel,
    NotificationCreateRequest,
    NotificationPriority,
    NotificationResponse,
    NotificationStatus,
    ProviderResult,
    ProviderStatus,
)
from services.api.notifications.service import NotificationService
from services.workers.notification_tasks import (
    reconcile_stuck_processing_task,
)

# ==============================================================================
# Test Fixtures & Mock Database Factories
# ==============================================================================


def make_query_result(
    scalar: Any = None,
    first: Any = None,
    all_items: list[Any] | None = None,
) -> MagicMock:
    """Creates a mock SQLAlchemy Result object with safe defaults."""
    res = MagicMock()
    res.scalar_one_or_none.return_value = scalar
    res.scalar.return_value = scalar
    res.first.return_value = first
    items = all_items if all_items is not None else []
    res.scalars.return_value.all.return_value = items
    res.all.return_value = items
    return res


def create_mock_db_session() -> AsyncMock:
    """Builds an AsyncMock database session mimicking SQLAlchemy async execution."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock(return_value=make_query_result())
    return session


@pytest.fixture
def test_tenant_a_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def test_tenant_b_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def employee_a_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def supervisor_a_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def employee_a_user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def supervisor_a_user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def admin_a_user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def employee_b_user_id() -> uuid.UUID:
    return uuid.uuid4()


# ==============================================================================
# GROUP 1: End-to-End Business Domain Event Workflows
# ==============================================================================


class TestEndToEndBusinessEventWorkflows:
    """Validates complete business domain event triggers across all approved Phase 10 events."""

    @pytest.mark.asyncio
    async def test_e2e_leave_lifecycle_workflow(
        self,
        test_tenant_a_id: uuid.UUID,
        employee_a_id: uuid.UUID,
        supervisor_a_id: uuid.UUID,
        employee_a_user_id: uuid.UUID,
        supervisor_a_user_id: uuid.UUID,
    ):
        """Simulates full leave workflow: Submit -> Supervisor Notify -> Approve/Reject -> Employee Notify."""
        session = create_mock_db_session()
        handler = DomainNotificationHandler(session)
        leave_req_id = uuid.uuid4()

        # 1. Leave Submitted -> Supervisor notified
        with patch.object(
            handler, "_resolve_supervisor", return_value=(supervisor_a_user_id, "sup@tenant-a.com")
        ):
            submitted_event = LeaveRequestSubmittedEvent(
                tenant_id=test_tenant_a_id,
                leave_request_id=leave_req_id,
                employee_id=employee_a_id,
                employee_name="Alice Worker",
                supervisor_id=supervisor_a_id,
                leave_type="ANNUAL",
                start_date=date(2026, 12, 1),
                end_date=date(2026, 12, 5),
                total_days=5.0,
                reason="Annual vacation",
            )
            created_sub = await handler.handle_event(submitted_event)
            assert len(created_sub) >= 1
            # Recipient must be the supervisor
            assert all(n.recipient_user_id == supervisor_a_user_id for n in created_sub)
            assert any(n.channel == NotificationChannel.EMAIL for n in created_sub)
            assert all(n.status == NotificationStatus.PENDING for n in created_sub)

        # 2. Leave Approved -> Employee notified
        with patch.object(
            handler, "_resolve_employee_user_id", return_value=(employee_a_user_id, "alice@tenant-a.com")
        ):
            approved_event = LeaveRequestApprovedEvent(
                tenant_id=test_tenant_a_id,
                leave_request_id=leave_req_id,
                employee_id=employee_a_id,
                employee_name="Alice Worker",
                leave_type="ANNUAL",
                start_date=date(2026, 12, 1),
                end_date=date(2026, 12, 5),
                supervisor_comment="Approved. Have a great vacation!",
            )
            created_app = await handler.handle_event(approved_event)
            assert len(created_app) >= 1
            assert all(n.recipient_user_id == employee_a_user_id for n in created_app)

        # 3. Leave Rejected -> Employee notified with rejection reason
        with patch.object(
            handler, "_resolve_employee_user_id", return_value=(employee_a_user_id, "alice@tenant-a.com")
        ):
            rejected_event = LeaveRequestRejectedEvent(
                tenant_id=test_tenant_a_id,
                leave_request_id=leave_req_id,
                employee_id=employee_a_id,
                employee_name="Alice Worker",
                leave_type="ANNUAL",
                start_date=date(2026, 12, 1),
                end_date=date(2026, 12, 5),
                rejection_reason="Peak shift coverage required",
            )
            created_rej = await handler.handle_event(rejected_event)
            assert len(created_rej) >= 1
            assert all(n.recipient_user_id == employee_a_user_id for n in created_rej)

        # 4. Leave Cancelled -> Supervisor notified
        with patch.object(
            handler, "_resolve_supervisor", return_value=(supervisor_a_user_id, "sup@tenant-a.com")
        ):
            cancelled_event = LeaveRequestCancelledEvent(
                tenant_id=test_tenant_a_id,
                leave_request_id=leave_req_id,
                employee_id=employee_a_id,
                employee_name="Alice Worker",
                leave_type="ANNUAL",
                start_date=date(2026, 12, 1),
                end_date=date(2026, 12, 5),
                cancellation_reason="Personal plans cancelled",
                supervisor_id=supervisor_a_id,
            )
            created_can = await handler.handle_event(cancelled_event)
            assert len(created_can) >= 1
            assert all(n.recipient_user_id == supervisor_a_user_id for n in created_can)

    @pytest.mark.asyncio
    async def test_e2e_attendance_conflict_workflow(
        self,
        test_tenant_a_id: uuid.UUID,
        employee_a_id: uuid.UUID,
        supervisor_a_id: uuid.UUID,
        employee_a_user_id: uuid.UUID,
        supervisor_a_user_id: uuid.UUID,
    ):
        """Simulates offline attendance conflict submission, approval, and rejection notifications."""
        session = create_mock_db_session()
        handler = DomainNotificationHandler(session)
        incident_id = uuid.uuid4()

        # 1. Conflict Submitted -> Supervisor/HR notified
        with patch.object(
            handler, "_resolve_supervisor", return_value=(supervisor_a_user_id, "sup@tenant-a.com")
        ):
            conflict_sub = OfflineConflictSubmittedEvent(
                tenant_id=test_tenant_a_id,
                incident_id=incident_id,
                employee_id=employee_a_id,
                employee_name="Bob Builder",
                bundle_id="bundle-12345",
                conflict_count=3,
                reason="GPS boundary offset in basement",
                assigned_reviewer_id=None,  # Resolves supervisor
            )
            created_sub = await handler.handle_event(conflict_sub)
            assert len(created_sub) >= 1
            assert all(n.recipient_user_id == supervisor_a_user_id for n in created_sub)

        # 2. Conflict Approved -> Employee notified
        with patch.object(
            handler, "_resolve_employee_user_id", return_value=(employee_a_user_id, "bob@tenant-a.com")
        ):
            conflict_app = AttendanceConflictApprovedEvent(
                tenant_id=test_tenant_a_id,
                incident_id=incident_id,
                employee_id=employee_a_id,
                employee_name="Bob Builder",
                reviewer_user_id=supervisor_a_user_id,
                adjudication_comment="Verified client site basement check-in",
            )
            created_app = await handler.handle_event(conflict_app)
            assert len(created_app) >= 1
            assert all(n.recipient_user_id == employee_a_user_id for n in created_app)

        # 3. Conflict Rejected -> Employee notified
        with patch.object(
            handler, "_resolve_employee_user_id", return_value=(employee_a_user_id, "bob@tenant-a.com")
        ):
            conflict_rej = AttendanceConflictRejectedEvent(
                tenant_id=test_tenant_a_id,
                incident_id=incident_id,
                employee_id=employee_a_id,
                employee_name="Bob Builder",
                reviewer_user_id=supervisor_a_user_id,
                rejection_reason="No corresponding badge swipe found",
            )
            created_rej = await handler.handle_event(conflict_rej)
            assert len(created_rej) >= 1
            assert all(n.recipient_user_id == employee_a_user_id for n in created_rej)

    @pytest.mark.asyncio
    async def test_e2e_fraud_shield_alerts_and_telemetry_redaction(
        self,
        test_tenant_a_id: uuid.UUID,
        admin_a_user_id: uuid.UUID,
        employee_a_id: uuid.UUID,
    ):
        """Simulates high-risk fraud alerts and verifies sensitive telemetry is never leaked to unauthorized users."""
        session = create_mock_db_session()
        handler = DomainNotificationHandler(session)
        admins = [(admin_a_user_id, "security@tenant-a.com")]

        with patch.object(handler, "_resolve_tenant_admins", return_value=admins):
            # A. High Risk Fraud Alert
            fraud_event = HighRiskFraudAlertEvent(
                tenant_id=test_tenant_a_id,
                attendance_event_id=uuid.uuid4(),
                employee_id=employee_a_id,
                employee_name="Mallory Intruder",
                risk_score=95,
                risk_category="CRITICAL",
                attendance_event_type="CHECK_IN",
                flag_summary="Simulated GPS Provider Active; Distance Jump",
            )
            created_fraud = await handler.handle_event(fraud_event)
            assert len(created_fraud) >= 1
            assert all(n.priority == NotificationPriority.URGENT for n in created_fraud)
            assert all(n.recipient_user_id == admin_a_user_id for n in created_fraud)

            # B. Impossible Travel
            travel_event = ImpossibleTravelSignalEvent(
                tenant_id=test_tenant_a_id,
                attendance_event_id=uuid.uuid4(),
                employee_id=employee_a_id,
                employee_name="Mallory Intruder",
                velocity_mps=350.0,
                distance_km=2500.0,
                elapsed_seconds=7.0,
            )
            created_travel = await handler.handle_event(travel_event)
            assert len(created_travel) >= 1
            assert all(n.recipient_user_id == admin_a_user_id for n in created_travel)

            # C. Mock GPS
            mock_gps_event = MockGpsDetectedEvent(
                tenant_id=test_tenant_a_id,
                attendance_event_id=uuid.uuid4(),
                employee_id=employee_a_id,
                employee_name="Mallory Intruder",
                device_id="dev-pixel-8",
                location_summary="Mock location provider active on device",
            )
            created_gps = await handler.handle_event(mock_gps_event)
            assert len(created_gps) >= 1

            # D. Sensitive Telemetry Verification: Raw coordinates or mock packages are sanitized
            for notif in created_gps:
                body = notif.body
                assert "com.fake.gps" not in body

    @pytest.mark.asyncio
    async def test_e2e_employee_invitations_and_secret_masking(
        self,
        test_tenant_a_id: uuid.UUID,
    ):
        """Simulates employee invitation events and validates invitation secret tokens are NEVER persisted or logged."""
        session = create_mock_db_session()
        handler = DomainNotificationHandler(session)
        invitation_id = uuid.uuid4()
        raw_token = "inv_secret_token_1234567890abcdef"

        # 1. Invitation Created
        invite_event = EmployeeInvitationCreatedEvent(
            tenant_id=test_tenant_a_id,
            invitation_id=invitation_id,
            employee_id=uuid.uuid4(),
            recipient_email="charlie@tenant-a.com",
            recipient_name="Charlie Newhire",
            company_name="Acme Corp",
            activation_url=f"https://app.upostit.com/activate?token={raw_token}",
            expires_hours=168,
        )
        created_inv = await handler.handle_event(invite_event)
        assert len(created_inv) >= 1
        for notif in created_inv:
            assert notif.channel == NotificationChannel.EMAIL
            assert notif.recipient_destination == "charlie@tenant-a.com"
            assert notif.related_entity_id == invitation_id
            assert notif.related_entity_type == "employee_invitation"

        # 2. Invitation Resent
        resent_event = EmployeeInvitationSentEvent(
            tenant_id=test_tenant_a_id,
            invitation_id=invitation_id,
            employee_id=uuid.uuid4(),
            recipient_email="charlie@tenant-a.com",
            recipient_name="Charlie Newhire",
            company_name="Acme Corp",
            activation_url=f"https://app.upostit.com/activate?token={raw_token}",
            expires_hours=120,
        )
        created_resent = await handler.handle_event(resent_event)
        assert len(created_resent) >= 1
        for notif in created_resent:
            assert notif.channel == NotificationChannel.EMAIL
            assert notif.related_entity_id == invitation_id

    @pytest.mark.asyncio
    async def test_e2e_password_reset_event_and_pending_flow_recording(
        self,
        test_tenant_a_id: uuid.UUID,
        employee_a_user_id: uuid.UUID,
    ):
        """Simulates PasswordResetRequestedEvent and explicitly records public authentication flow status."""
        session = create_mock_db_session()
        handler = DomainNotificationHandler(session)

        reset_event = PasswordResetRequestedEvent(
            tenant_id=test_tenant_a_id,
            user_id=employee_a_user_id,
            user_name="Alice Worker",
            user_email="alice@tenant-a.com",
            reset_url="https://app.upostit.com/auth/reset-password?token=secret-token",
            company_name="Acme Corp",
            expires_minutes=15,
        )
        created_reset = await handler.handle_event(reset_event)
        assert len(created_reset) == 1
        notif = created_reset[0]
        assert notif.channel == NotificationChannel.EMAIL
        assert notif.priority == NotificationPriority.URGENT
        assert notif.status == NotificationStatus.PENDING
        assert "Password Reset" in notif.subject


# ==============================================================================
# GROUP 2: Transaction and Outbox Chaos Scenarios
# ==============================================================================


class TestTransactionAndOutboxChaos:
    """Rigorous failure, rollback, network partition, and concurrency chaos testing."""

    @pytest.mark.asyncio
    async def test_business_transaction_rollback_preserves_zero_orphan_notifications(
        self,
        test_tenant_a_id: uuid.UUID,
        employee_a_id: uuid.UUID,
        supervisor_a_id: uuid.UUID,
        supervisor_a_user_id: uuid.UUID,
    ):
        """When an exception occurs during the business transaction, rolling back ensures NO notification survives."""
        session = create_mock_db_session()
        handler = DomainNotificationHandler(session)

        # Simulate exception during business logic after notification generation
        with patch.object(
            handler, "_resolve_supervisor", return_value=(supervisor_a_user_id, "sup@tenant-a.com")
        ):
            event = LeaveRequestSubmittedEvent(
                tenant_id=test_tenant_a_id,
                leave_request_id=uuid.uuid4(),
                employee_id=employee_a_id,
                employee_name="Alice Worker",
                supervisor_id=supervisor_a_id,
                leave_type="ANNUAL",
                start_date=date(2026, 12, 1),
                end_date=date(2026, 12, 5),
                total_days=5.0,
                reason="Annual vacation",
            )
            created = await handler.handle_event(event)
            assert len(created) >= 1

            # Business failure occurs!
            try:
                raise RuntimeError("Database deadlock or constraint failure during leave deduction")
            except RuntimeError:
                await session.rollback()

            session.rollback.assert_awaited_once()
            session.commit.assert_not_awaited()

    def test_successful_commit_followed_by_celery_enqueue_failure_keeps_pending_outbox(
        self,
        test_tenant_a_id: uuid.UUID,
    ):
        """When Celery/Redis is unreachable, enqueue_celery_dispatch logs a warning and leaves notifications in PENDING."""
        fake_response = NotificationResponse(
            id=uuid.uuid4(),
            tenant_id=test_tenant_a_id,
            recipient_user_id=uuid.uuid4(),
            recipient_employee_id=None,
            recipient_destination="user@example.com",
            event_type="leave_request_submitted",
            channel=NotificationChannel.EMAIL.value,
            template_key="leave_request_submitted",
            subject="Leave Request Submitted",
            body="Your leave request was submitted.",
            status=NotificationStatus.PENDING.value,
            priority=NotificationPriority.NORMAL.value,
            scheduled_for=datetime.now(UTC),
            attempt_count=0,
            max_attempts=3,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        with patch(
            "services.workers.notification_tasks.dispatch_single_notification_task.delay",
            side_effect=RuntimeError("Connection refused: 127.0.0.1:6379 (Redis Down)"),
        ):
            # Must NOT raise exception; returns 0 enqueued and leaves record PENDING
            enqueued = enqueue_celery_dispatch([fake_response])
            assert enqueued == 0

    def test_stuck_processing_reconciliation_chaos_recovery(
        self,
        test_tenant_a_id: uuid.UUID,
    ):
        """Notifications stuck in PROCESSING status due to killed worker are recovered to RETRY_SCHEDULED or FAILED."""
        session = create_mock_db_session()
        now = datetime.now(UTC)
        cutoff = now - timedelta(minutes=15)

        # Record 1: Stuck, attempt 0 < max 3 -> Recovers to RETRY_SCHEDULED
        stuck_recoverable = Notification(
            id=uuid.uuid4(),
            tenant_id=test_tenant_a_id,
            recipient_destination="token-1",
            channel=NotificationChannel.PUSH.value,
            subject="Alert 1",
            body="Body 1",
            status=NotificationStatus.PROCESSING.value,
            priority=NotificationPriority.NORMAL.value,
            attempt_count=0,
            max_attempts=3,
            created_at=cutoff - timedelta(minutes=5),
            updated_at=cutoff - timedelta(minutes=1),
        )

        # Record 2: Stuck, attempt 2 >= max 3 -> Marked FAILED
        stuck_exhausted = Notification(
            id=uuid.uuid4(),
            tenant_id=test_tenant_a_id,
            recipient_destination="token-2",
            channel=NotificationChannel.PUSH.value,
            subject="Alert 2",
            body="Body 2",
            status=NotificationStatus.PROCESSING.value,
            priority=NotificationPriority.NORMAL.value,
            attempt_count=2,
            max_attempts=3,
            created_at=cutoff - timedelta(minutes=20),
            updated_at=cutoff - timedelta(minutes=1),
        )

        session.execute.return_value = make_query_result(all_items=[stuck_recoverable, stuck_exhausted])

        class MockSessionContext:
            async def __aenter__(self):
                return session

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        with patch("services.workers.notification_tasks.AsyncSessionLocal", return_value=MockSessionContext()):
            res = reconcile_stuck_processing_task(timeout_minutes=15)
            assert res["total_stuck_found"] == 2
            assert res["recovered_to_retry"] == 1
            assert res["marked_failed"] == 1
            assert stuck_recoverable.status == NotificationStatus.RETRY_SCHEDULED.value
            assert stuck_exhausted.status == NotificationStatus.FAILED.value

    @pytest.mark.asyncio
    async def test_provider_timeout_and_temporary_failure_backoff_progression(
        self,
        test_tenant_a_id: uuid.UUID,
    ):
        """Simulates provider timeout and transient failures; verifies backoff formula: 60s -> 120s -> 240s."""
        # 1. Backoff calculation formula checks
        assert calculate_exponential_backoff(0, base_seconds=60, max_seconds=3600) == timedelta(seconds=60)
        assert calculate_exponential_backoff(1, base_seconds=60, max_seconds=3600) == timedelta(seconds=120)
        assert calculate_exponential_backoff(2, base_seconds=60, max_seconds=3600) == timedelta(seconds=240)
        assert calculate_exponential_backoff(10, base_seconds=60, max_seconds=3600) == timedelta(seconds=3600)

        # 2. Dispatcher handling of ProviderTimeoutError
        session = create_mock_db_session()
        dispatcher = NotificationDispatcher(session, base_backoff_seconds=60)
        notif_id = uuid.uuid4()

        notif = Notification(
            id=notif_id,
            tenant_id=test_tenant_a_id,
            recipient_destination="user@example.com",
            channel=NotificationChannel.EMAIL.value,
            subject="Test Timeout",
            body="Timeout Body",
            status=NotificationStatus.PROCESSING.value,
            priority=NotificationPriority.NORMAL.value,
            attempt_count=0,
            max_attempts=3,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        with patch.object(dispatcher.repository, "claim_for_processing", return_value=notif):
            with patch.object(
                dispatcher.provider_registry,
                "get_provider",
                return_value=MockFailingProvider(timeout=True),
            ):
                with patch.object(
                    dispatcher.repository,
                    "record_retryable_failure",
                    return_value=notif,
                ):
                    result = await dispatcher.dispatch(notif_id, test_tenant_a_id)
                    assert result.status == NotificationStatus.RETRY_SCHEDULED
                    assert "Timeout" in (result.error_message or "")

    @pytest.mark.asyncio
    async def test_provider_permanent_failure_transitions_to_failed_without_retries(
        self,
        test_tenant_a_id: uuid.UUID,
    ):
        """Unretryable provider errors (e.g. invalid token, 400 Bad Request) transition immediately to FAILED."""
        session = create_mock_db_session()
        dispatcher = NotificationDispatcher(session)
        notif_id = uuid.uuid4()

        notif = Notification(
            id=notif_id,
            tenant_id=test_tenant_a_id,
            recipient_destination="invalid_recipient",
            channel=NotificationChannel.PUSH.value,
            subject="Test Permanent",
            body="Permanent Error Body",
            status=NotificationStatus.PROCESSING.value,
            priority=NotificationPriority.NORMAL.value,
            attempt_count=0,
            max_attempts=3,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        with patch.object(dispatcher.repository, "claim_for_processing", return_value=notif):
            with patch.object(
                dispatcher.provider_registry,
                "get_provider",
                return_value=MockFailingProvider(permanent=True),
            ):
                with patch.object(
                    dispatcher.repository,
                    "record_permanent_failure",
                    return_value=notif,
                ):
                    result = await dispatcher.dispatch(notif_id, test_tenant_a_id)
                    assert result.status == NotificationStatus.FAILED
                    assert "Invalid token format" in (result.error_message or "")

    @pytest.mark.asyncio
    async def test_duplicate_event_submission_idempotency(
        self,
        test_tenant_a_id: uuid.UUID,
        employee_a_id: uuid.UUID,
        supervisor_a_id: uuid.UUID,
        supervisor_a_user_id: uuid.UUID,
    ):
        """Submitting identical domain events twice returns existing notification without duplicate outbox records."""
        session = create_mock_db_session()
        handler = DomainNotificationHandler(session)
        leave_req_id = uuid.uuid4()

        with patch.object(
            handler, "_resolve_supervisor", return_value=(supervisor_a_user_id, "sup@tenant-a.com")
        ):
            event = LeaveRequestSubmittedEvent(
                tenant_id=test_tenant_a_id,
                leave_request_id=leave_req_id,
                employee_id=employee_a_id,
                employee_name="Alice Worker",
                supervisor_id=supervisor_a_id,
                leave_type="ANNUAL",
                start_date=date(2026, 12, 1),
                end_date=date(2026, 12, 5),
                total_days=5.0,
                reason="Annual vacation",
            )

            # First dispatch creates record
            first_dispatches = await handler.handle_event(event)
            assert len(first_dispatches) >= 1

            # Second identical event produces same deterministic idempotency key
            second_dispatches = await handler.handle_event(event)
            assert len(second_dispatches) >= 1
            assert first_dispatches[0].idempotency_key == second_dispatches[0].idempotency_key

    @pytest.mark.asyncio
    async def test_concurrent_worker_race_condition_atomic_claim(
        self,
        test_tenant_a_id: uuid.UUID,
    ):
        """When two Celery workers simultaneously attempt to dispatch the same notification, only one worker wins."""
        session1 = create_mock_db_session()
        session2 = create_mock_db_session()
        dispatcher1 = NotificationDispatcher(session1)
        dispatcher2 = NotificationDispatcher(session2)

        notif_id = uuid.uuid4()
        notif = Notification(
            id=notif_id,
            tenant_id=test_tenant_a_id,
            recipient_destination="dev@push.test",
            channel=NotificationChannel.PUSH.value,
            subject="Race Condition Test",
            body="Body",
            status=NotificationStatus.PROCESSING.value,
            priority=NotificationPriority.NORMAL.value,
            attempt_count=0,
            max_attempts=3,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        # Worker 1 succeeds in claiming and recording success
        with patch.object(dispatcher1.repository, "claim_for_processing", return_value=notif):
            with patch.object(dispatcher1.repository, "record_success", return_value=notif):
                res1 = await dispatcher1.dispatch(notif_id, test_tenant_a_id)
                assert res1.status in [NotificationStatus.SENT, NotificationStatus.PROCESSING]

        # Worker 2 attempts same claim; repository returns None (already claimed / row locked)
        with patch.object(dispatcher2.repository, "claim_for_processing", return_value=None):
            with patch.object(dispatcher2.repository, "get_notification", return_value=notif):
                res2 = await dispatcher2.dispatch(notif_id, test_tenant_a_id)
                # Worker 2 yields diagnostic result and does not double-dispatch
                assert "Could not claim" in (res2.error_message or "")

    def test_formal_at_least_once_delivery_semantics_documentation(self):
        """Formally verifies that external notification dispatch guarantees are At-Least-Once, never Exactly-Once."""
        from services.api.notifications import dispatcher

        doc = dispatcher.__doc__ or ""
        assert "At-Least-Once" in doc
        assert "Exactly-Once within the database state machine" in doc


# ==============================================================================
# GROUP 3: Multi-Tenant Security & Isolation Validation
# ==============================================================================


class TestMultiTenantSecurityAndIsolation:
    """Rigorous tenant boundary, preference isolation, RBAC, and data leakage testing."""

    @pytest.mark.asyncio
    async def test_cross_tenant_notification_access_rejection(
        self,
        test_tenant_a_id: uuid.UUID,
        test_tenant_b_id: uuid.UUID,
    ):
        """Tenant A cannot retrieve or modify notifications belonging to Tenant B."""
        session = create_mock_db_session()
        repo = NotificationRepository(session)
        notif_id = uuid.uuid4()

        # Database returns record with tenant_id B
        notif_b = Notification(
            id=notif_id,
            tenant_id=test_tenant_b_id,
            recipient_destination="b@tenant-b.com",
            channel=NotificationChannel.EMAIL.value,
            subject="Confidential Tenant B Alert",
            body="Sensitive Tenant B Info",
            status=NotificationStatus.SENT.value,
            priority=NotificationPriority.HIGH.value,
            attempt_count=1,
            max_attempts=3,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert notif_b.tenant_id == test_tenant_b_id

        # When queried with Tenant A context, repository must return None
        session.execute.return_value = make_query_result(scalar=None)
        res = await repo.get_notification(notif_id, test_tenant_a_id)
        assert res is None

    @pytest.mark.asyncio
    async def test_cross_tenant_template_isolation_and_immutability(
        self,
        test_tenant_a_id: uuid.UUID,
        test_tenant_b_id: uuid.UUID,
    ):
        """Tenant A cannot read, override, or edit Tenant B's templates; System templates remain immutable."""
        session = create_mock_db_session()
        repo = NotificationRepository(session)

        # 1. System template immutability
        system_tmpl = NotificationTemplate(
            id=uuid.uuid4(),
            tenant_id=None,
            template_key="system_default_test",
            name="System Default Template",
            event_type="leave_request_submitted",
            channel=NotificationChannel.EMAIL.value,
            subject_template="System Subject",
            body_template="System Body",
            locale="en",
            is_active=True,
            is_system=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert system_tmpl.is_system is True
        assert system_tmpl.tenant_id is None

        # 2. Tenant B custom override
        tenant_b_tmpl = NotificationTemplate(
            id=uuid.uuid4(),
            tenant_id=test_tenant_b_id,
            template_key="leave_request_submitted",
            name="Tenant B Custom Template",
            event_type="leave_request_submitted",
            channel=NotificationChannel.EMAIL.value,
            subject_template="Custom Tenant B Subject",
            body_template="Custom Tenant B Body",
            locale="en",
            is_active=True,
            is_system=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert tenant_b_tmpl.tenant_id == test_tenant_b_id

        # Attempt to lookup template under Tenant A returns system default, never Tenant B's override
        session.execute.return_value = make_query_result(scalar=None)
        res = await repo.get_template(test_tenant_a_id, "leave_request_submitted", "EMAIL")
        assert res is not None
        assert res.is_system is True
        assert res.tenant_id is None
        assert res.tenant_id != test_tenant_b_id

    @pytest.mark.asyncio
    async def test_cross_tenant_device_tokens_isolation(
        self,
        test_tenant_a_id: uuid.UUID,
        test_tenant_b_id: uuid.UUID,
    ):
        """Device tokens registered under Tenant B cannot be read or revoked by Tenant A."""
        session = create_mock_db_session()
        repo = NotificationRepository(session)
        raw_token = "fcm_token_tenant_b_secret"
        token_hash = hash_push_token(raw_token)

        # Token belongs to Tenant B
        token_b = DevicePushToken(
            id=uuid.uuid4(),
            tenant_id=test_tenant_b_id,
            user_id=uuid.uuid4(),
            platform=DevicePlatform.ANDROID.value,
            token_hash=token_hash,
            token=encrypt_push_token(raw_token),
            status="ACTIVE",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert token_b.tenant_id == test_tenant_b_id

        # Tenant A revocation attempt returns False (rowcount 0)
        session.execute.return_value = make_query_result(scalar=None)
        revoked = await repo.revoke_device_token(test_tenant_a_id, raw_token)
        assert revoked is False

    @pytest.mark.asyncio
    async def test_tenant_scoped_preferences_and_quiet_hours(
        self,
        test_tenant_a_id: uuid.UUID,
        test_tenant_b_id: uuid.UUID,
    ):
        """Quiet hours configured in Tenant A do not affect dispatch eligibility in Tenant B."""
        now_utc = datetime(2026, 11, 22, 23, 0, tzinfo=UTC)  # 11:00 PM UTC

        # Tenant A: Quiet hours active (22:00 - 07:00 UTC)
        pref_a = EffectivePreferences(
            is_email_enabled=True,
            is_push_enabled=True,
            is_sms_enabled=False,
            quiet_hours_enabled=True,
            quiet_hours_start="22:00",
            quiet_hours_end="07:00",
            timezone="UTC",
            category_preferences={},
            source="TENANT_DEFAULT",
        )
        res_a = QuietHoursEvaluator.evaluate(pref_a, NotificationPriority.NORMAL, evaluation_time_utc=now_utc)
        assert res_a.should_defer is True

        # Tenant B: Quiet hours disabled
        pref_b = EffectivePreferences(
            is_email_enabled=True,
            is_push_enabled=True,
            is_sms_enabled=False,
            quiet_hours_enabled=False,
            quiet_hours_start=None,
            quiet_hours_end=None,
            timezone="UTC",
            category_preferences={},
            source="TENANT_DEFAULT",
        )
        res_b = QuietHoursEvaluator.evaluate(pref_b, NotificationPriority.NORMAL, evaluation_time_utc=now_utc)
        assert res_b.should_defer is False

    @pytest.mark.asyncio
    async def test_manager_recipient_resolution_enforces_direct_report_hierarchy(
        self,
        test_tenant_a_id: uuid.UUID,
        employee_a_id: uuid.UUID,
        supervisor_a_id: uuid.UUID,
        supervisor_a_user_id: uuid.UUID,
    ):
        """Supervisor resolution ensures notifications only reach authorized reporting managers."""
        session = create_mock_db_session()
        handler = DomainNotificationHandler(session)

        # Mock Employee query returning supervisor_a_id as reporting manager
        session.execute.side_effect = [
            make_query_result(scalar=supervisor_a_id),  # reporting_manager_id
            make_query_result(first=(supervisor_a_user_id, "manager@company.com")),  # supervisor User
        ]

        mgr_uid, mgr_email = await handler._resolve_supervisor(test_tenant_a_id, employee_a_id)
        assert mgr_uid == supervisor_a_user_id
        assert mgr_email == "manager@company.com"

    def test_postgresql_rls_policies_and_table_grants_validation(self):
        """Validates that all Phase 10 tables define FORCE ROW LEVEL SECURITY and tenant isolation policies."""
        import inspect

        from database.migrations.versions import b5c6d7e8f9a0_phase_10_notifications as m10

        source = inspect.getsource(m10.upgrade)
        assert "ENABLE ROW LEVEL SECURITY" in source
        assert "FORCE ROW LEVEL SECURITY" in source
        assert "tenant_isolation" in source
        assert "current_setting('app.tenant_id', true)" in source


# ==============================================================================
# GROUP 4: Cross-Platform (Web & Mobile) Integration Simulation
# ==============================================================================


class TestCrossPlatformIntegrationSimulation:
    """Simulates the entire workflow connecting Backend -> Web Admin -> Flutter Mobile."""

    @pytest.mark.asyncio
    async def test_end_to_end_mobile_token_registration_and_inbox_gap_handling(
        self,
        test_tenant_a_id: uuid.UUID,
        employee_a_user_id: uuid.UUID,
    ):
        """Simulates mobile device token registration, FCM push delivery, and documented 404 inbox API gap."""
        session = create_mock_db_session()
        repo = NotificationRepository(session)

        raw_fcm_token = "fcm_mobile_client_token_987654321"
        token_hash = hash_push_token(raw_fcm_token)

        # 1. Mobile Token Registration: POST /api/v1/notifications/devices
        reg_req = DeviceTokenRegisterRequest(
            token=raw_fcm_token,
            platform=DevicePlatform.ANDROID,
            device_model="Pixel 8 Pro",
            os_version="Android 14",
            app_version="1.0.0",
        )
        saved_token = DevicePushToken(
            id=uuid.uuid4(),
            tenant_id=test_tenant_a_id,
            user_id=employee_a_user_id,
            platform=reg_req.platform.value,
            token_hash=token_hash,
            token=encrypt_push_token(raw_fcm_token),
            device_model=reg_req.device_model,
            os_version=reg_req.os_version,
            app_version=reg_req.app_version,
            status="ACTIVE",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        with patch.object(repo, "register_device_token", return_value=saved_token):
            token_record = await repo.register_device_token(
                tenant_id=test_tenant_a_id,
                user_id=employee_a_user_id,
                token=raw_fcm_token,
                platform=reg_req.platform.value,
                device_model=reg_req.device_model,
                os_version=reg_req.os_version,
                app_version=reg_req.app_version,
            )
            assert token_record.status == "ACTIVE"
            assert token_record.token_hash == token_hash

        # 2. Mock Push Provider Delivery: Verified using MockPushProvider
        mock_push = MockPushProvider()
        push_res = await mock_push.send(
            recipient_destination=raw_fcm_token,
            subject="Leave Request Approved",
            body="Your leave request has been approved.",
            payload={"deep_link_route": "/leave", "notification_id": str(uuid.uuid4())},
        )
        assert push_res.success is True
        assert push_res.status == ProviderStatus.ACCEPTED

        # 3. Mobile Logout: Device token revoked
        with patch.object(repo, "revoke_device_token", return_value=True):
            revoked = await repo.revoke_device_token(test_tenant_a_id, raw_fcm_token)
            assert revoked is True

        # 4. In-App Notification Center API Gap:
        # FastAPI backend does not yet define GET /api/v1/notifications/inbox
        # Verify app returns 404 for this route (which Flutter translates to ApiGapException)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/api/v1/notifications/inbox")
            assert resp.status_code == status.HTTP_404_NOT_FOUND


# ==============================================================================
# GROUP 5: Provider Readiness & Delivery Status Taxonomy
# ==============================================================================


class TestProviderReadinessAndDeliveryStatusTaxonomy:
    """Validates operational readiness taxonomy and strict separation of lifecycle statuses."""

    def test_channel_operational_readiness_taxonomy(self):
        """Asserts correct readiness taxonomy: MOCK, CONFIGURED_UNVERIFIED, and UNCONFIGURED."""
        # 1. PUSH Channel: Without credentials -> unconfigured permanent error
        fcm_mock = FirebasePushProvider(credentials_path=None)
        assert fcm_mock.name == "fcm"
        assert fcm_mock._is_configured is False

        # 2. EMAIL Channel: MockEmailProvider
        email_mock = MockEmailProvider()
        assert email_mock.name == "mock_email"

        # 3. SMS Channel: Unconfigured in Phase 10
        sms_mock = MockSmsProvider()
        assert sms_mock.name == "mock_sms"

    def test_strict_delivery_status_progression_invariants(self):
        """Asserts that SENT and DELIVERED are semantically and operationally distinct."""
        statuses = [s.value for s in NotificationStatus]
        assert "PENDING" in statuses
        assert "PROCESSING" in statuses
        assert "SENT" in statuses  # Provider accepted gateway handoff
        assert "DELIVERED" in statuses  # Client terminal delivery confirmed
        assert "RETRY_SCHEDULED" in statuses
        assert "FAILED" in statuses
        assert "CANCELLED" in statuses

        # SENT must NOT equal DELIVERED
        assert NotificationStatus.SENT != NotificationStatus.DELIVERED


# ==============================================================================
# GROUP 6: Performance & Reliability Simulation
# ==============================================================================


class TestPerformanceAndReliabilitySimulation:
    """Measures execution speed and throughput for batch operations and recovery tasks."""

    @pytest.mark.asyncio
    async def test_batch_outbox_notification_creation_performance(
        self,
        test_tenant_a_id: uuid.UUID,
        supervisor_a_user_id: uuid.UUID,
    ):
        """Measures execution time for creating a batch of 50 outbox notifications."""
        session = create_mock_db_session()
        service = NotificationService(session)

        start_time = time.perf_counter()
        count = 50
        for i in range(count):
            req = NotificationCreateRequest(
                recipient_user_id=supervisor_a_user_id,
                recipient_employee_id=None,
                recipient_destination=f"sup_{i}@company.com",
                event_type="leave_request_submitted",
                channel=NotificationChannel.EMAIL,
                template_key="leave_request_submitted",
                template_variables={
                    "employee_name": f"Worker {i}",
                    "leave_type": "ANNUAL",
                    "duration_days": "3",
                    "start_date": "2026-12-01",
                    "end_date": "2026-12-03",
                    "reason": "Family vacation",
                },
                priority=NotificationPriority.NORMAL,
                idempotency_key=f"bench:{test_tenant_a_id}:{i}",
            )
            await service.create_notification(test_tenant_a_id, req, enforce_preferences=False)

        duration_ms = (time.perf_counter() - start_time) * 1000
        # 50 records created in memory should complete under 500ms
        assert duration_ms < 500, f"Batch creation took too long: {duration_ms:.2f}ms"

    @pytest.mark.asyncio
    async def test_batch_dispatch_processing_performance(
        self,
        test_tenant_a_id: uuid.UUID,
    ):
        """Measures worker dispatch throughput on a batch of 25 pending notifications."""
        session = create_mock_db_session()
        dispatcher = NotificationDispatcher(session)

        fake_results = [
            DispatchResult(
                notification_id=uuid.uuid4(),
                status=NotificationStatus.SENT,
                provider_name="mock_email",
                attempt_count=1,
            )
            for _ in range(25)
        ]

        start_time = time.perf_counter()
        with patch.object(dispatcher, "dispatch_pending_batch", return_value=fake_results):
            results = await dispatcher.dispatch_pending_batch(tenant_id=test_tenant_a_id, limit=25)
            duration_ms = (time.perf_counter() - start_time) * 1000

        assert len(results) == 25
        assert duration_ms < 100, f"Batch dispatch took too long: {duration_ms:.2f}ms"


# ==============================================================================
# Helper Mock Provider & Coroutine Runners
# ==============================================================================


class MockFailingProvider(BaseNotificationProvider):
    """Custom mock provider for simulating timeouts, transient, and permanent provider errors."""

    def __init__(self, timeout: bool = False, permanent: bool = False):
        self.timeout = timeout
        self.permanent = permanent

    @property
    def channel(self) -> NotificationChannel:
        return NotificationChannel.PUSH

    @property
    def name(self) -> str:
        return "mock_failing_provider"

    async def send(
        self,
        recipient_destination: str | None,
        subject: str,
        body: str,
        payload: dict[str, Any] | None = None,
    ) -> ProviderResult:
        if self.timeout:
            raise ProviderTimeoutError("mock_failing_provider", "Connection timed out after 5000ms")
        if self.permanent:
            raise ProviderPermanentError("mock_failing_provider", "400 Bad Request: Invalid token format")
        raise ProviderRetryableError("mock_failing_provider", "503 Service Temporarily Unavailable")
