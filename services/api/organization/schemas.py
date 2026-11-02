"""Pydantic schemas for departments and designations."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DepartmentCreateRequest(BaseModel):
    """Payload to create a new department."""

    name: str = Field(..., min_length=2, max_length=100)
    code: str = Field(..., min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=500)
    manager_id: uuid.UUID | None = None


class DepartmentUpdateRequest(BaseModel):
    """Payload to update an existing department."""

    name: str | None = Field(default=None, min_length=2, max_length=100)
    code: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=500)
    manager_id: uuid.UUID | None = None
    is_active: bool | None = None


class DepartmentResponse(BaseModel):
    """DTO representing a department."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    code: str
    description: str | None = None
    manager_id: uuid.UUID | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DepartmentListResponse(BaseModel):
    """List response for departments with pagination count."""

    items: list[DepartmentResponse]
    total: int


class DesignationCreateRequest(BaseModel):
    """Payload to create a new job designation."""

    title: str = Field(..., min_length=2, max_length=100)
    code: str = Field(..., min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=500)


class DesignationUpdateRequest(BaseModel):
    """Payload to update an existing designation."""

    title: str | None = Field(default=None, min_length=2, max_length=100)
    code: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class DesignationResponse(BaseModel):
    """DTO representing a designation."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    title: str
    code: str
    description: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DesignationListResponse(BaseModel):
    """List response for designations with pagination count."""

    items: list[DesignationResponse]
    total: int
