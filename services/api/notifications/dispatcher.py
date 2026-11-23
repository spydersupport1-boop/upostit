"""Core Dispatch Engine: orchestrates atomic status transitions, quiet hours, provider invocation, and retry policies.

Delivery Semantics & Invariants:
- Exactly-Once within the database state machine (via atomic conditional status claims).
- At-Least-Once downstream delivery: If downstream provider accepts the message but the worker
  or database session fails prior to commit, a retry may deliver a duplicate. Downstream idempotent
  message keys should be used where supported by the external provider.
- SENT != DELIVERED: Provider acceptance transitions status to SENT. Confirmed end-user reception
  requires asynchronous delivery webhooks (Phase 10.3+).
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from services.api.notifications.exceptions import (
    InvalidStateTransitionError,
    ProviderError,
    ProviderTimeoutError,
)
from services.api.notifications.preference_resolver import PreferenceResolver
from services.api.notifications.provider import (
    BaseNotificationProvider,
    ProviderRegistry,
)
from services.api.notifications.quiet_hours import QuietHoursEvaluator
from services.api.notifications.repository import NotificationRepository
from services.api.notifications.schemas import (
    DispatchResult,
    NotificationChannel,
    NotificationPriority,
    NotificationStatus,
    ProviderResult,
    ProviderStatus,
)

logger = logging.getLogger(__name__)


def calculate_exponential_backoff(
    attempt_count: int,
    base_seconds: int = 60,
    max_seconds: int = 3600,
) -> timedelta:
    """Calculates exponential backoff delay for retrying failed dispatch attempts.

    attempt 0 -> 60s (1m)
    attempt 1 -> 120s (2m)
    attempt 2 -> 240s (4m)
    capped at max_seconds (1 hour).
    """
    delay = min(base_seconds * (2**attempt_count), max_seconds)
    return timedelta(seconds=delay)


class NotificationDispatcher:
    """Orchestrates outbound notification delivery across registered providers."""

    def __init__(
        self,
        session: AsyncSession,
        provider_registry: ProviderRegistry | None = None,
        base_backoff_seconds: int = 60,
        max_backoff_seconds: int = 3600,
    ) -> None:
        self.session = session
        self.repository = NotificationRepository(session)
        self.provider_registry = provider_registry or ProviderRegistry()
        self.base_backoff_seconds = base_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds

    async def dispatch(
        self,
        notification_id: uuid.UUID,
        tenant_id: uuid.UUID,
        *,
        evaluation_time_utc: datetime | None = None,
    ) -> DispatchResult:
        """Executes a dispatch attempt for a specific notification.

        Args:
            notification_id: The ID of the notification to dispatch.
            tenant_id: Tenant context.
            evaluation_time_utc: Optional override for current time.

        Returns:
            DispatchResult summarizing the outcome.
        """
        now = evaluation_time_utc or datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)

        # 1. Atomic claim: transition PENDING / RETRY_SCHEDULED -> PROCESSING
        claimed = await self.repository.claim_for_processing(notification_id, tenant_id)
        if not claimed:
            # Check current status for diagnostic reporting
            current = await self.repository.get_notification(notification_id, tenant_id)
            if not current:
                raise InvalidStateTransitionError("NON_EXISTENT", NotificationStatus.PROCESSING.value)
            return DispatchResult(
                notification_id=notification_id,
                status=NotificationStatus(current.status),
                attempt_count=current.attempt_count,
                error_message=f"Could not claim notification in status '{current.status}'",
            )

        # 2. Quiet-hours re-evaluation at execution time
        user_pref = None
        if claimed.recipient_user_id:
            user_pref = await self.repository.get_user_preference(tenant_id, claimed.recipient_user_id)
        tenant_pref = await self.repository.get_tenant_default_preference(tenant_id)
        effective_pref = PreferenceResolver.resolve(user_pref, tenant_pref)

        # Check if channel was disabled in the interim
        allowed, skip_reason = PreferenceResolver.is_channel_allowed(
            claimed.channel, user_pref, tenant_pref
        )
        if not allowed:
            await self.repository.record_permanent_failure(
                notification_id=notification_id,
                tenant_id=tenant_id,
                error_message=f"Delivery aborted: {skip_reason}",
            )
            return DispatchResult(
                notification_id=notification_id,
                status=NotificationStatus.FAILED,
                attempt_count=claimed.attempt_count + 1,
                error_message=skip_reason,
            )

        quiet_result = QuietHoursEvaluator.evaluate(
            preferences=effective_pref,
            priority=NotificationPriority(claimed.priority),
            evaluation_time_utc=now,
        )

        if quiet_result.should_defer and quiet_result.next_eligible_dispatch_time:
            # Quiet hours active: defer dispatch
            deferred = await self.repository.defer_for_quiet_hours(
                notification_id=notification_id,
                tenant_id=tenant_id,
                next_eligible_at=quiet_result.next_eligible_dispatch_time,
                reason=quiet_result.reason or "Deferred due to quiet hours",
            )
            return DispatchResult(
                notification_id=notification_id,
                status=NotificationStatus.RETRY_SCHEDULED,
                attempt_count=deferred.attempt_count,
                is_deferred=True,
                next_eligible_at=quiet_result.next_eligible_dispatch_time,
                error_message=quiet_result.reason,
            )

        # 3. Resolve Provider
        try:
            channel_enum = NotificationChannel(claimed.channel)
            provider: BaseNotificationProvider = self.provider_registry.get_provider(channel_enum)
        except Exception as exc:
            logger.exception("Failed to locate provider for channel %s: %s", claimed.channel, exc)
            await self.repository.record_permanent_failure(
                notification_id=notification_id,
                tenant_id=tenant_id,
                error_message=f"Provider lookup failed: {str(exc)}",
            )
            return DispatchResult(
                notification_id=notification_id,
                status=NotificationStatus.FAILED,
                attempt_count=claimed.attempt_count + 1,
                error_message=str(exc),
            )

        # 4. Invoke Provider
        provider_result: ProviderResult
        try:
            provider_result = await provider.send(
                recipient_destination=claimed.recipient_destination,
                subject=claimed.subject,
                body=claimed.body,
                payload=claimed.payload_json,
            )
        except ProviderTimeoutError as exc:
            provider_result = ProviderResult(
                success=False,
                status=ProviderStatus.FAILED,
                provider_name=exc.provider_name,
                is_retryable=True,
                error_message=f"Timeout: {str(exc)}",
            )
        except ProviderError as exc:
            provider_result = ProviderResult(
                success=False,
                status=ProviderStatus.FAILED,
                provider_name=exc.provider_name,
                is_retryable=exc.is_retryable,
                error_message=str(exc),
            )
        except Exception as exc:
            logger.exception("Unexpected exception in provider %s: %s", provider.name, exc)
            provider_result = ProviderResult(
                success=False,
                status=ProviderStatus.FAILED,
                provider_name=provider.name,
                is_retryable=True,
                error_message=f"Unexpected error: {type(exc).__name__}",
            )

        # 5. Handle Provider Outcome
        if provider_result.success:
            updated = await self.repository.record_success(
                notification_id=notification_id,
                tenant_id=tenant_id,
                provider_name=provider_result.provider_name,
                provider_message_id=provider_result.provider_message_id or f"mock-{uuid.uuid4()}",
                provider_response=str(provider_result.raw_response or {}),
            )
            return DispatchResult(
                notification_id=notification_id,
                status=NotificationStatus.SENT,
                provider_name=provider_result.provider_name,
                provider_message_id=updated.provider_message_id,
                attempt_count=updated.attempt_count,
            )

        # Failure path: check retry eligibility
        next_attempt_number = claimed.attempt_count + 1
        can_retry = provider_result.is_retryable and (next_attempt_number < claimed.max_attempts)

        if can_retry:
            backoff_delta = calculate_exponential_backoff(
                attempt_count=claimed.attempt_count,
                base_seconds=self.base_backoff_seconds,
                max_seconds=self.max_backoff_seconds,
            )
            next_retry_at = now + backoff_delta
            updated = await self.repository.record_retryable_failure(
                notification_id=notification_id,
                tenant_id=tenant_id,
                error_message=provider_result.error_message or "Retryable provider dispatch failure",
                next_retry_at=next_retry_at,
                provider_name=provider_result.provider_name,
                provider_response=str(provider_result.raw_response or {}),
            )
            return DispatchResult(
                notification_id=notification_id,
                status=NotificationStatus.RETRY_SCHEDULED,
                provider_name=provider_result.provider_name,
                attempt_count=updated.attempt_count,
                next_eligible_at=next_retry_at,
                error_message=provider_result.error_message,
            )

        # Terminal failure
        updated = await self.repository.record_permanent_failure(
            notification_id=notification_id,
            tenant_id=tenant_id,
            error_message=provider_result.error_message or "Permanent provider dispatch rejection",
            provider_name=provider_result.provider_name,
            provider_response=str(provider_result.raw_response or {}),
        )
        return DispatchResult(
            notification_id=notification_id,
            status=NotificationStatus.FAILED,
            provider_name=provider_result.provider_name,
            attempt_count=updated.attempt_count,
            error_message=provider_result.error_message,
        )

    async def dispatch_pending_batch(
        self,
        tenant_id: uuid.UUID | None = None,
        limit: int = 50,
        now: datetime | None = None,
    ) -> list[DispatchResult]:
        """Polls and dispatches eligible pending notifications."""
        pending = await self.repository.get_pending_notifications(
            tenant_id=tenant_id,
            now=now,
            limit=limit,
        )
        results: list[DispatchResult] = []
        for notif in pending:
            try:
                res = await self.dispatch(
                    notification_id=notif.id,
                    tenant_id=notif.tenant_id,
                    evaluation_time_utc=now,
                )
                results.append(res)
            except Exception as exc:
                logger.exception("Failed processing notification %s: %s", notif.id, exc)
        return results
