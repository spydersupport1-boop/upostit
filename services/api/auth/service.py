"""Authentication and tenant registration business logic service."""

import logging
import re
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.auth.models import RefreshToken, User
from services.api.auth.permissions import UserRole
from services.api.auth.schemas import (
    LoginRequest,
    RegisterTenantRequest,
    RegisterTenantResponse,
    TokenResponse,
    UserResponse,
)
from services.api.auth.security import (
    create_access_token,
    generate_secure_token,
    hash_password,
    hash_token,
    validate_password_strength,
    verify_password,
)
from services.api.config import settings
from services.api.database import set_tenant_context
from services.api.tenants.models import Tenant
from services.api.tenants.schemas import TenantResponse

logger = logging.getLogger(__name__)


def generate_tenant_slug(company_name: str) -> str:
    """Normalizes company name into a URL-friendly slug."""
    clean = re.sub(r"[^a-z0-9]+", "-", company_name.lower().strip()).strip("-")
    return clean if clean else "company"


async def register_tenant(
    session: AsyncSession,
    req: RegisterTenantRequest,
) -> RegisterTenantResponse:
    """
    Atomically registers a new company tenant and creates its initial owner user account.
    Enforces password complexity, email normalization, unique slug generation,
    and returns initial credentials with JWT access and refresh tokens.
    """
    # 1. Validate password strength
    validate_password_strength(req.password)

    # 2. Normalize inputs
    company_email = req.company_email.lower().strip()
    owner_email = req.owner_email.lower().strip()
    owner_name = req.owner_name.strip()
    company_name = req.company_name.strip()

    # 3. Generate unique slug
    base_slug = generate_tenant_slug(company_name)
    slug = base_slug
    suffix = 1

    while True:
        existing = await session.execute(select(Tenant.id).where(Tenant.slug == slug))
        if existing.scalar() is None:
            break
        slug = f"{base_slug}-{suffix}"
        suffix += 1

    # 4. Check if company_email is already used for an existing tenant
    existing_tenant = await session.execute(
        select(Tenant.id).where(Tenant.company_email == company_email)
    )
    if existing_tenant.scalar() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A company with this company email is already registered.",
        )

    # 5. Create Tenant and User atomically
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    family_id = uuid.uuid4()

    tenant = Tenant(
        id=tenant_id,
        name=company_name,
        slug=slug,
        company_email=company_email,
        country_code=req.country_code,
        timezone=req.timezone,
        status="active",
    )
    session.add(tenant)
    await session.flush()

    user = User(
        id=user_id,
        tenant_id=tenant_id,
        full_name=owner_name,
        email=owner_email,
        password_hash=hash_password(req.password),
        role=UserRole.OWNER.value,
        status="active",
    )
    session.add(user)
    await session.flush()

    # 6. Generate initial rotating refresh token
    raw_refresh_token = generate_secure_token()
    token_hash_val = hash_token(raw_refresh_token)
    expires_at = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    refresh_token_record = RefreshToken(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        token_hash=token_hash_val,
        family_id=family_id,
        expires_at=expires_at,
    )
    session.add(refresh_token_record)
    await session.commit()
    await session.refresh(tenant)
    await session.refresh(user)

    # 7. Generate JWT access token
    access_token = create_access_token(
        user_id=user.id,
        tenant_id=tenant.id,
        role=user.role,
    )

    tokens = TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    return RegisterTenantResponse(
        tenant=TenantResponse.model_validate(tenant),
        user=UserResponse.model_validate(user),
        tokens=tokens,
    )


async def login(
    session: AsyncSession,
    req: LoginRequest,
) -> tuple[TokenResponse, User, Tenant]:
    """
    Authenticates a user for a specific tenant slug.
    Prevents account enumeration through uniform generic authentication errors.
    """
    generic_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials or inactive account",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 1. Lookup tenant by slug
    clean_slug = req.tenant_slug.strip().lower()
    tenant_res = await session.execute(
        select(Tenant).where(Tenant.slug == clean_slug, Tenant.status == "active")
    )
    tenant = tenant_res.scalar_one_or_none()
    if not tenant:
        raise generic_error

    # 2. Set tenant isolation context
    await set_tenant_context(session, str(tenant.id))

    # 3. Lookup user within tenant scope
    normalized_email = req.email.strip().lower()
    user_res = await session.execute(
        select(User).where(
            User.tenant_id == tenant.id,
            User.email == normalized_email,
            User.status == "active",
        )
    )
    user = user_res.scalar_one_or_none()
    if not user:
        raise generic_error

    # 4. Verify password with Argon2id
    if not verify_password(req.password, user.password_hash):
        raise generic_error

    # 5. Update last login timestamp
    user.last_login_at = datetime.now(UTC)

    # 6. Issue new refresh token family
    family_id = uuid.uuid4()
    raw_refresh_token = generate_secure_token()
    token_hash_val = hash_token(raw_refresh_token)
    expires_at = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    refresh_record = RefreshToken(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        user_id=user.id,
        token_hash=token_hash_val,
        family_id=family_id,
        expires_at=expires_at,
    )
    session.add(refresh_record)
    await session.commit()

    # 7. Issue access token
    access_token = create_access_token(
        user_id=user.id,
        tenant_id=tenant.id,
        role=user.role,
    )

    tokens = TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    return tokens, user, tenant


