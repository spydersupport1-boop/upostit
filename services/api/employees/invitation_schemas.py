"""Pydantic schemas for employee invitations and account activation."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class InvitationResponse(BaseModel):
    """Secure representation of an employee invitation."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    employee_id: uuid.UUID
    invited_by_user_id: uuid.UUID | None = None
    email: str
    status: str
    delivery_status: str
    delivery_error: str | None = None
    attempt_count: int
    expires_at: datetime
    accepted_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    preview_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class InvitationListResponse(BaseModel):
    """Paginated collection of employee invitations."""

    items: list[InvitationResponse]
    total: int
    skip: int
    limit: int


class ValidateInvitationResponse(BaseModel):
    """Sanitized public details returned when an invitee validates their token."""

    valid: bool
    email: str
    employee_name: str
    company_name: str
    expires_at: datetime


class ActivateAccountRequest(BaseModel):
    """Payload submitted by an invited employee to establish their password and activate their account."""

    token: str = Field(..., min_length=16, description="URL-safe activation token")
    password: str = Field(..., min_length=8, max_length=128, description="New user password")
    password_confirm: str = Field(..., min_length=8, max_length=128, description="Password confirmation")


class ActivateAccountResponse(BaseModel):
    """Response returned upon successful account activation."""

    success: bool
    message: str
    user_id: uuid.UUID
    email: str
