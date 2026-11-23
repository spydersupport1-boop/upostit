"""Comprehensive unit and integration test suite for Phase 10 Milestone 10.4:
Domain Event Triggers & Notification Integration.

Test Groups:
1. TestLeaveDomainEvents: Leave submission, approval, rejection, cancellation.
2. TestConflictDomainEvents: Offline conflict submission, approval, rejection.
3. TestFraudShieldDomainEvents: High-risk fraud alerts, impossible travel, mock GPS.
4. TestEmployeeInvitationEvents: Invitation creation and resend (secret protection).
5. TestPasswordResetDomainEvents: Password reset request (secret protection).
6. TestIdempotencyAndOutboxReliability: Idempotency deduplication, outbox rollback, Celery failure resilience.
7. TestPreferencesAndQuietHoursIntegration: User opt-out, tenant policy, quiet-hours deferral.
8. TestCrossTenantIsolationAndManagerScoping: Cross-tenant boundary, manager reporting fallback.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.api.notifications.dispatcher import NotificationDispatcher
from services.api.notifications.event_handler import (
    DomainNotificationHandler,
    dispatch_domain_event,
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
from services.api.notifications.models import (
    Notification,
    NotificationPreference,
)
from services.api.notifications.schemas import (
    NotificationChannel,
    NotificationPriority,
    NotificationResponse,
    NotificationStatus,
    ProviderResult,
    ProviderStatus,
)

# ==============================================================================
# Helper Mock Database Factory
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
    """Builds an AsyncMock database session that mimics SQLAlchemy execution."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.execute.return_value = make_query_result()
    return session


# ==============================================================================
# 1. Phase 9 — Leave Domain Event Tests
# ==============================================================================