async def refresh_access_token(
    session: AsyncSession,
    raw_refresh_token: str,
) -> TokenResponse:
    """
    Validates a refresh token, rotates it, detects token reuse,
    revokes compromised token families, and issues a new access/refresh pair.
    """
    if not raw_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_hash_val = hash_token(raw_refresh_token)

    # Lookup token without tenant filter first to detect compromise
    res = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash_val)
    )
    token = res.scalar_one_or_none()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # REUSE DETECTION: If this token was already revoked, a compromised token is being reused!
    if token.revoked_at is not None:
        logger.warning(
            "Refresh token reuse detected for family %s! Revoking entire family session.",
            token.family_id,
        )
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == token.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token reuse detected. All sessions in this family have been revoked.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check expiration
    now = datetime.now(UTC)
    if token.expires_at < now:
        token.revoked_at = now
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Set tenant context
    await set_tenant_context(session, str(token.tenant_id))

    # Verify user and tenant are active
    user_res = await session.execute(
        select(User).where(
            User.id == token.user_id,
            User.tenant_id == token.tenant_id,
            User.status == "active",
        )
    )
    user = user_res.scalar_one_or_none()

    tenant_res = await session.execute(
        select(Tenant).where(Tenant.id == token.tenant_id, Tenant.status == "active")
    )
    tenant = tenant_res.scalar_one_or_none()

    if not user or not tenant:
        token.revoked_at = now
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User or tenant account is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # TOKEN ROTATION
    token.revoked_at = now
    token.last_used_at = now

    new_raw_token = generate_secure_token()
    new_token_hash = hash_token(new_raw_token)
    new_expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    new_token_id = uuid.uuid4()

    new_token_record = RefreshToken(
        id=new_token_id,
        tenant_id=token.tenant_id,
        user_id=token.user_id,
        token_hash=new_token_hash,
        family_id=token.family_id,  # Preserve family ID across rotations
        expires_at=new_expires_at,
    )
    session.add(new_token_record)
    await session.flush()  # Ensure new token is inserted before referencing its ID
    token.replaced_by_token_id = new_token_id

    await session.commit()

    # Issue new access token
    new_access_token = create_access_token(
        user_id=user.id,
        tenant_id=tenant.id,
        role=user.role,
    )

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_raw_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


async def logout(
    session: AsyncSession,
    raw_refresh_token: str | None,
) -> None:
    """Revokes the active refresh token session."""
    if not raw_refresh_token:
        return

    token_hash_val = hash_token(raw_refresh_token)
    res = await session.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash_val,
            RefreshToken.revoked_at.is_(None),
        )
    )
    token = res.scalar_one_or_none()
    if token:
        token.revoked_at = datetime.now(UTC)
        await session.commit()


async def logout_all(
    session: AsyncSession,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> int:
    """Revokes all active refresh token sessions for the given user."""
    await set_tenant_context(session, str(tenant_id))
    result = await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.tenant_id == tenant_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )
    await session.commit()
    return int(getattr(result, "rowcount", 0) or 0)


async def request_password_reset(
    session: AsyncSession,
    tenant_slug: str,
    email: str,
) -> None:
    """
    Initiates a secure password reset workflow and emits a transactional notification event.
    Prevents account enumeration by always completing without throwing 404/401 errors to callers.
    Guarantees zero-leak logging of sensitive reset tokens.
    """
    clean_slug = tenant_slug.strip().lower()
    clean_email = email.strip().lower()

    # 1. Lookup tenant
    tenant_res = await session.execute(
        select(Tenant).where(Tenant.slug == clean_slug, Tenant.status == "active")
    )
    tenant = tenant_res.scalar_one_or_none()
    if not tenant:
        return

    # 2. Lookup user
    user_res = await session.execute(
        select(User).where(
            User.tenant_id == tenant.id,
            User.email == clean_email,
            User.status == "active",
        )
    )
    user = user_res.scalar_one_or_none()
    if not user:
        return

    # 3. Generate secure reset token
    raw_token = generate_secure_token()
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={raw_token}"

    # 4. Emit Phase 10 PasswordResetRequestedEvent (non-blocking)
    try:
        from services.api.notifications import (
            PasswordResetRequestedEvent,
            dispatch_domain_event,
        )

        await dispatch_domain_event(
            session=session,
            event=PasswordResetRequestedEvent(
                tenant_id=tenant.id,
                user_id=user.id,
                user_email=user.email,
                user_name=user.full_name,
                company_name=tenant.name,
                reset_url=reset_url,
                expires_minutes=30,
                actor_user_id=user.id,
            ),
        )
    except Exception as exc:
        logger.warning("Failed to dispatch password reset notification: %s", exc)
