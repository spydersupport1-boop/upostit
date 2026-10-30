"""FastAPI authentication, tenant context injection, and RBAC authorization dependencies."""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.auth.models import User
from services.api.auth.permissions import Permission, UserRole, has_permission
from services.api.auth.security import decode_access_token
from services.api.database import get_db, set_tenant_context
from services.api.tenants.models import Tenant

security_scheme = HTTPBearer(auto_error=False)


class TokenPayload(BaseModel):
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: str
    jti: str


class AuthenticatedContext(BaseModel):
    user: User
    tenant: Tenant

    model_config = {"arbitrary_types_allowed": True}


async def get_token_payload(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(security_scheme)],
) -> TokenPayload:
    """Extracts and validates the JWT Bearer token from the Authorization header."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    claims = decode_access_token(credentials.credentials)

    sub = claims.get("sub")
    tenant_id = claims.get("tenant_id")
    role = claims.get("role")
    jti = claims.get("jti", "")

    if not sub or not tenant_id or not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload is missing required authorization claims",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_uuid = uuid.UUID(sub)
        tenant_uuid = uuid.UUID(tenant_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed UUID in token claims",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenPayload(
        user_id=user_uuid,
        tenant_id=tenant_uuid,
        role=role,
        jti=jti,
    )


async def get_authenticated_context(
    payload: Annotated[TokenPayload, Depends(get_token_payload)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AuthenticatedContext:
    """
    Validates token context, sets the transaction-local PostgreSQL tenant context,
    and loads active User and Tenant models.
    """
    # 1. Inject transaction-scoped tenant identity for PostgreSQL Row-Level Security
    await set_tenant_context(session, str(payload.tenant_id))

    # 2. Fetch User within tenant scope
    user_res = await session.execute(
        select(User).where(
            User.id == payload.user_id,
            User.tenant_id == payload.tenant_id,
            User.status == "active",
        )
    )
    user = user_res.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or deactivated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. Fetch Tenant
    tenant_res = await session.execute(
        select(Tenant).where(
            Tenant.id == payload.tenant_id,
            Tenant.status == "active",
        )
    )
    tenant = tenant_res.scalar_one_or_none()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Company tenant account not found or suspended",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthenticatedContext(user=user, tenant=tenant)


async def get_current_user(
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
) -> User:
    """Returns the authenticated active user."""
    return context.user


async def get_current_tenant(
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
) -> Tenant:
    """Returns the authenticated active tenant."""
    return context.tenant


def require_roles(*allowed_roles: UserRole):
    """Dependency factory enforcing role membership."""
    allowed_values = {role.value for role in allowed_roles}

    async def role_checker(
        user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if user.role not in allowed_values:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this operation",
            )
        return user

    return role_checker


def require_permission(permission: Permission):
    """Dependency factory enforcing specific functional permission."""

    async def permission_checker(
        user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if not has_permission(user.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: missing '{permission.value}' capability",
            )
        return user

    return permission_checker