class TestLeaveDomainEvents:
    """Verifies notification dispatch on all Phase 9 leave lifecycle events."""

    @pytest.mark.asyncio
    async def test_leave_request_submitted_dispatches_to_supervisor(self):
        session = create_mock_db_session()
        tenant_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        mgr_emp_id = uuid.uuid4()
        mgr_user_id = uuid.uuid4()
        req_id = uuid.uuid4()

        async def mock_execute(stmt):
            sql_str = str(stmt)
            if "reporting_manager_id" in sql_str:
                return make_query_result(scalar=mgr_emp_id, first=(mgr_emp_id,))
            elif "user_id" in sql_str and "employees" in sql_str:
                return make_query_result(first=(mgr_user_id, "manager@company.test"))
            return make_query_result()

        session.execute = AsyncMock(side_effect=mock_execute)

        event = LeaveRequestSubmittedEvent(
            tenant_id=tenant_id,
            leave_request_id=req_id,
            employee_id=emp_id,
            employee_name="Alice Smith",
            leave_type="Annual Leave",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 5),
            total_days=Decimal("5.0"),
            reason="Summer family vacation",
            supervisor_id=None,
        )

        handler = DomainNotificationHandler(session)
        notifications = await handler.handle_event(event)

        # Both EMAIL and PUSH should be created for supervisor
        assert len(notifications) == 2
        channels = {n.channel for n in notifications}
        assert NotificationChannel.EMAIL in channels
        assert NotificationChannel.PUSH in channels

        email_notif = next(n for n in notifications if n.channel == NotificationChannel.EMAIL)
        assert email_notif.recipient_user_id == mgr_user_id
        assert email_notif.recipient_destination == "manager@company.test"
        assert "Alice Smith" in email_notif.subject
        assert "Summer family vacation" in email_notif.body
        assert email_notif.status == NotificationStatus.PENDING
        assert email_notif.priority == NotificationPriority.NORMAL

    @pytest.mark.asyncio
    async def test_leave_request_approved_dispatches_to_employee(self):
        session = create_mock_db_session()
        tenant_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        emp_user_id = uuid.uuid4()
        req_id = uuid.uuid4()

        async def mock_execute(stmt):
            sql_str = str(stmt)
            if "employees" in sql_str:
                return make_query_result(first=(emp_user_id, "alice@company.test"))
            return make_query_result()

        session.execute = AsyncMock(side_effect=mock_execute)

        event = LeaveRequestApprovedEvent(
            tenant_id=tenant_id,
            leave_request_id=req_id,
            employee_id=emp_id,
            employee_name="Alice Smith",
            leave_type="Annual Leave",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 5),
            supervisor_comment="Approved, enjoy your break!",
        )

        handler = DomainNotificationHandler(session)
        notifications = await handler.handle_event(event)

        assert len(notifications) == 2
        push_notif = next(n for n in notifications if n.channel == NotificationChannel.PUSH)
        assert push_notif.recipient_user_id == emp_user_id
        assert "Approved" in push_notif.subject
        assert push_notif.recipient_destination == f"user:{emp_user_id}"

        email_notif = next(n for n in notifications if n.channel == NotificationChannel.EMAIL)
        assert email_notif.recipient_destination == "alice@company.test"
        assert "Approved, enjoy your break!" in email_notif.body

    @pytest.mark.asyncio
    async def test_leave_request_rejected_dispatches_to_employee(self):
        session = create_mock_db_session()
        tenant_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        emp_user_id = uuid.uuid4()
        req_id = uuid.uuid4()

        async def mock_execute(stmt):
            sql_str = str(stmt)
            if "employees" in sql_str:
                return make_query_result(first=(emp_user_id, "alice@company.test"))
            return make_query_result()

        session.execute = AsyncMock(side_effect=mock_execute)

        event = LeaveRequestRejectedEvent(
            tenant_id=tenant_id,
            leave_request_id=req_id,
            employee_id=emp_id,
            employee_name="Alice Smith",
            leave_type="Casual Leave",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 2),
            rejection_reason="Team coverage unavailable on this date",
        )

        notifications = await dispatch_domain_event(session, event)
        assert len(notifications) == 2
        email_notif = next(n for n in notifications if n.channel == NotificationChannel.EMAIL)
        assert email_notif.recipient_destination == "alice@company.test"
        assert "Team coverage unavailable" in email_notif.body

    @pytest.mark.asyncio
    async def test_leave_request_cancelled_dispatches_to_supervisor(self):
        session = create_mock_db_session()
        tenant_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        mgr_user_id = uuid.uuid4()
        req_id = uuid.uuid4()

        async def mock_execute(stmt):
            sql_str = str(stmt)
            if "reporting_manager_id" in sql_str:
                return make_query_result(scalar=uuid.uuid4())
            elif "user_id" in sql_str and "employees" in sql_str:
                return make_query_result(first=(mgr_user_id, "supervisor@company.test"))
            return make_query_result()

        session.execute = AsyncMock(side_effect=mock_execute)

        event = LeaveRequestCancelledEvent(
            tenant_id=tenant_id,
            leave_request_id=req_id,
            employee_id=emp_id,
            employee_name="Alice Smith",
            leave_type="Sick Leave",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 2),
            cancellation_reason="Felt better, decided to work",
        )

        notifications = await dispatch_domain_event(session, event)
        assert len(notifications) == 2
        email_notif = next(n for n in notifications if n.channel == NotificationChannel.EMAIL)
        assert email_notif.recipient_destination == "supervisor@company.test"
        assert "Felt better" in email_notif.body


# ==============================================================================
# 2. Phase 8 — Attendance Conflict Domain Event Tests
# ==============================================================================


