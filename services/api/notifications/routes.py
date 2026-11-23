"""FastAPI routes for Phase 10: Device Push Token Registration & Management."""

import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.auth.dependencies import (
    AuthenticatedContext,
    get_authenticated_context,
    require_roles,
)
from services.api.auth.permissions import UserRole
from services.api.config import settings
from services.api.database import get_db
from services.api.employees.models import Employee
from services.api.notifications.crypto import (
    hash_push_token,
    mask_token_for_display,
)
from services.api.notifications.models import (
    DevicePushToken,
    NotificationTemplate,
)
from services.api.notifications.repository import NotificationRepository
from services.api.notifications.schemas import (
    ChannelConfigItem,
    ChannelListResponse,
    DevicePushTokenResponse,
    DeviceTokenRegisterRequest,
    NotificationChannel,
    NotificationListResponse,
    NotificationOverviewResponse,
    NotificationPreferenceResponse,
    NotificationResponse,
    NotificationTemplateResponse,
    PreferenceUpdateRequest,
    TemplateCreateRequest,
    TemplateUpdateRequest,
)

logger = logging.getLogger(__name__)

_HEX_64_REGEX = re.compile(r"^[a-fA-F0-9]{64}$")

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def _map_token_to_response(token_record: DevicePushToken) -> DevicePushTokenResponse:
    """Safely maps a DevicePushToken ORM model to response schema with masked token preview."""
    return DevicePushTokenResponse(
        id=token_record.id,
        tenant_id=token_record.tenant_id,
        user_id=token_record.user_id,
        employee_id=token_record.employee_id,
        platform=token_record.platform,
        token_preview=mask_token_for_display(token_record.token_hash),
        device_model=token_record.device_model,
        os_version=token_record.os_version,
        app_version=token_record.app_version,
        status=token_record.status,
        last_seen_at=token_record.last_seen_at,
        created_at=token_record.created_at,
    )


@router.post(
    "/devices",
    response_model=DevicePushTokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register or update mobile device FCM push token",
)
async def register_device_token(
    payload: DeviceTokenRegisterRequest,
    auth: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DevicePushTokenResponse:
    """Registers or rotates an FCM device push token for the authenticated user.

    Enforces:
    - Tenant and user identity derived strictly from authenticated backend context.
    - Token encrypted at rest using vetted authenticated cryptography (Fernet).
    - SHA-256 hash generated for deduplication and fast indexing.
    - Automatic token rotation without duplicate active entries.
    - Zero raw tokens returned in response or logged.
    """
    tenant_id = auth.tenant.id
    user_id = auth.user.id

    # Resolve optional Employee association
    emp_stmt = select(Employee.id).where(
        Employee.tenant_id == tenant_id,
        Employee.user_id == user_id,
    )
    employee_id = (await session.execute(emp_stmt)).scalar_one_or_none()

    repo = NotificationRepository(session)
    token_record = await repo.register_device_token(
        tenant_id=tenant_id,
        user_id=user_id,
        platform=payload.platform.value,
        raw_token=payload.token,
        employee_id=employee_id,
        device_model=payload.device_model,
        os_version=payload.os_version,
        app_version=payload.app_version,
    )

    await session.commit()
    logger.info(
        "Registered push device for user %s on platform %s (preview: %s)",
        user_id,
        payload.platform.value,
        mask_token_for_display(token_record.token_hash),
    )
    return _map_token_to_response(token_record)


@router.get(
    "/devices",
    response_model=list[DevicePushTokenResponse],
    status_code=status.HTTP_200_OK,
    summary="List active device push registrations for authenticated user",
)
async def list_user_device_tokens(
    auth: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[DevicePushTokenResponse]:
    """Retrieves all active device push tokens registered to the authenticated user.

    Raw tokens are never exposed; only masked preview strings are returned.
    """
    repo = NotificationRepository(session)
    tokens = await repo.get_active_tokens_for_user(
        tenant_id=auth.tenant.id,
        user_id=auth.user.id,
    )
    return [_map_token_to_response(t) for t in tokens]


@router.delete(
    "/devices/{token_hash}",
    status_code=status.HTTP_200_OK,
    summary="Revoke a registered device push token by hash",
)
async def revoke_device_token_by_hash(
    token_hash: str,
    auth: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Revokes an active device token belonging to the authenticated user."""
    clean_hash = token_hash.strip()
    if len(clean_hash) > 128:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token hash exceeds maximum permissible length of 128 characters",
        )

    stmt = (
        update(DevicePushToken)
        .where(
            DevicePushToken.tenant_id == auth.tenant.id,
            DevicePushToken.user_id == auth.user.id,
            DevicePushToken.token_hash == clean_hash,
            DevicePushToken.status == "ACTIVE",
        )
        .values(status="REVOKED")
    )
    result = await session.execute(stmt)
    await session.commit()
    cursor_res = cast(CursorResult[Any], result)

    if not cursor_res.rowcount:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active device registration token not found or already revoked",
        )

    logger.info("Revoked push device token %s for user %s", mask_token_for_display(token_hash), auth.user.id)
    return {"status": "revoked", "token_hash": token_hash.strip()}


@router.post(
    "/devices/revoke",
    status_code=status.HTTP_200_OK,
    summary="Revoke device token using raw token value",
)
async def revoke_device_token_by_value(
    body: dict[str, str],
    auth: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Revokes a device token by its raw token value, computing its hash internally."""
    raw_token = body.get("token", "").strip()
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing 'token' field in request body",
        )
    if len(raw_token) > 4096:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token exceeds maximum permissible length of 4096 characters",
        )

    thash = hash_push_token(raw_token)
    stmt = (
        update(DevicePushToken)
        .where(
            DevicePushToken.tenant_id == auth.tenant.id,
            DevicePushToken.user_id == auth.user.id,
            DevicePushToken.token_hash == thash,
            DevicePushToken.status == "ACTIVE",
        )
        .values(status="REVOKED")
    )
    result = await session.execute(stmt)
    await session.commit()
    cursor_res = cast(CursorResult[Any], result)

    if not cursor_res.rowcount:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active device registration token not found or already revoked",
        )

    logger.info("Revoked push token for user %s (hash preview: %s)", auth.user.id, mask_token_for_display(thash))
    return {"status": "revoked", "message": "Device token successfully revoked"}


