"""Authentication and user session routes under /api/v1/auth."""

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.auth.dependencies import (
    AuthenticatedContext,
    get_authenticated_context,
)
from services.api.auth.schemas import (
    LoginRequest,
    RefreshTokenRequest,
    RegisterTenantRequest,
    RegisterTenantResponse,
    TokenResponse,
    UserProfileResponse,
    UserResponse,
)
from services.api.auth.service import (
    login as auth_login,
)
from services.api.auth.service import (
    logout as auth_logout,
)
from services.api.auth.service import (
    logout_all as auth_logout_all,
)
from services.api.auth.service import (
    refresh_access_token,
)
from services.api.auth.service import (
    register_tenant as auth_register_tenant,
)
from services.api.config import settings
from services.api.database import get_db
from services.api.employees.invitation_schemas import (
    ActivateAccountRequest,
    ActivateAccountResponse,
    ValidateInvitationResponse,
)
from services.api.employees.invitation_service import (
    activate_account as service_activate_account,
)
from services.api.employees.invitation_service import (
    validate_public_invitation_token,
)
from services.api.tenants.schemas import TenantResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _is_cookie_secure() -> bool:
    if settings.ENVIRONMENT == "production":
        return True
    return settings.COOKIE_SECURE


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """Sets a secure HTTP-only refresh token cookie for web clients."""
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=_is_cookie_secure(),
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        domain=settings.COOKIE_DOMAIN,
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Clears the refresh token cookie upon logout."""
    response.delete_cookie(
        key="refresh_token",
        path="/api/v1/auth",
        domain=settings.COOKIE_DOMAIN,
        httponly=True,
        secure=_is_cookie_secure(),
        samesite=settings.COOKIE_SAMESITE,
    )


@router.post(
    "/register-tenant",
    response_model=RegisterTenantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new company and initial owner account",
)
async def register_tenant(
    req: RegisterTenantRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> RegisterTenantResponse:
    result = await auth_register_tenant(session, req)
    _set_refresh_cookie(response, result.tokens.refresh_token)
    return result


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate a user and issue access and refresh tokens",
)
async def login(
    req: LoginRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    tokens, user, tenant = await auth_login(session, req)
    _set_refresh_cookie(response, tokens.refresh_token)
    return tokens


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate refresh token and issue a new access token",
)
async def refresh_token(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db)],
    body: RefreshTokenRequest | None = None,
    cookie_token: Annotated[str | None, Cookie(alias="refresh_token")] = None,
) -> TokenResponse:
    # Accept token from request body or fallback to HTTP-only cookie
    raw_token = body.refresh_token if (body and body.refresh_token) else cookie_token
    tokens = await refresh_access_token(session, raw_token or "")
    _set_refresh_cookie(response, tokens.refresh_token)
    return tokens


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Revoke the active refresh token session",
)
async def logout(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db)],
    body: RefreshTokenRequest | None = None,
    cookie_token: Annotated[str | None, Cookie(alias="refresh_token")] = None,
) -> dict[str, str]:
    raw_token = body.refresh_token if (body and body.refresh_token) else cookie_token
    await auth_logout(session, raw_token)
    _clear_refresh_cookie(response)
    return {"message": "Successfully logged out"}


@router.get(
    "/me",
    response_model=UserProfileResponse,
    summary="Get current authenticated user profile and company info",
)
async def get_me(
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
) -> UserProfileResponse:
    return UserProfileResponse(
        user=UserResponse.model_validate(context.user),
        tenant=TenantResponse.model_validate(context.tenant),
    )


@router.post(
    "/logout-all",
    status_code=status.HTTP_200_OK,
    summary="Revoke all active refresh sessions for the current user",
)
async def logout_all(
    response: Response,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str | int]:
    count = await auth_logout_all(session, context.user.id, context.tenant.id)
    _clear_refresh_cookie(response)
    return {
        "message": "All refresh sessions have been revoked",
        "revoked_count": count,
    }


@router.get(
    "/invitations/validate",
    response_model=ValidateInvitationResponse,
    status_code=status.HTTP_200_OK,
    summary="Public endpoint: Validate employee invitation token",
)
async def validate_invitation_endpoint(
    token: Annotated[str, Query(description="URL-safe activation token")],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ValidateInvitationResponse:
    return await validate_public_invitation_token(session=session, raw_token=token)


@router.post(
    "/invitations/activate",
    response_model=ActivateAccountResponse,
    status_code=status.HTTP_200_OK,
    summary="Public endpoint: Activate account and set password",
)
async def activate_account_endpoint(
    req: ActivateAccountRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ActivateAccountResponse:
    return await service_activate_account(session=session, req=req)