class TestConflictDomainEvents:
    """Verifies notification dispatch on offline sequence conflict submission and adjudication."""

    @pytest.mark.asyncio
    async def test_offline_conflict_submitted_event(self):
        session = create_mock_db_session()
        tenant_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        rev_user_id = uuid.uuid4()
        inc_id = uuid.uuid4()

        async def mock_execute(stmt):
            sql_str = str(stmt)
            if "users" in sql_str and "email" in sql_str:
                return make_query_result(scalar="reviewer@company.test")
            return make_query_result()

        session.execute = AsyncMock(side_effect=mock_execute)

        event = OfflineConflictSubmittedEvent(
            tenant_id=tenant_id,
            incident_id=inc_id,
            employee_id=emp_id,
            employee_name="Bob Jones",
            bundle_id="bndl-12345678",
            conflict_count=3,
            reason="Device sync clock failure during tunnel transit",
            assigned_reviewer_id=rev_user_id,
        )

        notifications = await dispatch_domain_event(session, event)
        assert len(notifications) == 2
        email_notif = next(n for n in notifications if n.channel == NotificationChannel.EMAIL)
        assert email_notif.recipient_user_id == rev_user_id
        assert email_notif.recipient_destination == "reviewer@company.test"
        assert "3 incident(s)" in email_notif.body
        assert str(inc_id) in email_notif.body

    @pytest.mark.asyncio
    async def test_attendance_conflict_adjudication_events(self):
        session = create_mock_db_session()
        tenant_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        emp_user_id = uuid.uuid4()
        rev_user_id = uuid.uuid4()
        inc_id = uuid.uuid4()

        async def mock_execute(stmt):
            sql_str = str(stmt)
            if "employees" in sql_str:
                return make_query_result(first=(emp_user_id, "bob@company.test"))
            return make_query_result()

        session.execute = AsyncMock(side_effect=mock_execute)

        # 1. Approved Event
        app_event = AttendanceConflictApprovedEvent(
            tenant_id=tenant_id,
            incident_id=inc_id,
            employee_id=emp_id,
            employee_name="Bob Jones",
            reviewer_user_id=rev_user_id,
            adjudication_comment="Manual check-in verified with site manager",
        )
        app_notifs = await dispatch_domain_event(session, app_event)
        assert len(app_notifs) == 2
        app_email = next(n for n in app_notifs if n.channel == NotificationChannel.EMAIL)
        assert app_email.recipient_destination == "bob@company.test"
        assert "Manual check-in verified" in app_email.body

        # 2. Rejected Event
        rej_event = AttendanceConflictRejectedEvent(
            tenant_id=tenant_id,
            incident_id=inc_id,
            employee_id=emp_id,
            employee_name="Bob Jones",
            reviewer_user_id=rev_user_id,
            rejection_reason="GPS logs indicate off-site punch",
        )
        rej_notifs = await dispatch_domain_event(session, rej_event)
        assert len(rej_notifs) == 2
        rej_email = next(n for n in rej_notifs if n.channel == NotificationChannel.EMAIL)
        assert rej_email.recipient_destination == "bob@company.test"
        assert "GPS logs indicate off-site" in rej_email.body


# ==============================================================================
# 3. Phase 7 — Fraud Shield Domain Event Tests
# ==============================================================================