# =============================================================================
# Milestone 10.5 Administration Console Endpoints
# =============================================================================


@router.get(
    "/overview",
    response_model=NotificationOverviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Notification delivery metrics and recent activity overview",
)
async def get_notification_overview(
    auth: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[Any, Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.HR))],
) -> NotificationOverviewResponse:
    """Returns aggregated notification delivery metrics, status breakdown, channel distribution,
    and recent activity for the tenant console.
    """
    repo = NotificationRepository(session)
    summary = await repo.get_delivery_summary(auth.tenant.id)
    recent_responses = [
        NotificationResponse.model_validate(n) for n in summary["recent_notifications"]
    ]
    return NotificationOverviewResponse(
        total_count=summary["total_count"],
        status_counts=summary["status_counts"],
        channel_counts=summary["channel_counts"],
        recent_notifications=recent_responses,
    )


@router.get(
    "/templates",
    response_model=list[NotificationTemplateResponse],
    status_code=status.HTTP_200_OK,
    summary="List available notification templates for the tenant",
)
async def list_templates(
    auth: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[Any, Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.HR))],
) -> list[NotificationTemplateResponse]:
    """Retrieves all system default templates and active tenant-specific overrides."""
    repo = NotificationRepository(session)
    templates = await repo.list_templates_for_tenant(auth.tenant.id)
    return [NotificationTemplateResponse.model_validate(t) for t in templates]


@router.post(
    "/templates",
    response_model=NotificationTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create or override a notification template for the tenant",
)
async def create_or_override_template(
    payload: TemplateCreateRequest,
    auth: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[Any, Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.HR))],
) -> NotificationTemplateResponse:
    """Creates or updates a tenant-owned notification template override."""
    repo = NotificationRepository(session)
    tpl = await repo.upsert_template(
        tenant_id=auth.tenant.id,
        template_key=payload.template_key,
        name=payload.name,
        event_type=payload.event_type,
        channel=payload.channel.value,
        body_template=payload.body_template,
        subject_template=payload.subject_template,
        description=payload.description,
        locale=payload.locale,
        is_active=payload.is_active,
        user_id=auth.user.id,
    )
    await session.commit()
    logger.info(
        "Tenant %s created/updated template override: key=%s, channel=%s",
        auth.tenant.id,
        payload.template_key,
        payload.channel.value,
    )
    return NotificationTemplateResponse.model_validate(tpl)


