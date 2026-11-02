"""Business logic service for employee workplace assignments."""

import uuid
from datetime import UTC, date, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.employees.models import Employee
from services.api.locations.models import EmployeeLocation, Location
from services.api.locations.schemas import (
    EmployeeWorkplaceAssignRequest,
    EmployeeWorkplaceResponse,
    EmployeeWorkplaceUpdateRequest,
    LocationEmployeeItem,
)
from services.api.locations.service import date_ranges_overlap
from services.api.organization.models import Department, Designation


def format_location_address(loc: Location) -> str:
    """Combines location address fields into a single legible string."""
    parts = [loc.address_line1]
    if loc.address_line2:
        parts.append(loc.address_line2)
    parts.append(loc.city)
    if loc.state:
        parts.append(loc.state)
    if loc.postal_code:
        parts.append(loc.postal_code)
    parts.append(loc.country_code)
    return ", ".join(parts)


def map_assignment_to_response(
    assignment: EmployeeLocation,
    location: Location,
    on_date: date | None = None,
) -> EmployeeWorkplaceResponse:
    """Serializes an EmployeeLocation ORM model into an EmployeeWorkplaceResponse DTO."""
    d = on_date or date.today()
    is_current = assignment.effective_from <= d and (
        assignment.effective_to is None or assignment.effective_to >= d
    )
    return EmployeeWorkplaceResponse(
        id=assignment.id,
        employee_id=assignment.employee_id,
        location_id=location.id,
        location_name=location.name,
        location_code=location.code,
        location_address=format_location_address(location),
        location_city=location.city,
        location_country_code=location.country_code,
        location_is_active=location.is_active,
        is_primary=assignment.is_primary,
        effective_from=assignment.effective_from,
        effective_to=assignment.effective_to,
        is_current=is_current,
        created_at=assignment.created_at,
    )


async def assign_workplace_to_employee(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    data: EmployeeWorkplaceAssignRequest,
) -> EmployeeWorkplaceResponse:
    """Assigns an employee to a workplace location with primary status and date validation."""
    # 1. Verify employee exists and belongs to tenant
    emp_stmt = select(Employee).where(
        Employee.id == employee_id,
        Employee.tenant_id == tenant_id,
    )
    emp_res = await session.execute(emp_stmt)
    employee = emp_res.scalar_one_or_none()
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found.",
        )

    # 2. Inactive employees cannot receive new workplace assignments
    if employee.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot assign workplace to an inactive employee. Current status: '{employee.status}'.",
        )

    # 3. Verify location exists and belongs to tenant
    loc_stmt = select(Location).where(
        Location.id == data.location_id,
        Location.tenant_id == tenant_id,
    )
    loc_res = await session.execute(loc_stmt)
    location = loc_res.scalar_one_or_none()
    if location is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workplace location not found.",
        )

    # 4. Inactive locations cannot receive new assignments
    if not location.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot assign an inactive workplace location.",
        )

    # 5. Validate date bounds
    if data.effective_to is not None and data.effective_to < data.effective_from:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Effective end date cannot be earlier than start date.",
        )

    # 6. Check for duplicate assignment starting on same date
    dup_stmt = select(EmployeeLocation.id).where(
        EmployeeLocation.tenant_id == tenant_id,
        EmployeeLocation.employee_id == employee_id,
        EmployeeLocation.location_id == data.location_id,
        EmployeeLocation.effective_from == data.effective_from,
    )
    dup_res = await session.execute(dup_stmt)
    if dup_res.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An assignment for this workplace starting on {data.effective_from} already exists for this employee.",
        )

    # 7. Check for overlapping primary assignments if this assignment is primary
    if data.is_primary:
        primaries_stmt = (
            select(EmployeeLocation, Location)
            .join(Location, EmployeeLocation.location_id == Location.id)
            .where(
                EmployeeLocation.tenant_id == tenant_id,
                EmployeeLocation.employee_id == employee_id,
                EmployeeLocation.is_primary.is_(True),
            )
        )
        primaries_res = await session.execute(primaries_stmt)
        for existing_assign, existing_loc in primaries_res.all():
            if date_ranges_overlap(
                existing_assign.effective_from,
                existing_assign.effective_to,
                data.effective_from,
                data.effective_to,
            ):
                conflicting_dates = (
                    f"{existing_assign.effective_from} to "
                    f"{existing_assign.effective_to.isoformat() if existing_assign.effective_to else 'ongoing'}"
                )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"An employee can have only one primary workplace on any given date. "
                        f"Conflicting primary assignment: '{existing_loc.name}' ({conflicting_dates})."
                    ),
                )

    # 8. Create assignment record
    now = datetime.now(UTC)
    assignment = EmployeeLocation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=employee_id,
        location_id=data.location_id,
        is_primary=data.is_primary,
        effective_from=data.effective_from,
        effective_to=data.effective_to,
        created_at=now,
    )
    session.add(assignment)

    try:
        await session.commit()
        await session.refresh(assignment)
    except IntegrityError as exc:
        await session.rollback()
        err_msg = str(exc).lower()
        if "excl_emp_primary_workplace_overlap" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An employee can have only one primary workplace on any given date.",
            )
        if "uq_emp_loc_assignment" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An assignment for this workplace starting on this date already exists for this employee.",
            )
        if "chk_emp_loc_dates" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Effective end date cannot be earlier than start date.",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workplace assignment violates database integrity constraints.",
        )

    return map_assignment_to_response(assignment, location)


