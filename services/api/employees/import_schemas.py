"""Pydantic schemas for bulk employee import operations."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ImportJobResponse(BaseModel):
    """Status and progress counters for an asynchronous employee import job."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    created_by_user_id: uuid.UUID | None
    file_name: str
    file_format: str
    status: str
    total_rows: int
    processed_rows: int
    succeeded_rows: int
    failed_rows: int
    progress_percentage: float = Field(
        default=0.0, description="Calculated completion percentage (0.0 to 100.0)"
    )
    last_processed_row_index: int
    has_error_report: bool
    error_summary: list[dict[str, Any]]
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ImportRowError(BaseModel):
    """Detailed error diagnostics for a specific rejected row in an import file."""

    row_number: int
    employee_id: str | None = None
    work_email: str | None = None
    errors: list[str]


class ImportErrorsResponse(BaseModel):
    """Line-by-line error diagnostics and downloadable report reference for an import job."""

    job_id: uuid.UUID
    status: str
    total_failed_rows: int
    errors: list[ImportRowError]
    download_url: str | None = None


class ImportRetryResponse(BaseModel):
    """Response returned when an interrupted or failed import job is retried."""

    job_id: uuid.UUID
    status: str
    resumed_from_row_index: int
    message: str
