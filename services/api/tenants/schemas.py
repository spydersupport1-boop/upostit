"""Pydantic schemas for tenant data transfer objects."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class TenantBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    company_email: EmailStr
    country_code: str = Field(..., min_length=2, max_length=2)
    timezone: str = Field(default="UTC")


class TenantResponse(TenantBase):
    id: uuid.UUID
    slug: str
    legal_name: str | None = None
    industry: str | None = None
    company_phone: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
