"""Shared contracts, base schemas, and common Pydantic models."""

from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """Standardized API envelope for consistent responses."""

    model_config = ConfigDict(from_attributes=True)

    success: bool = True
    data: T | None = None
    error: dict[str, Any] | None = None
    request_id: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class HealthResponse(BaseModel):
    """Schema for health probe response."""

    status: str
    timestamp: datetime
    service: str
    version: str
    environment: str
