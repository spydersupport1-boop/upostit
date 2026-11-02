"""Business logic service for employee management."""

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from services.api.employees.models import Employee
from services.api.employees.schemas import (
    EmployeeCreateRequest,
    EmployeeResponse,
    EmployeeUpdateRequest,
)
from services.api.organization.models import Department, Designation


async def _to_employee_response(emp: Employee) -> EmployeeResponse:
    """Converts an Employee ORM model to EmployeeResponse DTO with enriched display names."""
    return EmployeeResponse(
        id=emp.id,
        tenant_id=emp.tenant_id,
        user_id=emp.user_id,
        employee_id=emp.employee_id,
        first_name=emp.first_name,
        last_name=emp.last_name,
        work_email=emp.work_email,
        phone_number=emp.phone_number,
        department_id=emp.department_id,
        department_name=emp.department.name if emp.department else None,
        designation_id=emp.designation_id,
        designation_title=emp.designation.title if emp.designation else None,
        reporting_manager_id=emp.reporting_manager_id,
        reporting_manager_name=(
            f"{emp.manager.first_name} {emp.manager.last_name}"
            if emp.manager
            else None
        ),
        employment_type=emp.employment_type,
        joining_date=emp.joining_date,
        status=emp.status,
        work_location=emp.work_location,
        created_at=emp.created_at,
        updated_at=emp.updated_at,
    )


async def create_employee(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    req: EmployeeCreateRequest,
) -> EmployeeResponse:
    """Creates a new employee profile within the tenant organization."""
    clean_emp_id = req.employee_id.strip().upper()
    clean_email = str(req.work_email).strip().lower()

    # 1. Uniqueness check for employee_id within tenant
    res_id = await session.execute(
        select(Employee).where(
            Employee.tenant_id == tenant_id,
            Employee.employee_id == clean_emp_id,
        )
    )
    if res_id.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Employee with ID '{clean_emp_id}' already exists in your organization",
        )

    # 2. Uniqueness check for work_email within tenant
    res_email = await session.execute(
        select(Employee).where(
            Employee.tenant_id == tenant_id,
            func.lower(Employee.work_email) == clean_email,
        )
    )
    if res_email.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Employee with work email '{clean_email}' already exists in your organization",
        )

    # 3. Department validation (must belong to same tenant and be active)
    if req.department_id:
        dept_res = await session.execute(
            select(Department).where(
                Department.id == req.department_id,
                Department.tenant_id == tenant_id,
            )
        )
        dept = dept_res.scalar_one_or_none()
        if not dept:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected department does not exist in your organization",
            )
        if not dept.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot assign an inactive department",
            )

    # 4. Designation validation (must belong to same tenant and be active)
    if req.designation_id:
        desig_res = await session.execute(
            select(Designation).where(
                Designation.id == req.designation_id,
                Designation.tenant_id == tenant_id,
            )
        )
        desig = desig_res.scalar_one_or_none()
        if not desig:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected designation does not exist in your organization",
            )
        if not desig.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot assign an inactive designation",
            )

    # 5. Reporting manager validation (must belong to same tenant and be active)
    if req.reporting_manager_id:
        mgr_res = await session.execute(
            select(Employee).where(
                Employee.id == req.reporting_manager_id,
                Employee.tenant_id == tenant_id,
            )
        )
        mgr = mgr_res.scalar_one_or_none()
        if not mgr:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected reporting manager does not exist in your organization",
            )
        if mgr.status != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot assign an inactive or terminated employee as reporting manager",
            )

    # 6. User account association validation (if provided, must belong to same tenant and not already linked)
    if req.user_id:
        from services.api.auth.models import User

        user_res = await session.execute(
            select(User).where(
                User.id == req.user_id,
                User.tenant_id == tenant_id,
            )
        )
        if not user_res.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected user account does not exist in your organization",
            )
        existing_link_res = await session.execute(
            select(Employee).where(
                Employee.tenant_id == tenant_id,
                Employee.user_id == req.user_id,
            )
        )
        if existing_link_res.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Selected user account is already linked to another employee profile",
            )

    new_emp = Employee(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=req.user_id,
        employee_id=clean_emp_id,
        first_name=req.first_name.strip(),
        last_name=req.last_name.strip(),
        work_email=clean_email,
        phone_number=req.phone_number.strip() if req.phone_number else None,
        department_id=req.department_id,
        designation_id=req.designation_id,
        reporting_manager_id=req.reporting_manager_id,
        employment_type=req.employment_type,
        joining_date=req.joining_date,
        status=req.status,
        work_location=req.work_location.strip() if req.work_location else None,
    )
    session.add(new_emp)
    await session.commit()

    # Load with joined relations for display names
    return await get_employee(session, tenant_id, new_emp.id)