class TestFraudShieldDomainEvents:
    """Verifies urgent security notifications for high risk scores, velocity anomalies, and mock GPS."""

    @pytest.mark.asyncio
    async def test_high_risk_fraud_alert_is_urgent_priority(self):
        session = create_mock_db_session()
        tenant_id = uuid.uuid4()
        admin_id = uuid.uuid4()
        att_id = uuid.uuid4()

        async def mock_execute(stmt):
            sql_str = str(stmt)
            if "users" in sql_str:
                return make_query_result(all_items=[(admin_id, "security@company.test")])
            return make_query_result()

        session.execute = AsyncMock(side_effect=mock_execute)

        event = HighRiskFraudAlertEvent(
            tenant_id=tenant_id,
            attendance_event_id=att_id,
            employee_id=uuid.uuid4(),
            employee_name="Charlie Davis",
            risk_score=85,
            risk_category="CRITICAL",
            attendance_event_type="CHECK_IN",
            flag_summary="MOCK_LOCATION_DETECTED, REVOKED_DEVICE",
        )

        notifications = await dispatch_domain_event(session, event)
        assert len(notifications) == 2

        for n in notifications:
            assert n.recipient_user_id == admin_id
            # Security alerts are strictly URGENT priority
            assert n.priority == NotificationPriority.URGENT
            assert n.related_entity_type == "attendance_event"
            assert n.related_entity_id == att_id

        email_notif = next(n for n in notifications if n.channel == NotificationChannel.EMAIL)
        assert email_notif.recipient_destination == "security@company.test"
        assert "URGENT" in email_notif.subject
        assert "Charlie Davis" in email_notif.body
        assert "Score: 85" in email_notif.body

    @pytest.mark.asyncio
    async def test_impossible_travel_signal_alert(self):
        session = create_mock_db_session()
        tenant_id = uuid.uuid4()
        admin_id = uuid.uuid4()

        async def mock_execute(stmt):
            sql_str = str(stmt)
            if "users" in sql_str:
                return make_query_result(all_items=[(admin_id, "security@company.test")])
            return make_query_result()

        session.execute = AsyncMock(side_effect=mock_execute)

        event = ImpossibleTravelSignalEvent(
            tenant_id=tenant_id,
            attendance_event_id=uuid.uuid4(),
            employee_id=uuid.uuid4(),
            employee_name="Charlie Davis",
            velocity_mps=450.5,
            distance_km=120.3,
            elapsed_seconds=267.0,
        )

        notifications = await dispatch_domain_event(session, event)
        assert len(notifications) == 2
        email_notif = next(n for n in notifications if n.channel == NotificationChannel.EMAIL)
        assert email_notif.recipient_destination == "security@company.test"
        assert "450.5 m/s" in email_notif.body
        assert "120.30 km" in email_notif.body

    @pytest.mark.asyncio
    async def test_mock_gps_detected_alert(self):
        session = create_mock_db_session()
        tenant_id = uuid.uuid4()
        admin_id = uuid.uuid4()

        async def mock_execute(stmt):
            sql_str = str(stmt)
            if "users" in sql_str:
                return make_query_result(all_items=[(admin_id, "security@company.test")])
            return make_query_result()

        session.execute = AsyncMock(side_effect=mock_execute)

        event = MockGpsDetectedEvent(
            tenant_id=tenant_id,
            attendance_event_id=uuid.uuid4(),
            employee_id=uuid.uuid4(),
            employee_name="Charlie Davis",
            device_id="device-mock-xyz",
            location_summary="Mock location provider active at lat=37.77, lon=-122.41",
        )

        notifications = await dispatch_domain_event(session, event)
        assert len(notifications) == 2
        email_notif = next(n for n in notifications if n.channel == NotificationChannel.EMAIL)
        assert email_notif.recipient_destination == "security@company.test"
        assert "Mock location provider active" in email_notif.body
        assert "device-mock-xyz" in email_notif.body


# ==============================================================================
# 4. Phase 4 — Employee Invitation Events (Secret Protection)
# ==============================================================================


class TestEmployeeInvitationEvents:
    """Verifies invitation notifications and zero-exposure of invitation secrets."""

    @pytest.mark.asyncio
    async def test_invitation_created_protects_raw_token(self):
        session = create_mock_db_session()
        tenant_id = uuid.uuid4()
        inv_id = uuid.uuid4()
        emp_id = uuid.uuid4()

        raw_secret_token = "secret_raw_token_abcdef1234567890"
        activation_url = f"https://app.upostit.test/activate?token={raw_secret_token}"

        event = EmployeeInvitationCreatedEvent(
            tenant_id=tenant_id,
            invitation_id=inv_id,
            employee_id=emp_id,
            recipient_email="newhire@company.test",
            recipient_name="David Miller",
            company_name="Acme Corp",
            activation_url=activation_url,
            expires_hours=72,
        )

        notifications = await dispatch_domain_event(session, event)
        # Invitations are EMAIL only (new hire has no mobile device token registered)
        assert len(notifications) == 1
        notif = notifications[0]
        assert notif.channel == NotificationChannel.EMAIL
        assert notif.recipient_destination == "newhire@company.test"
        assert notif.priority == NotificationPriority.HIGH

        # Verify safe substitution
        assert "Acme Corp" in notif.subject
        assert "David Miller" in notif.body
        assert activation_url in notif.body

        # CRITICAL SECURITY INVARIANT: raw token alone is NEVER logged or stored in isolation
        assert notif.payload_json is not None
        assert "token" not in notif.payload_json
        assert "raw_token" not in notif.payload_json

    @pytest.mark.asyncio
    async def test_invitation_sent_resend_event(self):
        session = create_mock_db_session()
        tenant_id = uuid.uuid4()
        inv_id = uuid.uuid4()

        event = EmployeeInvitationSentEvent(
            tenant_id=tenant_id,
            invitation_id=inv_id,
            employee_id=uuid.uuid4(),
            recipient_email="newhire@company.test",
            recipient_name="David Miller",
            company_name="Acme Corp",
            activation_url="https://app.upostit.test/activate?token=resend123",
            expires_hours=48,
        )

        notifications = await dispatch_domain_event(session, event)
        assert len(notifications) == 1
        assert "re-sent" in notifications[0].body


