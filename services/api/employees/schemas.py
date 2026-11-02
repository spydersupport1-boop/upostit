"""Pydantic schemas for employee management."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

EmploymentType = Literal["full_time", "part_time", "contract", "intern", "temporary"]
EmployeeStatus = Literal["active", "inactive", "on_leave", "terminated"]


class EmployeeCreateRequest(BaseModel):
    """Payload to onboard a new employee."""

    employee_id: str = Field(..., min_length=1, max_length=50, description="Company-specific employee ID (e.g. EMP-001)")
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    work_email: EmailStr
    phone_number: str | None = Field(default=None, max_length=50)
    department_id: uuid.UUID | None = None
    designation_id: uuid.UUID | None = None
    reporting_manager_id: uuid.UUID | None = None
    employment_type: EmploymentType = "full_time"
    joining_date: date
    status: EmployeeStatus = "active"
    work_location: str | None = Field(default=None, max_length=100)
    user_id: uuid.UUID | None = None


class EmployeeUpdateRequest(BaseModel):
    """Payload to update an existing employee profile."""

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    phone_number: str | None = Field(default=None, max_length=50)
    department_id: uuid.UUID | None = None
    designation_id: uuid.UUID | None = None
    reporting_manager_id: uuid.UUID | None = None
    employment_type: EmploymentType | None = None
    joining_date: date | None = None
    work_location: str | None = Field(default=None, max_length=100)
    user_id: uuid.UUID | None = None


class EmployeeStatusUpdateRequest(BaseModel):
    """Payload to update employee lifecycle status."""

    status: EmployeeStatus


class EmployeeResponse(BaseModel):
    """DTO representing an employee profile."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID | None = None
    employee_id: str
    first_name: str
    last_name: str
    work_email: str
    phone_number: str | None = None
    department_id: uuid.UUID | None = None
    department_name: str | None = None
    designation_id: uuid.UUID | None = None
    designation_title: str | None = None
    reporting_manager_id: uuid.UUID | None = None
    reporting_manager_name: str | None = None
    employment_type: str
    joining_date: date
    status: str
    work_location: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EmployeeListResponse(BaseModel):
    """Paginated list response for employees."""

    items: list[EmployeeResponse]
    total: int
    page: int
    page_size: int