async def get_employee(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    emp_id: uuid.UUID,
) -> EmployeeResponse:
    """Retrieves full employee details with joined department, designation, and manager names."""
    res = await session.execute(
        select(Employee)
        .options(
            joinedload(Employee.department),
            joinedload(Employee.designation),
            joinedload(Employee.manager),
        )
        .where(
            Employee.id == emp_id,
            Employee.tenant_id == tenant_id,
        )
    )
    emp = res.scalar_one_or_none()
    if not emp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )
    return await _to_employee_response(emp)


async def list_employees(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    search: str | None = None,
    department_id: uuid.UUID | None = None,
    designation_id: uuid.UUID | None = None,
    status_filter: str | None = None,
    employment_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[EmployeeResponse], int]:
    """Lists employees with search, multi-field filtering, and pagination."""
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    offset = (page - 1) * page_size

    query = (
        select(Employee)
        .options(
            joinedload(Employee.department),
            joinedload(Employee.designation),
            joinedload(Employee.manager),
        )
        .where(Employee.tenant_id == tenant_id)
    )
    count_query = select(func.count()).select_from(Employee).where(Employee.tenant_id == tenant_id)

    if department_id:
        query = query.where(Employee.department_id == department_id)
        count_query = count_query.where(Employee.department_id == department_id)

    if designation_id:
        query = query.where(Employee.designation_id == designation_id)
        count_query = count_query.where(Employee.designation_id == designation_id)

    if status_filter:
        query = query.where(Employee.status == status_filter)
        count_query = count_query.where(Employee.status == status_filter)

    if employment_type:
        query = query.where(Employee.employment_type == employment_type)
        count_query = count_query.where(Employee.employment_type == employment_type)

    if search:
        search_pattern = f"%{search.strip()}%"
        cond = or_(
            Employee.first_name.ilike(search_pattern),
            Employee.last_name.ilike(search_pattern),
            Employee.employee_id.ilike(search_pattern),
            Employee.work_email.ilike(search_pattern),
        )
        query = query.where(cond)
        count_query = count_query.where(cond)

    total_res = await session.execute(count_query)
    total = total_res.scalar_one()

    query = query.order_by(Employee.last_name.asc(), Employee.first_name.asc()).limit(page_size).offset(offset)
    items_res = await session.execute(query)
    items = list(items_res.scalars().all())

    responses = [await _to_employee_response(e) for e in items]
    return responses, total