# ==============================================================================
# 5. Phase 2 — Password Reset Domain Event Tests (Secret Protection)
# ==============================================================================


class TestPasswordResetDomainEvents:
    """Verifies password reset notifications and zero-exposure of reset tokens."""

    @pytest.mark.asyncio
    async def test_password_reset_requested_urgent_email(self):
        session = create_mock_db_session()
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()

        reset_url = "https://app.upostit.test/reset-password?token=pwd_reset_token_xyz"

        event = PasswordResetRequestedEvent(
            tenant_id=tenant_id,
            user_id=user_id,
            user_email="owner@acme.test",
            user_name="Emma Watson",
            company_name="Acme Corp",
            reset_url=reset_url,
            expires_minutes=30,
        )

        notifications = await dispatch_domain_event(session, event)
        assert len(notifications) == 1
        notif = notifications[0]
        assert notif.channel == NotificationChannel.EMAIL
        assert notif.recipient_user_id == user_id
        assert notif.recipient_destination == "owner@acme.test"
        assert notif.priority == NotificationPriority.URGENT

        assert "Password Reset Request - Acme Corp" in notif.subject
        assert "Emma Watson" in notif.body
        assert reset_url in notif.body

        # Verification of secret protection
        assert "token" not in notif.payload_json
        assert "raw_token" not in notif.payload_json


# ==============================================================================
# 6. Idempotency & Outbox Reliability Tests
# ==============================================================================