async def list_employee_workplaces(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    is_current: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[EmployeeWorkplaceResponse], int]:
    """Retrieves paginated workplace assignments for an employee."""
    # Verify employee exists in caller tenant
    emp_stmt = select(Employee.id).where(
        Employee.id == employee_id,
        Employee.tenant_id == tenant_id,
    )
    emp_res = await session.execute(emp_stmt)
    if emp_res.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found.",
        )

    base_query = (
        select(EmployeeLocation, Location)
        .join(
            Location,
            (EmployeeLocation.location_id == Location.id)
            & (EmployeeLocation.tenant_id == Location.tenant_id),
        )
        .where(
            EmployeeLocation.tenant_id == tenant_id,
            EmployeeLocation.employee_id == employee_id,
        )
    )

    today = date.today()
    if is_current is True:
        base_query = base_query.where(
            EmployeeLocation.effective_from <= today,
            or_(
                EmployeeLocation.effective_to.is_(None),
                EmployeeLocation.effective_to >= today,
            ),
        )
    elif is_current is False:
        base_query = base_query.where(
            or_(
                EmployeeLocation.effective_to < today,
                EmployeeLocation.effective_from > today,
            )
        )

    # Count total
    count_stmt = select(func.count()).select_from(base_query.subquery())
    count_res = await session.execute(count_stmt)
    total = count_res.scalar_one() or 0

    # Paginate and order by primary first, then effective_from descending, then location name
    offset = (page - 1) * page_size
    query = (
        base_query.order_by(
            EmployeeLocation.is_primary.desc(),
            EmployeeLocation.effective_from.desc(),
            Location.name.asc(),
        )
        .offset(offset)
        .limit(page_size)
    )
    res = await session.execute(query)
    items = [
        map_assignment_to_response(assignment, loc, on_date=today)
        for assignment, loc in res.all()
    ]
    return items, total


async def get_my_workplaces(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    is_current: bool | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[EmployeeWorkplaceResponse], int]:
    """Retrieves workplace assignments for the authenticated user's linked employee profile."""
    emp_stmt = select(Employee.id).where(
        Employee.tenant_id == tenant_id,
        Employee.user_id == user_id,
    )
    emp_res = await session.execute(emp_stmt)
    emp_id = emp_res.scalar_one_or_none()
    if emp_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No employee profile found for current user account",
        )
    return await list_employee_workplaces(
        session=session,
        tenant_id=tenant_id,
        employee_id=emp_id,
        is_current=is_current,
        page=page,
        page_size=page_size,
    )


