"""Pydantic schemas for authentication and registration requests/responses."""

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo, available_timezones

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from services.api.tenants.schemas import TenantResponse


class RegisterTenantRequest(BaseModel):
    """Payload to register a new tenant and create the first owner account."""

    company_name: str = Field(..., min_length=2, max_length=100)
    company_email: EmailStr
    owner_name: str = Field(..., min_length=2, max_length=100)
    owner_email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    country_code: str = Field(..., min_length=2, max_length=2)
    timezone: str = Field(default="UTC")

    @field_validator("country_code")
    @classmethod
    def validate_country_code(cls, v: str) -> str:
        clean = v.strip().upper()
        if len(clean) != 2 or not clean.isalpha():
            raise ValueError("country_code must be a 2-letter ISO country code (e.g. US, IN, GB)")
        return clean

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        clean = v.strip()
        try:
            ZoneInfo(clean)
        except Exception:
            if clean not in available_timezones():
                raise ValueError(f"Invalid IANA timezone: '{clean}'")
        return clean


class LoginRequest(BaseModel):
    """Payload for user authentication."""

    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)
    tenant_slug: str = Field(..., min_length=1, max_length=100)


class TokenResponse(BaseModel):
    """Token response returning JWT access token and rotating refresh token."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # Access token TTL in seconds


class RefreshTokenRequest(BaseModel):
    """Payload for token refresh if refresh token is passed in JSON body."""

    refresh_token: str | None = None


class UserResponse(BaseModel):
    """Public user response DTO omitting sensitive hash data."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    full_name: str
    email: str
    role: str
    status: str
    email_verified_at: datetime | None = None
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RegisterTenantResponse(BaseModel):
    """Response returned upon successful tenant registration."""

    tenant: TenantResponse
    user: UserResponse
    tokens: TokenResponse


class UserProfileResponse(BaseModel):
    """Combined profile response for /api/v1/auth/me."""

    user: UserResponse
    tenant: TenantResponse