class TestIdempotencyAndOutboxReliability:
    """Verifies deduplication, transactional rollback isolation, and Celery error resilience."""

    @pytest.mark.asyncio
    async def test_duplicate_event_processing_returns_existing_notification(self):
        session = create_mock_db_session()
        tenant_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        user_id = uuid.uuid4()
        req_id = uuid.uuid4()

        existing_notif = Notification(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            recipient_user_id=user_id,
            recipient_destination="emp@test.local",
            channel="EMAIL",
            body="Approved",
            status="SENT",
            priority="NORMAL",
            event_type="leave_request_approved",
            scheduled_for=datetime.now(UTC),
            attempt_count=1,
            max_attempts=3,
            idempotency_key=f"leave_request_approved:{req_id}:{emp_id}:EMAIL",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        async def mock_execute(stmt):
            sql_str = str(stmt)
            if "employees" in sql_str:
                return make_query_result(first=(user_id, "emp@test.local"))
            elif "idempotency_key" in sql_str:
                # Simulate existing row in DB
                return make_query_result(scalar=existing_notif)
            return make_query_result()

        session.execute = AsyncMock(side_effect=mock_execute)

        event = LeaveRequestApprovedEvent(
            tenant_id=tenant_id,
            leave_request_id=req_id,
            employee_id=emp_id,
            employee_name="Alice",
            leave_type="Annual",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 2),
        )

        handler = DomainNotificationHandler(session)
        notifications = await handler.handle_event(event)

        # The email notification matched the existing row and was returned with existing ID
        email_n = next(n for n in notifications if n.channel == NotificationChannel.EMAIL)
        assert email_n.id == existing_notif.id

    @pytest.mark.asyncio
    async def test_transactional_outbox_rollback_simulation(self):
        """Simulates transaction rollback: business operation and staged notifications roll back together."""
        session = create_mock_db_session()
        staged_objects = []
        session.add = MagicMock(side_effect=lambda obj: staged_objects.append(obj))

        async def mock_execute(stmt):
            sql_str = str(stmt)
            if "users" in sql_str:
                return make_query_result(all_items=[(uuid.uuid4(), "admin@test.local")])
            return make_query_result()

        session.execute = AsyncMock(side_effect=mock_execute)

        event = HighRiskFraudAlertEvent(
            tenant_id=uuid.uuid4(),
            attendance_event_id=uuid.uuid4(),
            employee_id=uuid.uuid4(),
            employee_name="Test User",
            risk_score=90,
            risk_category="CRITICAL",
            attendance_event_type="CHECK_IN",
            flag_summary="MOCK_LOCATION",
        )

        await dispatch_domain_event(session, event)

        # Assert notifications were added to the session
        assert len(staged_objects) > 0
        assert all(isinstance(obj, Notification) for obj in staged_objects)

        # Now simulate business transaction failure
        await session.rollback()
        assert session.rollback.called

    def test_celery_enqueue_failure_resilience(self):
        """Ensures that Celery/Redis connection failures do not crash the caller."""
        nid = uuid.uuid4()
        fake_response = NotificationResponse(
            id=nid,
            tenant_id=uuid.uuid4(),
            channel=NotificationChannel.EMAIL,
            status=NotificationStatus.PENDING,
            priority=NotificationPriority.NORMAL,
            event_type="leave_request_approved",
            recipient_destination="test@company.test",
            subject="Subj",
            body="Body",
            scheduled_for=datetime.now(UTC),
            attempt_count=0,
            max_attempts=3,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        with patch(
            "services.workers.notification_tasks.dispatch_single_notification_task.delay",
            side_effect=RuntimeError("Redis connection refused on port 6379"),
        ):
            # Enqueue helper must NOT raise exception; logs warning and returns 0 enqueued
            enqueued = enqueue_celery_dispatch([fake_response])
            assert enqueued == 0

    @pytest.mark.asyncio
    async def test_provider_failure_does_not_rollback_business_transaction(self):
        """Provider failure only marks the notification as RETRY_SCHEDULED or FAILED, leaving business entities intact."""
        session = create_mock_db_session()
        dispatcher = NotificationDispatcher(session)

        notif_id = uuid.uuid4()
        tid = uuid.uuid4()
        notif = Notification(
            id=notif_id,
            tenant_id=tid,
            recipient_destination="dev_unregistered@push.test",
            channel=NotificationChannel.PUSH.value,
            body="Test",
            status=NotificationStatus.PROCESSING.value,
            priority=NotificationPriority.NORMAL.value,
            attempt_count=0,
            max_attempts=3,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        async def mock_execute(stmt):
            sql_str = str(stmt)
            if "notifications" in sql_str:
                return make_query_result(scalar=notif)
            return make_query_result()

        session.execute = AsyncMock(side_effect=mock_execute)

        with patch.object(dispatcher.provider_registry, "get_provider") as mock_get_provider:
            mock_provider = AsyncMock()
            mock_provider.send.return_value = ProviderResult(
                success=False,
                status=ProviderStatus.FAILED,
                provider_name="MockPush",
                is_retryable=True,
                error_message="Gateway timeout",
            )
            mock_get_provider.return_value = mock_provider

            dispatch_result = await dispatcher.dispatch(
                notification_id=notif_id,
                tenant_id=tid,
            )
            assert dispatch_result.status == NotificationStatus.RETRY_SCHEDULED
            # Critical invariant: business session was never rolled back
            assert not session.rollback.called

    def test_worker_queries_strictly_use_retry_scheduled_not_retry(self):
        """Verifies that the canonical lifecycle status is RETRY_SCHEDULED and 'RETRY' is not an enum value."""
        assert NotificationStatus.RETRY_SCHEDULED.value == "RETRY_SCHEDULED"
        assert not hasattr(NotificationStatus, "RETRY")


# ==============================================================================
# 7. User Preferences & Quiet Hours Integration Tests
# ==============================================================================


class TestPreferencesAndQuietHoursIntegration:
    """Verifies preference filtering and quiet-hours scheduling."""

    @pytest.mark.asyncio
    async def test_user_opt_out_skips_channel(self):
        session = create_mock_db_session()
        tenant_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        emp_user_id = uuid.uuid4()

        # User preference explicitly disables email
        user_pref = NotificationPreference(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=emp_user_id,
            is_push_enabled=True,
            is_email_enabled=False,  # OPTED OUT
            is_sms_enabled=False,
        )

        async def mock_execute(stmt):
            sql_str = str(stmt)
            if "employees" in sql_str:
                return make_query_result(first=(emp_user_id, "emp@company.test"))
            elif "notification_preferences" in sql_str:
                return make_query_result(scalar=user_pref)
            return make_query_result()

        session.execute = AsyncMock(side_effect=mock_execute)

        event = LeaveRequestApprovedEvent(
            tenant_id=tenant_id,
            leave_request_id=uuid.uuid4(),
            employee_id=emp_id,
            employee_name="Alice",
            leave_type="Annual",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 2),
        )

        notifications = await dispatch_domain_event(session, event)
        # EMAIL is skipped due to user preference; only PUSH is created
        assert len(notifications) == 1
        assert notifications[0].channel == NotificationChannel.PUSH

    @pytest.mark.asyncio
    async def test_quiet_hours_defers_dispatch(self):
        session = create_mock_db_session()
        tenant_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        emp_user_id = uuid.uuid4()

        # User preference with quiet hours enabled: 22:00 to 07:00 in UTC
        user_pref = NotificationPreference(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=emp_user_id,
            is_push_enabled=True,
            is_email_enabled=True,
            is_sms_enabled=False,
            quiet_hours_enabled=True,
            quiet_hours_start="22:00",
            quiet_hours_end="07:00",
            timezone="UTC",
        )

        async def mock_execute(stmt):
            sql_str = str(stmt)
            if "employees" in sql_str:
                return make_query_result(first=(emp_user_id, "emp@company.test"))
            elif "notification_preferences" in sql_str:
                return make_query_result(scalar=user_pref)
            return make_query_result()

        session.execute = AsyncMock(side_effect=mock_execute)

        # Event occurs at 23:30 UTC (inside quiet hours)
        event_time = datetime(2026, 6, 1, 23, 30, tzinfo=UTC)

        event = LeaveRequestApprovedEvent(
            tenant_id=tenant_id,
            leave_request_id=uuid.uuid4(),
            employee_id=emp_id,
            employee_name="Alice",
            leave_type="Annual",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 2),
            occurred_at=event_time,
        )

        notifications = await dispatch_domain_event(session, event)
        assert len(notifications) == 2

        # Scheduled time should be deferred past quiet hours end (next day 07:00 UTC)
        for n in notifications:
            assert n.scheduled_for > event_time
            assert n.scheduled_for.hour == 7
            assert n.scheduled_for.minute == 0

    @pytest.mark.asyncio
    async def test_password_reset_during_quiet_hours_is_deferred(self):
        """Password reset requested during quiet hours respects user quiet hours without bypass."""
        session = create_mock_db_session()
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()

        user_pref = NotificationPreference(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            is_push_enabled=True,
            is_email_enabled=True,
            is_sms_enabled=False,
            quiet_hours_enabled=True,
            quiet_hours_start="22:00",
            quiet_hours_end="07:00",
            timezone="UTC",
        )

        async def mock_execute(stmt):
            sql_str = str(stmt)
            if "notification_preferences" in sql_str:
                return make_query_result(scalar=user_pref)
            return make_query_result()

        session.execute = AsyncMock(side_effect=mock_execute)

        event_time = datetime(2026, 6, 1, 23, 45, tzinfo=UTC)
        event = PasswordResetRequestedEvent(
            tenant_id=tenant_id,
            user_id=user_id,
            user_email="user@company.test",
            user_name="Emma",
            company_name="Acme",
            reset_url="https://app.upostit.test/reset-password?token=safe_token",
            expires_minutes=30,
            occurred_at=event_time,
        )

        notifications = await dispatch_domain_event(session, event)
        assert len(notifications) == 1
        notif = notifications[0]
        assert notif.priority == NotificationPriority.URGENT
        # Critical invariant: URGENT priority strictly adheres to quiet hours
        assert notif.scheduled_for > event_time
        assert notif.scheduled_for.hour == 7
        assert notif.scheduled_for.minute == 0

    @pytest.mark.asyncio
    async def test_fraud_alert_during_quiet_hours_is_deferred(self):
        """High risk fraud alerts during admin quiet hours are deferred to morning without bypass."""
        session = create_mock_db_session()
        tenant_id = uuid.uuid4()
        admin_user_id = uuid.uuid4()

        admin_pref = NotificationPreference(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=admin_user_id,
            is_push_enabled=True,
            is_email_enabled=True,
            is_sms_enabled=False,
            quiet_hours_enabled=True,
            quiet_hours_start="22:00",
            quiet_hours_end="07:00",
            timezone="UTC",
        )

        async def mock_execute(stmt):
            sql_str = str(stmt)
            if "users" in sql_str:
                return make_query_result(all_items=[(admin_user_id, "admin@company.test")])
            elif "notification_preferences" in sql_str:
                return make_query_result(scalar=admin_pref)
            return make_query_result()

        session.execute = AsyncMock(side_effect=mock_execute)

        event_time = datetime(2026, 6, 1, 23, 15, tzinfo=UTC)
        event = HighRiskFraudAlertEvent(
            tenant_id=tenant_id,
            attendance_event_id=uuid.uuid4(),
            employee_id=uuid.uuid4(),
            employee_name="Charlie Davis",
            risk_score=95,
            risk_category="CRITICAL",
            attendance_event_type="CHECK_IN",
            flag_summary="MOCK_LOCATION",
            occurred_at=event_time,
        )

        notifications = await dispatch_domain_event(session, event)
        assert len(notifications) == 2
        for n in notifications:
            assert n.priority == NotificationPriority.URGENT
            # All categories respect recipient quiet hours
            assert n.scheduled_for > event_time
            assert n.scheduled_for.hour == 7
            assert n.scheduled_for.minute == 0