async def update_employee_workplace_assignment(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    assignment_id: uuid.UUID,
    data: EmployeeWorkplaceUpdateRequest,
) -> EmployeeWorkplaceResponse:
    """Updates an existing workplace assignment's primary status or effective date range."""
    # 1. Verify employee exists in tenant
    emp_stmt = select(Employee.id).where(
        Employee.id == employee_id,
        Employee.tenant_id == tenant_id,
    )
    emp_res = await session.execute(emp_stmt)
    if emp_res.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found.",
        )

    # 2. Verify assignment exists in tenant for this employee
    assign_stmt = (
        select(EmployeeLocation, Location)
        .join(Location, EmployeeLocation.location_id == Location.id)
        .where(
            EmployeeLocation.tenant_id == tenant_id,
            EmployeeLocation.employee_id == employee_id,
            EmployeeLocation.id == assignment_id,
        )
    )
    assign_res = await session.execute(assign_stmt)
    row = assign_res.one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workplace assignment not found.",
        )
    assignment, location = row

    target_is_primary = data.is_primary if data.is_primary is not None else assignment.is_primary
    target_effective_from = (
        data.effective_from if data.effective_from is not None else assignment.effective_from
    )
    target_effective_to = (
        data.effective_to if "effective_to" in data.model_fields_set else assignment.effective_to
    )

    if target_effective_to is not None and target_effective_to < target_effective_from:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Effective end date cannot be earlier than start date.",
        )

    # 3. Check for overlapping primary assignments (excluding this assignment itself)
    if target_is_primary:
        other_primaries_stmt = (
            select(EmployeeLocation, Location)
            .join(Location, EmployeeLocation.location_id == Location.id)
            .where(
                EmployeeLocation.tenant_id == tenant_id,
                EmployeeLocation.employee_id == employee_id,
                EmployeeLocation.id != assignment_id,
                EmployeeLocation.is_primary.is_(True),
            )
        )
        other_primaries_res = await session.execute(other_primaries_stmt)
        for other_assign, other_loc in other_primaries_res.all():
            if date_ranges_overlap(
                other_assign.effective_from,
                other_assign.effective_to,
                target_effective_from,
                target_effective_to,
            ):
                conflicting_dates = (
                    f"{other_assign.effective_from} to "
                    f"{other_assign.effective_to.isoformat() if other_assign.effective_to else 'ongoing'}"
                )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"An employee can have only one primary workplace on any given date. "
                        f"Conflicting primary assignment: '{other_loc.name}' ({conflicting_dates})."
                    ),
                )

    assignment.is_primary = target_is_primary
    assignment.effective_from = target_effective_from
    assignment.effective_to = target_effective_to

    try:
        await session.commit()
        await session.refresh(assignment)
    except IntegrityError as exc:
        await session.rollback()
        err_msg = str(exc).lower()
        if "excl_emp_primary_workplace_overlap" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An employee can have only one primary workplace on any given date.",
            )
        if "uq_emp_loc_assignment" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An assignment for this workplace starting on this date already exists for this employee.",
            )
        if "chk_emp_loc_dates" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Effective end date cannot be earlier than start date.",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workplace assignment violates database integrity constraints.",
        )

    return map_assignment_to_response(assignment, location)


