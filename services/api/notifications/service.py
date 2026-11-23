"""Notification Creation Service: handles recipient resolution, preferences, template rendering, and persistence."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.auth.models import User
from services.api.employees.models import Employee
from services.api.notifications.crypto import (
    decrypt_push_token as decrypt_token_at_rest,
)
from services.api.notifications.exceptions import (
    ChannelDisabledError,
    RecipientNotFoundError,
    TemplateNotFoundError,
)
from services.api.notifications.preference_resolver import PreferenceResolver
from services.api.notifications.quiet_hours import QuietHoursEvaluator
from services.api.notifications.repository import NotificationRepository
from services.api.notifications.schemas import (
    NotificationCreateRequest,
    NotificationResponse,
)
from services.api.notifications.template_renderer import SafeTemplateRenderer


class NotificationService:
    """Service layer for preparing, validating, and persisting outbound notifications."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = NotificationRepository(session)

    async def _resolve_destination(
        self,
        tenant_id: uuid.UUID,
        channel: str,
        recipient_destination: str | None,
        recipient_user_id: uuid.UUID | None,
        recipient_employee_id: uuid.UUID | None,
    ) -> str:
        """Resolves destination address (email, phone, or push token) from database identities."""
        if recipient_destination and recipient_destination.strip():
            return recipient_destination.strip()

        ch = channel.upper()

        if ch == "EMAIL":
            if recipient_user_id:
                user_stmt = select(User).where(User.id == recipient_user_id, User.tenant_id == tenant_id)
                user = (await self.session.execute(user_stmt)).scalar_one_or_none()
                if user and user.email:
                    return user.email
            if recipient_employee_id:
                emp_stmt = select(Employee).where(Employee.id == recipient_employee_id, Employee.tenant_id == tenant_id)
                emp = (await self.session.execute(emp_stmt)).scalar_one_or_none()
                if emp and emp.work_email:
                    return emp.work_email
            raise RecipientNotFoundError("Could not resolve recipient email address from user or employee ID")

        elif ch == "SMS":
            if recipient_employee_id:
                emp_stmt = select(Employee).where(Employee.id == recipient_employee_id, Employee.tenant_id == tenant_id)
                emp = (await self.session.execute(emp_stmt)).scalar_one_or_none()
                if emp and emp.phone_number:
                    return emp.phone_number
            if recipient_user_id:
                emp_stmt = select(Employee).where(Employee.user_id == recipient_user_id, Employee.tenant_id == tenant_id)
                emp = (await self.session.execute(emp_stmt)).scalar_one_or_none()
                if emp and emp.phone_number:
                    return emp.phone_number
            raise RecipientNotFoundError("Could not resolve recipient phone number for SMS delivery")

        elif ch == "PUSH":
            if recipient_user_id:
                tokens = await self.repository.get_active_tokens_for_user(tenant_id, recipient_user_id)
                if tokens:
                    # Use most recently updated active token
                    sorted_tokens = sorted(tokens, key=lambda t: t.last_seen_at or t.created_at, reverse=True)
                    decrypted = decrypt_token_at_rest(sorted_tokens[0].token)
                    return decrypted
                # If no token registered yet, record destination as recipient user URI so notification is queued
                return f"user:{recipient_user_id}"
            raise RecipientNotFoundError("Push notifications require a valid recipient_user_id")

        raise RecipientNotFoundError(f"Unsupported notification channel: {channel}")

    async def create_notification(
        self,
        tenant_id: uuid.UUID,
        request: NotificationCreateRequest,
        *,
        enforce_preferences: bool = True,
    ) -> NotificationResponse:
        """Validates, resolves, renders, and persists an outbound notification.

        Args:
            tenant_id: Trusted tenant context.
            request: Typed notification creation request.
            enforce_preferences: If True, rejects creation if channel is disabled by preference.

        Returns:
            NotificationResponse representation of the persisted record.

        Raises:
            TemplateNotFoundError: If template is not found.
            TemplateRenderError: If required variables are missing or malicious syntax is detected.
            ChannelDisabledError: If enforce_preferences is True and channel is disabled.
            RecipientNotFoundError: If destination cannot be resolved.
        """
        ch_str = request.channel.value

        # 1. Resolve Preferences
        user_pref = None
        if request.recipient_user_id:
            user_pref = await self.repository.get_user_preference(tenant_id, request.recipient_user_id)
        tenant_default_pref = await self.repository.get_tenant_default_preference(tenant_id)

        if enforce_preferences:
            allowed, skip_reason = PreferenceResolver.is_channel_allowed(
                request.channel, user_pref, tenant_default_pref
            )
            if not allowed:
                raise ChannelDisabledError(ch_str, skip_reason or "Channel disabled by preference")

        # 2. Resolve Template
        template = await self.repository.get_template(
            tenant_id=tenant_id,
            template_key=request.template_key,
            channel=ch_str,
            locale=request.locale,
        )
        if not template:
            raise TemplateNotFoundError(
                template_key=request.template_key,
                channel=ch_str,
                locale=request.locale,
            )

        # 3. Render Subject and Body Safely
        rendered_subject, rendered_body = SafeTemplateRenderer.render_notification(
            subject_template=template.subject_template,
            body_template=template.body_template,
            variables=request.template_variables,
            is_html_channel=(ch_str == "EMAIL"),
        )

        # 4. Resolve Destination
        destination = await self._resolve_destination(
            tenant_id=tenant_id,
            channel=ch_str,
            recipient_destination=request.recipient_destination,
            recipient_user_id=request.recipient_user_id,
            recipient_employee_id=request.recipient_employee_id,
        )

        # 5. Evaluate Quiet Hours for Initial Scheduling
        now_utc = datetime.now(UTC)
        scheduled = request.scheduled_for or now_utc
        if scheduled.tzinfo is None:
            scheduled = scheduled.replace(tzinfo=UTC)

        effective_pref = PreferenceResolver.resolve(user_pref, tenant_default_pref)
        quiet_result = QuietHoursEvaluator.evaluate(
            preferences=effective_pref,
            priority=request.priority,
            evaluation_time_utc=scheduled,
        )

        if quiet_result.should_defer and quiet_result.next_eligible_dispatch_time:
            # Reschedule for end of quiet hours
            scheduled = quiet_result.next_eligible_dispatch_time

        # 6. Persist with Idempotency
        notification, _ = await self.repository.create_notification(
            tenant_id=tenant_id,
            event_type=request.event_type,
            channel=ch_str,
            recipient_destination=destination,
            subject=rendered_subject,
            body=rendered_body,
            recipient_user_id=request.recipient_user_id,
            recipient_employee_id=request.recipient_employee_id,
            template_id=template.id,
            template_key=template.template_key,
            payload_json=request.template_variables,
            priority=request.priority.value,
            idempotency_key=request.idempotency_key,
            scheduled_for=scheduled,
            related_entity_type=request.related_entity_type,
            related_entity_id=request.related_entity_id,
        )

        return NotificationResponse.model_validate(notification)

    async def create_batch(
        self,
        tenant_id: uuid.UUID,
        requests: list[NotificationCreateRequest],
        *,
        enforce_preferences: bool = True,
    ) -> list[NotificationResponse]:
        """Creates a batch of notifications transactionally."""
        results: list[NotificationResponse] = []
        for req in requests:
            res = await self.create_notification(tenant_id, req, enforce_preferences=enforce_preferences)
            results.append(res)
        return results
