"""Tests for Phase 3 Pydantic schemas (Departments, Designations, Employees)."""

import uuid
from datetime import date

import pytest
from pydantic import ValidationError

from services.api.employees.schemas import (
    EmployeeCreateRequest,
    EmployeeStatusUpdateRequest,
)
from services.api.organization.schemas import (
    DepartmentCreateRequest,
    DesignationCreateRequest,
)


def test_department_create_valid():
    req = DepartmentCreateRequest(
        name="Engineering",
        code="ENG",
        description="Software development department",
    )
    assert req.name == "Engineering"
    assert req.code == "ENG"
    assert req.description == "Software development department"
    assert req.manager_id is None


def test_department_create_invalid():
    # Name too short
    with pytest.raises(ValidationError):
        DepartmentCreateRequest(name="A", code="ENG")

    # Code empty
    with pytest.raises(ValidationError):
        DepartmentCreateRequest(name="Engineering", code="")


def test_designation_create_valid():
    req = DesignationCreateRequest(
        title="Senior Software Engineer",
        code="SWE-SR",
        description="Senior level engineering role",
    )
    assert req.title == "Senior Software Engineer"
    assert req.code == "SWE-SR"


def test_designation_create_invalid():
    with pytest.raises(ValidationError):
        DesignationCreateRequest(title="", code="SWE")


def test_employee_create_valid():
    dept_id = uuid.uuid4()
    desig_id = uuid.uuid4()
    req = EmployeeCreateRequest(
        employee_id="EMP-1001",
        first_name="Jane",
        last_name="Doe",
        work_email="jane.doe@enterprise.com",
        phone_number="+1-555-0199",
        department_id=dept_id,
        designation_id=desig_id,
        employment_type="full_time",
        joining_date=date(2026, 1, 15),
        status="active",
        work_location="Headquarters",
    )
    assert req.employee_id == "EMP-1001"
    assert req.first_name == "Jane"
    assert req.last_name == "Doe"
    assert str(req.work_email) == "jane.doe@enterprise.com"
    assert req.department_id == dept_id
    assert req.employment_type == "full_time"
    assert req.status == "active"


def test_employee_create_invalid_email():
    with pytest.raises(ValidationError):
        EmployeeCreateRequest(
            employee_id="EMP-1001",
            first_name="Jane",
            last_name="Doe",
            work_email="not-an-email",
            joining_date=date(2026, 1, 15),
        )


def test_employee_create_invalid_employment_type():
    with pytest.raises(ValidationError):
        EmployeeCreateRequest(
            employee_id="EMP-1001",
            first_name="Jane",
            last_name="Doe",
            work_email="jane@corp.com",
            joining_date=date(2026, 1, 15),
            employment_type="freelancer",  # Invalid literal
        )


def test_employee_status_update():
    valid = EmployeeStatusUpdateRequest(status="terminated")
    assert valid.status == "terminated"

    with pytest.raises(ValidationError):
        EmployeeStatusUpdateRequest(status="unknown_status")