async def end_employee_workplace_assignment(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    assignment_id: uuid.UUID,
    end_date: date | None = None,
) -> EmployeeWorkplaceResponse:
    """Safely ends an employee workplace assignment by setting effective_to, preserving historical data."""
    # 1. Verify employee exists in tenant
    emp_stmt = select(Employee.id).where(
        Employee.id == employee_id,
        Employee.tenant_id == tenant_id,
    )
    emp_res = await session.execute(emp_stmt)
    if emp_res.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found.",
        )

    # 2. Verify assignment exists in tenant for this employee
    assign_stmt = (
        select(EmployeeLocation, Location)
        .join(Location, EmployeeLocation.location_id == Location.id)
        .where(
            EmployeeLocation.tenant_id == tenant_id,
            EmployeeLocation.employee_id == employee_id,
            EmployeeLocation.id == assignment_id,
        )
    )
    assign_res = await session.execute(assign_stmt)
    row = assign_res.one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workplace assignment not found.",
        )
    assignment, location = row

    target_end_date = end_date or date.today()

    # 3. Check if already ended on or before target_end_date
    if assignment.effective_to is not None and assignment.effective_to <= target_end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Workplace assignment has already ended on {assignment.effective_to}.",
        )

    # 4. Check that end_date is not earlier than start date
    if target_end_date < assignment.effective_from:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"End date ({target_end_date}) cannot be earlier than assignment start date ({assignment.effective_from}).",
        )

    assignment.effective_to = target_end_date

    try:
        await session.commit()
        await session.refresh(assignment)
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to end workplace assignment due to constraint violation.",
        )

    return map_assignment_to_response(assignment, location)


async def list_location_employees(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID,
    search: str | None = None,
    is_primary: bool | None = None,
    is_current: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[LocationEmployeeItem], int]:
    """Lists employees assigned to a workplace location with search and filtering."""
    # 1. Verify location exists in tenant
    loc_stmt = select(Location.id).where(
        Location.id == location_id,
        Location.tenant_id == tenant_id,
    )
    loc_res = await session.execute(loc_stmt)
    if loc_res.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workplace location not found.",
        )

    base_query = (
        select(EmployeeLocation, Employee, Department.name, Designation.title)
        .join(
            Employee,
            (EmployeeLocation.employee_id == Employee.id)
            & (EmployeeLocation.tenant_id == Employee.tenant_id),
        )
        .outerjoin(Department, Employee.department_id == Department.id)
        .outerjoin(Designation, Employee.designation_id == Designation.id)
        .where(
            EmployeeLocation.tenant_id == tenant_id,
            EmployeeLocation.location_id == location_id,
        )
    )

    if search:
        search_pattern = f"%{search.strip()}%"
        base_query = base_query.where(
            or_(
                Employee.first_name.ilike(search_pattern),
                Employee.last_name.ilike(search_pattern),
                Employee.employee_id.ilike(search_pattern),
                Employee.work_email.ilike(search_pattern),
            )
        )

    if is_primary is not None:
        base_query = base_query.where(EmployeeLocation.is_primary == is_primary)

    today = date.today()
    if is_current is True:
        base_query = base_query.where(
            EmployeeLocation.effective_from <= today,
            or_(
                EmployeeLocation.effective_to.is_(None),
                EmployeeLocation.effective_to >= today,
            ),
        )
    elif is_current is False:
        base_query = base_query.where(
            or_(
                EmployeeLocation.effective_to < today,
                EmployeeLocation.effective_from > today,
            )
        )

    count_stmt = select(func.count()).select_from(base_query.subquery())
    count_res = await session.execute(count_stmt)
    total = count_res.scalar_one() or 0

    offset = (page - 1) * page_size
    query = (
        base_query.order_by(
            EmployeeLocation.is_primary.desc(),
            Employee.first_name.asc(),
            Employee.last_name.asc(),
        )
        .offset(offset)
        .limit(page_size)
    )
    res = await session.execute(query)

    items: list[LocationEmployeeItem] = []
    for assign, emp, dept_name, desig_title in res.all():
        is_cur = assign.effective_from <= today and (
            assign.effective_to is None or assign.effective_to >= today
        )
        items.append(
            LocationEmployeeItem(
                assignment_id=assign.id,
                employee_id=emp.id,
                employee_code=emp.employee_id,
                employee_name=f"{emp.first_name} {emp.last_name}",
                work_email=emp.work_email,
                department_id=emp.department_id,
                department_name=dept_name,
                designation_id=emp.designation_id,
                designation_title=desig_title,
                is_primary=assign.is_primary,
                effective_from=assign.effective_from,
                effective_to=assign.effective_to,
                is_current=is_cur,
            )
        )

    return items, total