@router.put(
    "/templates/{template_id}",
    response_model=NotificationTemplateResponse,
    status_code=status.HTTP_200_OK,
    summary="Update an existing tenant notification template override by ID",
)
async def update_template_by_id(
    template_id: uuid.UUID,
    payload: TemplateUpdateRequest,
    auth: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[Any, Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.HR))],
) -> NotificationTemplateResponse:
    """Updates an existing tenant-owned notification template override.

    Enforces:
    - System default templates are strictly immutable (returns 403 Forbidden).
    - Cross-tenant template updates are forbidden (returns 404 Not Found if template belongs to another tenant).
    - Preserves safe template parameter syntax.
    """
    stmt = select(NotificationTemplate).where(NotificationTemplate.id == template_id)
    result = await session.execute(stmt)
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    if template.is_system or template.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System default templates are immutable. Create a tenant override via POST /templates instead.",
        )

    if template.tenant_id != auth.tenant.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    now = datetime.now(UTC)
    if payload.name is not None:
        template.name = payload.name
    if payload.description is not None:
        template.description = payload.description
    if payload.subject_template is not None:
        template.subject_template = payload.subject_template
    if payload.body_template is not None:
        template.body_template = payload.body_template
    if payload.is_active is not None:
        template.is_active = payload.is_active
    template.updated_by_user_id = auth.user.id
    template.updated_at = now

    await session.commit()
    await session.refresh(template)
    logger.info("Updated tenant template override %s for tenant %s", template_id, auth.tenant.id)
    return NotificationTemplateResponse.model_validate(template)



@router.get(
    "/preferences",
    response_model=NotificationPreferenceResponse,
    status_code=status.HTTP_200_OK,
    summary="Get tenant-wide default notification preferences",
)
async def get_tenant_preferences(
    auth: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[Any, Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.HR))],
) -> NotificationPreferenceResponse:
    """Retrieves tenant default notification preferences.
    If no preference record exists yet, initializes and returns default preferences.
    """
    repo = NotificationRepository(session)
    pref = await repo.get_tenant_default_preference(auth.tenant.id)
    if not pref:
        pref = await repo.upsert_preference(
            tenant_id=auth.tenant.id,
            user_id=None,
            is_push_enabled=True,
            is_email_enabled=True,
            is_sms_enabled=False,
            quiet_hours_enabled=False,
            quiet_hours_start="22:00",
            quiet_hours_end="07:00",
            timezone="UTC",
        )
        await session.commit()
    return NotificationPreferenceResponse.model_validate(pref)


@router.put(
    "/preferences",
    response_model=NotificationPreferenceResponse,
    status_code=status.HTTP_200_OK,
    summary="Update tenant-wide default notification preferences",
)
async def update_tenant_preferences(
    payload: PreferenceUpdateRequest,
    auth: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[Any, Depends(require_roles(UserRole.OWNER, UserRole.ADMIN))],
) -> NotificationPreferenceResponse:
    """Updates tenant default notification preferences (channel toggles, quiet hours, timezone)."""
    repo = NotificationRepository(session)
    current = await repo.get_tenant_default_preference(auth.tenant.id)

    push = (
        payload.is_push_enabled
        if payload.is_push_enabled is not None
        else (current.is_push_enabled if current else True)
    )
    email = (
        payload.is_email_enabled
        if payload.is_email_enabled is not None
        else (current.is_email_enabled if current else True)
    )
    sms = (
        payload.is_sms_enabled
        if payload.is_sms_enabled is not None
        else (current.is_sms_enabled if current else False)
    )
    qh_enabled = (
        payload.quiet_hours_enabled
        if payload.quiet_hours_enabled is not None
        else (current.quiet_hours_enabled if current else False)
    )
    qh_start = (
        payload.quiet_hours_start
        if payload.quiet_hours_start is not None
        else (current.quiet_hours_start if current else "22:00")
    )
    qh_end = (
        payload.quiet_hours_end
        if payload.quiet_hours_end is not None
        else (current.quiet_hours_end if current else "07:00")
    )
    tz = (
        payload.timezone
        if payload.timezone is not None
        else (current.timezone if current else "UTC")
    )
    cat_prefs = (
        payload.category_preferences
        if payload.category_preferences is not None
        else (current.category_preferences if current else {})
    )

    updated = await repo.upsert_preference(
        tenant_id=auth.tenant.id,
        user_id=None,
        is_push_enabled=push,
        is_email_enabled=email,
        is_sms_enabled=sms,
        quiet_hours_enabled=qh_enabled,
        quiet_hours_start=qh_start,
        quiet_hours_end=qh_end,
        timezone=tz,
        category_preferences=cat_prefs,
    )
    await session.commit()
    logger.info("Updated tenant %s default notification preferences", auth.tenant.id)
    return NotificationPreferenceResponse.model_validate(updated)


