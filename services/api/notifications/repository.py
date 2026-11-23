"""Repository layer for Phase 10 Notifications, Templates, Preferences, and Device Tokens."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.notifications.crypto import (
    encrypt_push_token as encrypt_token_at_rest,
)
from services.api.notifications.crypto import (
    hash_push_token,
)
from services.api.notifications.default_templates import (
    SYSTEM_DEFAULT_TEMPLATES,
    get_default_system_template,
)
from services.api.notifications.exceptions import InvalidStateTransitionError
from services.api.notifications.models import (
    DevicePushToken,
    Notification,
    NotificationPreference,
    NotificationTemplate,
)
from services.api.notifications.schemas import (
    NotificationChannel,
    NotificationPriority,
    NotificationStatus,
)


class NotificationRepository:
    """Async repository for database operations on notification domain entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # =========================================================================
    # 1. Notification Persistence & Lifecycle
    # =========================================================================

    async def create_notification(
        self,
        tenant_id: uuid.UUID,
        event_type: str,
        channel: str,
        recipient_destination: str,
        body: str,
        subject: str | None = None,
        recipient_user_id: uuid.UUID | None = None,
        recipient_employee_id: uuid.UUID | None = None,
        template_id: uuid.UUID | None = None,
        template_key: str | None = None,
        payload_json: dict[str, Any] | None = None,
        priority: str = "NORMAL",
        idempotency_key: str | None = None,
        scheduled_for: datetime | None = None,
        related_entity_type: str | None = None,
        related_entity_id: uuid.UUID | None = None,
        max_attempts: int = 3,
    ) -> tuple[Notification, bool]:
        """Creates a notification record.

        Enforces idempotency: if a record exists for (tenant_id, idempotency_key),
        returns (existing_notification, False). Otherwise returns (new_notification, True).
        """
        now = datetime.now(UTC)
        scheduled = scheduled_for or now
        if scheduled.tzinfo is None:
            scheduled = scheduled.replace(tzinfo=UTC)

        # Check idempotency
        if idempotency_key:
            stmt = select(Notification).where(
                Notification.tenant_id == tenant_id,
                Notification.idempotency_key == idempotency_key,
            )
            result = await self.session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                return existing, False

        notification = Notification(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            recipient_user_id=recipient_user_id,
            recipient_employee_id=recipient_employee_id,
            event_type=event_type,
            channel=channel.upper(),
            template_id=template_id,
            template_key=template_key,
            recipient_destination=recipient_destination,
            subject=subject,
            body=body,
            payload_json=payload_json or {},
            status=NotificationStatus.PENDING.value,
            priority=priority.upper(),
            scheduled_for=scheduled,
            attempt_count=0,
            max_attempts=max_attempts,
            idempotency_key=idempotency_key,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
            created_at=now,
            updated_at=now,
        )

        self.session.add(notification)
        await self.session.flush()
        await self.session.refresh(notification)
        return notification, True

    async def get_notification(
        self,
        notification_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> Notification | None:
        """Retrieves a notification by ID enforcing tenant isolation."""
        stmt = select(Notification).where(
            Notification.id == notification_id,
            Notification.tenant_id == tenant_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_pending_notifications(
        self,
        tenant_id: uuid.UUID | None = None,
        now: datetime | None = None,
        limit: int = 50,
    ) -> Sequence[Notification]:
        """Queries pending notifications eligible for dispatch ordered by priority and schedule."""
        eval_now = now or datetime.now(UTC)
        if eval_now.tzinfo is None:
            eval_now = eval_now.replace(tzinfo=UTC)

        priority_order = case(
            (Notification.priority == NotificationPriority.URGENT.value, 1),
            (Notification.priority == NotificationPriority.HIGH.value, 2),
            (Notification.priority == NotificationPriority.NORMAL.value, 3),
            else_=4,
        )

        query = select(Notification).where(
            Notification.status.in_([
                NotificationStatus.PENDING.value,
                NotificationStatus.RETRY_SCHEDULED.value,
            ]),
            Notification.scheduled_for <= eval_now,
        )

        if tenant_id:
            query = query.where(Notification.tenant_id == tenant_id)

        query = query.order_by(priority_order, Notification.scheduled_for.asc()).limit(limit)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def claim_for_processing(
        self,
        notification_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> Notification | None:
        """Atomically transitions notification status to PROCESSING to prevent concurrent dispatch."""
        now = datetime.now(UTC)
        stmt = (
            update(Notification)
            .where(
                Notification.id == notification_id,
                Notification.tenant_id == tenant_id,
                Notification.status.in_([
                    NotificationStatus.PENDING.value,
                    NotificationStatus.RETRY_SCHEDULED.value,
                ]),
            )
            .values(
                status=NotificationStatus.PROCESSING.value,
                updated_at=now,
            )
            .returning(Notification)
        )
        result = await self.session.execute(stmt)
        updated = result.scalar_one_or_none()
        if updated:
            await self.session.flush()
        return updated

    async def record_success(
        self,
        notification_id: uuid.UUID,
        tenant_id: uuid.UUID,
        provider_name: str,
        provider_message_id: str,
        provider_response: str | None = None,
    ) -> Notification:
        """Records provider acceptance, transitioning status to SENT."""
        now = datetime.now(UTC)
        stmt = (
            update(Notification)
            .where(
                Notification.id == notification_id,
                Notification.tenant_id == tenant_id,
            )
            .values(
                status=NotificationStatus.SENT.value,
                sent_at=now,
                provider_name=provider_name,
                provider_message_id=provider_message_id,
                provider_response=provider_response,
                error_message=None,
                updated_at=now,
            )
            .returning(Notification)
        )
        result = await self.session.execute(stmt)
        updated = result.scalar_one_or_none()
        if not updated:
            raise InvalidStateTransitionError("UNKNOWN", NotificationStatus.SENT.value)
        await self.session.flush()
        return updated

    async def record_retryable_failure(
        self,
        notification_id: uuid.UUID,
        tenant_id: uuid.UUID,
        error_message: str,
        next_retry_at: datetime,
        provider_name: str | None = None,
        provider_response: str | None = None,
    ) -> Notification:
        """Increments attempt count and schedules a future retry."""
        now = datetime.now(UTC)
        if next_retry_at.tzinfo is None:
            next_retry_at = next_retry_at.replace(tzinfo=UTC)

        stmt = (
            update(Notification)
            .where(
                Notification.id == notification_id,
                Notification.tenant_id == tenant_id,
            )
            .values(
                status=NotificationStatus.RETRY_SCHEDULED.value,
                attempt_count=Notification.attempt_count + 1,
                next_retry_at=next_retry_at,
                scheduled_for=next_retry_at,
                error_message=error_message,
                provider_name=provider_name,
                provider_response=provider_response,
                updated_at=now,
            )
            .returning(Notification)
        )
        result = await self.session.execute(stmt)
        updated = result.scalar_one_or_none()
        if not updated:
            raise InvalidStateTransitionError("UNKNOWN", NotificationStatus.RETRY_SCHEDULED.value)
        await self.session.flush()
        return updated

    async def record_permanent_failure(
        self,
        notification_id: uuid.UUID,
        tenant_id: uuid.UUID,
        error_message: str,
        provider_name: str | None = None,
        provider_response: str | None = None,
    ) -> Notification:
        """Marks notification as terminally FAILED."""
        now = datetime.now(UTC)
        stmt = (
            update(Notification)
            .where(
                Notification.id == notification_id,
                Notification.tenant_id == tenant_id,
            )
            .values(
                status=NotificationStatus.FAILED.value,
                attempt_count=Notification.attempt_count + 1,
                failed_at=now,
                error_message=error_message,
                provider_name=provider_name,
                provider_response=provider_response,
                updated_at=now,
            )
            .returning(Notification)
        )
        result = await self.session.execute(stmt)
        updated = result.scalar_one_or_none()
        if not updated:
            raise InvalidStateTransitionError("UNKNOWN", NotificationStatus.FAILED.value)
        await self.session.flush()
        return updated

    async def defer_for_quiet_hours(
        self,
        notification_id: uuid.UUID,
        tenant_id: uuid.UUID,
        next_eligible_at: datetime,
        reason: str = "Deferred due to quiet hours",
    ) -> Notification:
        """Transitions claimed notification back to RETRY_SCHEDULED for after quiet hours."""
        now = datetime.now(UTC)
        if next_eligible_at.tzinfo is None:
            next_eligible_at = next_eligible_at.replace(tzinfo=UTC)

        stmt = (
            update(Notification)
            .where(
                Notification.id == notification_id,
                Notification.tenant_id == tenant_id,
            )
            .values(
                status=NotificationStatus.RETRY_SCHEDULED.value,
                scheduled_for=next_eligible_at,
                next_retry_at=next_eligible_at,
                error_message=reason,
                updated_at=now,
            )
            .returning(Notification)
        )
        result = await self.session.execute(stmt)
        updated = result.scalar_one_or_none()
        if not updated:
            raise InvalidStateTransitionError("UNKNOWN", NotificationStatus.RETRY_SCHEDULED.value)
        await self.session.flush()
        return updated

    async def cancel_notification(
        self,
        notification_id: uuid.UUID,
        tenant_id: uuid.UUID,
        reason: str = "Cancelled by user or system",
    ) -> Notification:
        """Cancels an un-dispatched notification."""
        now = datetime.now(UTC)
        stmt = (
            update(Notification)
            .where(
                Notification.id == notification_id,
                Notification.tenant_id == tenant_id,
                Notification.status.in_([
                    NotificationStatus.PENDING.value,
                    NotificationStatus.RETRY_SCHEDULED.value,
                ]),
            )
            .values(
                status=NotificationStatus.CANCELLED.value,
                error_message=reason,
                updated_at=now,
            )
            .returning(Notification)
        )
        result = await self.session.execute(stmt)
        updated = result.scalar_one_or_none()
        if not updated:
            raise InvalidStateTransitionError("NON_CANCELLABLE", NotificationStatus.CANCELLED.value)
        await self.session.flush()
        return updated

    async def get_notifications_by_recipient(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        employee_id: uuid.UUID | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[Sequence[Notification], int]:
        """Queries notifications for a specific user or employee with pagination."""
        query = select(Notification).where(Notification.tenant_id == tenant_id)
        if user_id:
            query = query.where(Notification.recipient_user_id == user_id)
        if employee_id:
            query = query.where(Notification.recipient_employee_id == employee_id)

        count_stmt = select(func.count()).select_from(query.subquery())
        total = (await self.session.execute(count_stmt)).scalar() or 0

        paged_query = query.order_by(Notification.created_at.desc()).offset(offset).limit(limit)
        items = (await self.session.execute(paged_query)).scalars().all()
        return items, total

    async def get_tenant_notifications(
        self,
        tenant_id: uuid.UUID,
        channel: str | None = None,
        status: str | None = None,
        event_type: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[Sequence[Notification], int]:
        """Queries tenant notifications with optional channel/status filters and pagination."""
        query = select(Notification).where(Notification.tenant_id == tenant_id)
        if channel:
            query = query.where(Notification.channel == channel.upper())
        if status:
            query = query.where(Notification.status == status.upper())
        if event_type:
            query = query.where(Notification.event_type == event_type)

        count_stmt = select(func.count()).select_from(query.subquery())
        total = (await self.session.execute(count_stmt)).scalar() or 0

        paged_query = query.order_by(Notification.created_at.desc()).offset(offset).limit(limit)
        items = (await self.session.execute(paged_query)).scalars().all()
        return items, total

    async def get_delivery_summary(
        self,
        tenant_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Aggregates notification counts by status and channel, plus recent activity."""
        # Status counts
        status_stmt = (
            select(Notification.status, func.count(Notification.id))
            .where(Notification.tenant_id == tenant_id)
            .group_by(Notification.status)
        )
        status_rows = (await self.session.execute(status_stmt)).all()
        status_counts = {s.value.lower(): 0 for s in NotificationStatus}
        total = 0
        for s_val, count in status_rows:
            status_counts[str(s_val).lower()] = int(count)
            total += int(count)

        # Channel counts
        channel_stmt = (
            select(Notification.channel, func.count(Notification.id))
            .where(Notification.tenant_id == tenant_id)
            .group_by(Notification.channel)
        )
        channel_rows = (await self.session.execute(channel_stmt)).all()
        channel_counts = {c.value.lower(): 0 for c in NotificationChannel}
        for c_val, count in channel_rows:
            channel_counts[str(c_val).lower()] = int(count)

        # Recent notifications (latest 10)
        recent_stmt = (
            select(Notification)
            .where(Notification.tenant_id == tenant_id)
            .order_by(Notification.created_at.desc())
            .limit(10)
        )
        recent_notifications = list((await self.session.execute(recent_stmt)).scalars().all())

        return {
            "total_count": total,
            "status_counts": status_counts,
            "channel_counts": channel_counts,
            "recent_notifications": recent_notifications,
        }

    # =========================================================================
    # 2. Notification Templates
    # =========================================================================

    async def list_templates_for_tenant(
        self,
        tenant_id: uuid.UUID,
        locale: str = "en",
    ) -> Sequence[NotificationTemplate]:
        """Retrieves all templates available to the tenant, including canonical system defaults and tenant overrides."""
        # 1. Tenant custom / override templates
        tenant_stmt = (
            select(NotificationTemplate)
            .where(
                NotificationTemplate.tenant_id == tenant_id,
            )
            .order_by(NotificationTemplate.template_key.asc(), NotificationTemplate.channel.asc())
        )
        tenant_templates = list((await self.session.execute(tenant_stmt)).scalars().all())

        # 2. DB-seeded system templates
        db_system_stmt = (
            select(NotificationTemplate)
            .where(
                NotificationTemplate.tenant_id.is_(None),
                NotificationTemplate.is_system == True,  # noqa: E712
            )
            .order_by(NotificationTemplate.template_key.asc(), NotificationTemplate.channel.asc())
        )
        db_system_templates = list((await self.session.execute(db_system_stmt)).scalars().all())
        db_system_keys = {(t.template_key, t.channel, t.locale) for t in db_system_templates}

        # 3. Canonical in-memory defaults
        built_in_templates: list[NotificationTemplate] = []
        for d in SYSTEM_DEFAULT_TEMPLATES:
            k = (d["template_key"], d["channel"], d.get("locale", "en"))
            if k not in db_system_keys:
                tpl = get_default_system_template(d["template_key"], d["channel"], d.get("locale", "en"))
                if tpl:
                    built_in_templates.append(tpl)

        all_system = db_system_templates + built_in_templates

        # Combine: tenant templates first, plus system defaults
        result: list[NotificationTemplate] = list(tenant_templates)
        for s in all_system:
            result.append(s)

        return sorted(result, key=lambda t: (t.template_key, t.channel, not t.is_system))

    async def upsert_template(
        self,
        tenant_id: uuid.UUID,
        template_key: str,
        name: str,
        event_type: str,
        channel: str,
        body_template: str,
        subject_template: str | None = None,
        description: str | None = None,
        locale: str = "en",
        is_active: bool = True,
        user_id: uuid.UUID | None = None,
    ) -> NotificationTemplate:
        """Creates or updates a tenant-specific notification template override."""
        now = datetime.now(UTC)
        ch = channel.upper()
        loc = locale.lower()

        # Check for existing tenant template
        stmt = select(NotificationTemplate).where(
            NotificationTemplate.tenant_id == tenant_id,
            NotificationTemplate.template_key == template_key,
            NotificationTemplate.channel == ch,
            NotificationTemplate.locale == loc,
        )
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing:
            existing.name = name
            existing.event_type = event_type
            existing.body_template = body_template
            existing.subject_template = subject_template
            if description is not None:
                existing.description = description
            existing.is_active = is_active
            existing.updated_by_user_id = user_id
            existing.updated_at = now
            await self.session.flush()
            await self.session.refresh(existing)
            return existing

        template = NotificationTemplate(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            template_key=template_key,
            name=name,
            description=description,
            event_type=event_type,
            channel=ch,
            subject_template=subject_template,
            body_template=body_template,
            locale=loc,
            is_active=is_active,
            is_system=False,
            created_by_user_id=user_id,
            created_at=now,
            updated_at=now,
        )
        self.session.add(template)
        await self.session.flush()
        await self.session.refresh(template)
        return template

    async def get_template(
        self,
        tenant_id: uuid.UUID,
        template_key: str,
        channel: str,
        locale: str = "en",
    ) -> NotificationTemplate | None:
        """Retrieves a template, checking tenant override first, then system default."""
        ch = channel.upper()
        # 1. Check for tenant-specific active override
        tenant_stmt = select(NotificationTemplate).where(
            NotificationTemplate.tenant_id == tenant_id,
            NotificationTemplate.template_key == template_key,
            NotificationTemplate.channel == ch,
            NotificationTemplate.locale == locale,
            NotificationTemplate.is_active == True,  # noqa: E712
        )
        tenant_override = (await self.session.execute(tenant_stmt)).scalar_one_or_none()
        if tenant_override:
            return tenant_override

        # 2. Check for system-wide template
        system_stmt = select(NotificationTemplate).where(
            NotificationTemplate.tenant_id.is_(None),
            NotificationTemplate.is_system == True,  # noqa: E712
            NotificationTemplate.template_key == template_key,
            NotificationTemplate.channel == ch,
            NotificationTemplate.locale == locale,
            NotificationTemplate.is_active == True,  # noqa: E712
        )
        system_tpl = (await self.session.execute(system_stmt)).scalar_one_or_none()
        if system_tpl:
            return system_tpl

        # 3. Check for canonical built-in system default template
        built_in = get_default_system_template(template_key, ch, locale)
        if built_in:
            return built_in

        return None

    async def create_template(
        self,
        template_key: str,
        name: str,
        event_type: str,
        channel: str,
        body_template: str,
        subject_template: str | None = None,
        tenant_id: uuid.UUID | None = None,
        is_system: bool = False,
        description: str | None = None,
        locale: str = "en",
        created_by_user_id: uuid.UUID | None = None,
    ) -> NotificationTemplate:
        """Creates a system or tenant template."""
        now = datetime.now(UTC)
        template = NotificationTemplate(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            template_key=template_key,
            name=name,
            description=description,
            event_type=event_type,
            channel=channel.upper(),
            subject_template=subject_template,
            body_template=body_template,
            locale=locale,
            is_active=True,
            is_system=is_system,
            created_by_user_id=created_by_user_id,
            created_at=now,
            updated_at=now,
        )
        self.session.add(template)
        await self.session.flush()
        await self.session.refresh(template)
        return template

    # =========================================================================
    # 3. Notification Preferences
    # =========================================================================

    async def get_user_preference(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> NotificationPreference | None:
        """Retrieves user-level preferences."""
        stmt = select(NotificationPreference).where(
            NotificationPreference.tenant_id == tenant_id,
            NotificationPreference.user_id == user_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_tenant_default_preference(
        self,
        tenant_id: uuid.UUID,
    ) -> NotificationPreference | None:
        """Retrieves tenant-wide default preferences."""
        stmt = select(NotificationPreference).where(
            NotificationPreference.tenant_id == tenant_id,
            NotificationPreference.user_id.is_(None),
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def upsert_preference(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID | None,
        is_push_enabled: bool = True,
        is_email_enabled: bool = True,
        is_sms_enabled: bool = False,
        quiet_hours_enabled: bool = False,
        quiet_hours_start: str | None = None,
        quiet_hours_end: str | None = None,
        timezone: str = "UTC",
        category_preferences: dict[str, Any] | None = None,
    ) -> NotificationPreference:
        """Upserts a user or tenant default preference record."""
        now = datetime.now(UTC)
        if user_id:
            existing = await self.get_user_preference(tenant_id, user_id)
        else:
            existing = await self.get_tenant_default_preference(tenant_id)

        if existing:
            existing.is_push_enabled = is_push_enabled
            existing.is_email_enabled = is_email_enabled
            existing.is_sms_enabled = is_sms_enabled
            existing.quiet_hours_enabled = quiet_hours_enabled
            existing.quiet_hours_start = quiet_hours_start
            existing.quiet_hours_end = quiet_hours_end
            existing.timezone = timezone
            if category_preferences is not None:
                existing.category_preferences = category_preferences
            existing.updated_at = now
            await self.session.flush()
            await self.session.refresh(existing)
            return existing

        pref = NotificationPreference(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            is_push_enabled=is_push_enabled,
            is_email_enabled=is_email_enabled,
            is_sms_enabled=is_sms_enabled,
            quiet_hours_enabled=quiet_hours_enabled,
            quiet_hours_start=quiet_hours_start,
            quiet_hours_end=quiet_hours_end,
            timezone=timezone,
            category_preferences=category_preferences or {},
            created_at=now,
            updated_at=now,
        )
        self.session.add(pref)
        await self.session.flush()
        await self.session.refresh(pref)
        return pref

    # =========================================================================
    # 4. Device Push Tokens
    # =========================================================================

    async def get_active_tokens_for_user(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Sequence[DevicePushToken]:
        """Queries active push tokens registered to a user."""
        stmt = select(DevicePushToken).where(
            DevicePushToken.tenant_id == tenant_id,
            DevicePushToken.user_id == user_id,
            DevicePushToken.status == "ACTIVE",
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def register_device_token(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        platform: str,
        raw_token: str,
        employee_id: uuid.UUID | None = None,
        device_id: uuid.UUID | None = None,
        device_model: str | None = None,
        os_version: str | None = None,
        app_version: str | None = None,
    ) -> DevicePushToken:
        """Registers an FCM push token, rotating existing active tokens for the hash if needed."""
        now = datetime.now(UTC)
        thash = hash_push_token(raw_token)
        encrypted = encrypt_token_at_rest(raw_token)

        # Check if an active record already exists with this hash
        stmt = select(DevicePushToken).where(
            DevicePushToken.token_hash == thash,
            DevicePushToken.status == "ACTIVE",
        )
        existing = (await self.session.execute(stmt)).scalar_one_or_none()

        if existing:
            # Update ownership & last seen
            existing.tenant_id = tenant_id
            existing.user_id = user_id
            existing.employee_id = employee_id
            existing.device_id = device_id
            existing.token = encrypted
            existing.device_model = device_model
            existing.os_version = os_version
            existing.app_version = app_version
            existing.last_seen_at = now
            existing.updated_at = now
            await self.session.flush()
            await self.session.refresh(existing)
            return existing

        token_record = DevicePushToken(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            employee_id=employee_id,
            device_id=device_id,
            platform=platform.upper(),
            token=encrypted,
            token_hash=thash,
            device_model=device_model,
            os_version=os_version,
            app_version=app_version,
            status="ACTIVE",
            last_seen_at=now,
            created_at=now,
            updated_at=now,
        )
        self.session.add(token_record)
        await self.session.flush()
        await self.session.refresh(token_record)
        return token_record

    async def revoke_device_token(
        self,
        tenant_id: uuid.UUID,
        raw_token: str,
    ) -> bool:
        """Revokes an active device token by raw token value."""
        now = datetime.now(UTC)
        thash = hash_push_token(raw_token)
        stmt = (
            update(DevicePushToken)
            .where(
                DevicePushToken.tenant_id == tenant_id,
                DevicePushToken.token_hash == thash,
                DevicePushToken.status == "ACTIVE",
            )
            .values(status="REVOKED", updated_at=now)
            .returning(DevicePushToken.id)
        )
        result = await self.session.execute(stmt)
        revoked_id = result.scalar_one_or_none()
        await self.session.flush()
        return revoked_id is not None