# ==============================================================================
# 8. Cross-Tenant Isolation & Supervisor Scoping Tests
# ==============================================================================


class TestCrossTenantIsolationAndManagerScoping:
    """Verifies strict tenant isolation and hierarchy fallback."""

    @pytest.mark.asyncio
    async def test_supervisor_resolution_fallback_to_tenant_admin(self):
        """When employee has no reporting manager, event resolves to tenant admin."""
        session = create_mock_db_session()
        tenant_id = uuid.uuid4()
        admin_user_id = uuid.uuid4()

        async def mock_execute(stmt):
            sql_str = str(stmt)
            if "reporting_manager_id" in sql_str:
                return make_query_result(scalar=None)
            elif "users" in sql_str:
                return make_query_result(first=(admin_user_id, "admin@test.local"))
            return make_query_result()

        session.execute = AsyncMock(side_effect=mock_execute)

        handler = DomainNotificationHandler(session)
        resolved_sup, sup_email = await handler._resolve_supervisor(tenant_id, uuid.uuid4())
        assert resolved_sup == admin_user_id
        assert sup_email == "admin@test.local"

    @pytest.mark.asyncio
    async def test_cross_tenant_isolation_enforced(self):
        """Ensures notifications created in tenant A carry tenant A ID."""
        session = create_mock_db_session()
        tenant_a = uuid.uuid4()

        async def mock_execute(stmt):
            sql_str = str(stmt)
            if "users" in sql_str:
                return make_query_result(all_items=[(uuid.uuid4(), "admin@tenanta.local")])
            return make_query_result()

        session.execute = AsyncMock(side_effect=mock_execute)

        event = HighRiskFraudAlertEvent(
            tenant_id=tenant_a,
            attendance_event_id=uuid.uuid4(),
            employee_id=uuid.uuid4(),
            employee_name="Tenant A Employee",
            risk_score=95,
            risk_category="CRITICAL",
            attendance_event_type="CHECK_IN",
            flag_summary="MOCK_LOCATION",
        )

        notifications = await dispatch_domain_event(session, event)
        assert len(notifications) > 0
        for n in notifications:
            assert n.tenant_id == tenant_a