async def update_employee(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    emp_id: uuid.UUID,
    req: EmployeeUpdateRequest,
) -> EmployeeResponse:
    """Updates an existing employee profile."""
    res = await session.execute(
        select(Employee).where(
            Employee.id == emp_id,
            Employee.tenant_id == tenant_id,
        )
    )
    emp = res.scalar_one_or_none()
    if not emp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    # Department validation
    if req.department_id is not None:
        dept_res = await session.execute(
            select(Department).where(
                Department.id == req.department_id,
                Department.tenant_id == tenant_id,
            )
        )
        dept = dept_res.scalar_one_or_none()
        if not dept:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected department does not exist in your organization",
            )
        if not dept.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot assign an inactive department",
            )
        emp.department_id = req.department_id

    # Designation validation
    if req.designation_id is not None:
        desig_res = await session.execute(
            select(Designation).where(
                Designation.id == req.designation_id,
                Designation.tenant_id == tenant_id,
            )
        )
        desig = desig_res.scalar_one_or_none()
        if not desig:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected designation does not exist in your organization",
            )
        if not desig.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot assign an inactive designation",
            )
        emp.designation_id = req.designation_id

    # Reporting manager validation & cycle detection
    if req.reporting_manager_id is not None:
        if req.reporting_manager_id == emp_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An employee cannot be their own reporting manager",
            )
        mgr_res = await session.execute(
            select(Employee).where(
                Employee.id == req.reporting_manager_id,
                Employee.tenant_id == tenant_id,
            )
        )
        mgr = mgr_res.scalar_one_or_none()
        if not mgr:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected reporting manager does not exist in your organization",
            )
        if mgr.status != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot assign an inactive or terminated employee as reporting manager",
            )

        # Detect reporting hierarchy cycles (emp_id cannot be an ancestor of req.reporting_manager_id)
        curr_mgr_id: uuid.UUID | None = mgr.reporting_manager_id
        visited: set[uuid.UUID] = {emp_id, req.reporting_manager_id}
        while curr_mgr_id is not None:
            if curr_mgr_id == emp_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Circular reporting detected: an employee cannot report to someone in their own reporting chain",
                )
            if curr_mgr_id in visited:
                break
            visited.add(curr_mgr_id)
            ancestor_res = await session.execute(
                select(Employee.reporting_manager_id).where(
                    Employee.id == curr_mgr_id,
                    Employee.tenant_id == tenant_id,
                )
            )
            curr_mgr_id = ancestor_res.scalar_one_or_none()

        emp.reporting_manager_id = req.reporting_manager_id

    if req.first_name is not None:
        emp.first_name = req.first_name.strip()
    if req.last_name is not None:
        emp.last_name = req.last_name.strip()
    if req.phone_number is not None:
        emp.phone_number = req.phone_number.strip() if req.phone_number else None
    if req.employment_type is not None:
        emp.employment_type = req.employment_type
    if req.joining_date is not None:
        emp.joining_date = req.joining_date
    if req.work_location is not None:
        emp.work_location = req.work_location.strip() if req.work_location else None
    if req.user_id is not None:
        from services.api.auth.models import User

        user_res = await session.execute(
            select(User).where(
                User.id == req.user_id,
                User.tenant_id == tenant_id,
            )
        )
        if not user_res.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected user account does not exist in your organization",
            )
        existing_link_res = await session.execute(
            select(Employee).where(
                Employee.tenant_id == tenant_id,
                Employee.user_id == req.user_id,
                Employee.id != emp_id,
            )
        )
        if existing_link_res.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Selected user account is already linked to another employee profile",
            )
        emp.user_id = req.user_id

    emp.updated_at = datetime.now(UTC)
    await session.commit()

    return await get_employee(session, tenant_id, emp_id)


ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "active": {"active", "inactive", "on_leave", "terminated"},
    "on_leave": {"on_leave", "active", "inactive", "terminated"},
    "inactive": {"inactive", "active", "terminated"},
    "terminated": {"terminated", "active"},
}


async def update_employee_status(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    emp_id: uuid.UUID,
    new_status: str,
) -> EmployeeResponse:
    """Updates employee status with transition validation (e.g. active, inactive, terminated, on_leave)."""
    res = await session.execute(
        select(Employee).where(
            Employee.id == emp_id,
            Employee.tenant_id == tenant_id,
        )
    )
    emp = res.scalar_one_or_none()
    if not emp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    allowed = ALLOWED_STATUS_TRANSITIONS.get(emp.status, set())
    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid employee status transition from '{emp.status}' to '{new_status}'",
        )

    emp.status = new_status
    emp.updated_at = datetime.now(UTC)

    # Synchronize linked User account and session state if user_id is present
    if emp.user_id:
        from services.api.auth.models import RefreshToken, User

        user_res = await session.execute(
            select(User).where(
                User.id == emp.user_id,
                User.tenant_id == tenant_id,
            )
        )
        linked_user = user_res.scalar_one_or_none()
        if linked_user:
            if new_status in ("inactive", "terminated"):
                linked_user.status = "inactive"
                linked_user.updated_at = datetime.now(UTC)
                # Immediately revoke all active refresh tokens for this user
                await session.execute(
                    update(RefreshToken)
                    .where(
                        RefreshToken.user_id == linked_user.id,
                        RefreshToken.tenant_id == tenant_id,
                        RefreshToken.revoked_at.is_(None),
                    )
                    .values(revoked_at=datetime.now(UTC))
                )
            elif new_status == "active" and linked_user.status == "inactive":
                linked_user.status = "active"
                linked_user.updated_at = datetime.now(UTC)

    await session.commit()

    return await get_employee(session, tenant_id, emp_id)


async def get_employee_by_user_id(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
) -> EmployeeResponse:
    """Retrieves an employee profile linked to a specific user account within the tenant."""
    res = await session.execute(
        select(Employee)
        .options(
            joinedload(Employee.department),
            joinedload(Employee.designation),
            joinedload(Employee.manager),
        )
        .where(
            Employee.tenant_id == tenant_id,
            Employee.user_id == user_id,
        )
    )
    emp = res.scalar_one_or_none()
    if not emp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No employee profile found for current user account",
        )
    return await _to_employee_response(emp)