@router.get(
    "/channels",
    response_model=ChannelListResponse,
    status_code=status.HTTP_200_OK,
    summary="List notification delivery channels and runtime operational status",
)
async def list_channel_configurations(
    auth: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    _: Annotated[Any, Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.HR))],
) -> ChannelListResponse:
    """Returns available delivery channels and their runtime configuration status.

    Clearly indicates whether providers are live/configured, development mock fallbacks,
    or unconfigured/deferred, without exposing secrets.
    """
    fcm_configured = bool(
        settings.FCM_ENABLED
        and (settings.FIREBASE_CREDENTIALS_PATH or settings.FIREBASE_CREDENTIALS_JSON)
    )
    email_configured = bool(
        settings.EMAIL_BACKEND == "smtp" and settings.SMTP_HOST
    )

    channels = [
        ChannelConfigItem(
            channel=NotificationChannel.PUSH,
            is_enabled=True,
            provider_name=(
                "Firebase Cloud Messaging (FCM Gateway)"
                if fcm_configured
                else "MockPushProvider (Development Fallback)"
            ),
            status="CONFIGURED_UNVERIFIED" if fcm_configured else "MOCK",
            description=(
                "FCM gateway credentials configured. Note: Gateway handoff does not guarantee "
                "end-device delivery without registered active device tokens and confirmed client receipts."
                if fcm_configured
                else "Push alerts simulated locally; payloads logged without remote network calls."
            ),
            details={
                "fcm_enabled": settings.FCM_ENABLED,
                "provider_mode": "gateway_unverified" if fcm_configured else "mock_development",
                "credentials_present": bool(
                    settings.FIREBASE_CREDENTIALS_PATH or settings.FIREBASE_CREDENTIALS_JSON
                ),
            },
        ),
        ChannelConfigItem(
            channel=NotificationChannel.EMAIL,
            is_enabled=True,
            provider_name=(
                "SMTP Relay (Credentials Present - Unverified Gateway in Phase 10)"
                if email_configured
                else f"Mock / {settings.EMAIL_BACKEND.capitalize()} Provider (Development Preview)"
            ),
            status="CONFIGURED_UNVERIFIED" if email_configured else "MOCK",
            description=(
                "SMTP configuration detected, but production email provider integration is unverified "
                "in this milestone. Outbound notifications use local sandbox dispatch."
                if email_configured
                else "Email dispatch simulated via mock provider or console output. Production email provider integration deferred."
            ),
            details={
                "backend": settings.EMAIL_BACKEND,
                "from_address": settings.EMAIL_FROM_ADDRESS,
                "provider_mode": "smtp_unverified" if email_configured else f"mock_{settings.EMAIL_BACKEND}",
            },
        ),
        ChannelConfigItem(
            channel=NotificationChannel.SMS,
            is_enabled=False,
            provider_name="Deferred / Unconfigured",
            status="UNCONFIGURED",
            description="SMS delivery provider integration is deferred per Phase 10 roadmap and unconfigured in this milestone.",
            details={
                "provider_mode": "unconfigured",
                "deferred": True,
            },
        ),
    ]
    return ChannelListResponse(channels=channels)


@router.get(
    "/activity",
    response_model=NotificationListResponse,
    status_code=status.HTTP_200_OK,
    summary="Query paginated tenant notification activity log",
)
async def list_notification_activity(
    auth: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[Any, Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.HR))],
    status: str | None = None,
    channel: str | None = None,
    event_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> NotificationListResponse:
    """Returns a paginated list of outbound notifications for the tenant, with optional status,
    channel, and event-type filtering.
    """
    safe_limit = min(max(1, limit), 100)
    safe_offset = max(0, offset)

    repo = NotificationRepository(session)
    items, total = await repo.get_tenant_notifications(
        tenant_id=auth.tenant.id,
        channel=channel,
        status=status,
        event_type=event_type,
        offset=safe_offset,
        limit=safe_limit,
    )
    return NotificationListResponse(
        items=[NotificationResponse.model_validate(n) for n in items],
        total=total,
        offset=safe_offset,
        limit=safe_limit,
    )

