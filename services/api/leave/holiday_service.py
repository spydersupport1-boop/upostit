"""Service layer for Holiday Calendars, Holiday Entries, and Hierarchical Calendar Resolution."""

import uuid
from datetime import UTC, date, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from services.api.employees.models import Employee
from services.api.leave.models import Holiday, HolidayCalendar
from services.api.leave.schemas import (
    HolidayCalendarCreateRequest,
    HolidayCalendarResponse,
    HolidayCalendarUpdateRequest,
    HolidayCreateRequest,
    HolidayResponse,
    HolidayUpdateRequest,
    UpcomingHolidayItem,
)
from services.api.locations.models import EmployeeLocation, Location
from services.api.organization.models import Department


def map_holiday_to_response(h: Holiday) -> HolidayResponse:
    """Maps a SQLAlchemy Holiday model to a Pydantic response."""
    now = datetime.now(UTC)
    return HolidayResponse(
        id=h.id or uuid.uuid4(),
        tenant_id=h.tenant_id,
        calendar_id=h.calendar_id,
        holiday_date=h.holiday_date,
        name=h.name,
        holiday_type=h.holiday_type,
        is_optional=h.is_optional,
        description=h.description,
        created_at=h.created_at or now,
        updated_at=h.updated_at or now,
    )


def map_calendar_to_response(
    cal: HolidayCalendar,
    holidays: list[Holiday] | None = None,
    holiday_count: int | None = None,
) -> HolidayCalendarResponse:
    """Maps a SQLAlchemy HolidayCalendar model to a Pydantic response."""
    now = datetime.now(UTC)
    h_items = [map_holiday_to_response(h) for h in holidays] if holidays is not None else []
    count = holiday_count if holiday_count is not None else len(h_items)
    return HolidayCalendarResponse(
        id=cal.id or uuid.uuid4(),
        tenant_id=cal.tenant_id,
        year=cal.year,
        name=cal.name,
        location_id=cal.location_id,
        department_id=cal.department_id,
        is_default=cal.is_default,
        holiday_count=count,
        holidays=h_items,
        created_at=cal.created_at or now,
        updated_at=cal.updated_at or now,
    )


# ==============================================================================
# Calendar Management
# ==============================================================================


async def create_holiday_calendar(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    payload: HolidayCalendarCreateRequest,
) -> HolidayCalendar:
    """Creates a new annual holiday calendar.

    Validates:
    - Workplace location belongs to tenant (if provided).
    - Department belongs to tenant (if provided).
    - If is_default is set to True, any prior default for the same tenant and year
      is updated so exactly one calendar acts as the annual default.
    """
    # 1. Validate location if specified
    if payload.location_id is not None:
        loc_stmt = select(Location).where(
            Location.tenant_id == tenant_id,
            Location.id == payload.location_id,
        )
        location = (await session.execute(loc_stmt)).scalar_one_or_none()
        if not location:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workplace location '{payload.location_id}' not found.",
            )

    # 2. Validate department if specified
    if payload.department_id is not None:
        dept_stmt = select(Department).where(
            Department.tenant_id == tenant_id,
            Department.id == payload.department_id,
        )
        department = (await session.execute(dept_stmt)).scalar_one_or_none()
        if not department:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Department '{payload.department_id}' not found.",
            )

    # 3. If setting as default, demote existing default for the same year
    if payload.is_default:
        existing_default_stmt = select(HolidayCalendar).where(
            HolidayCalendar.tenant_id == tenant_id,
            HolidayCalendar.year == payload.year,
            HolidayCalendar.is_default.is_(True),
        )
        existing_defaults = (await session.execute(existing_default_stmt)).scalars().all()
        for ed in existing_defaults:
            ed.is_default = False

    # 4. Instantiate calendar
    now = datetime.now(UTC)
    calendar = HolidayCalendar(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        year=payload.year,
        name=payload.name.strip(),
        location_id=payload.location_id,
        department_id=payload.department_id,
        is_default=payload.is_default,
        created_at=now,
        updated_at=now,
    )

    session.add(calendar)
    await session.flush()
    return calendar


async def list_holiday_calendars(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    year: int | None = None,
    location_id: uuid.UUID | None = None,
    department_id: uuid.UUID | None = None,
    is_default: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[HolidayCalendarResponse], int]:
    """Lists holiday calendars with holiday counts for the tenant."""
    base_conditions = [HolidayCalendar.tenant_id == tenant_id]

    if year is not None:
        base_conditions.append(HolidayCalendar.year == year)
    if location_id is not None:
        base_conditions.append(HolidayCalendar.location_id == location_id)
    if department_id is not None:
        base_conditions.append(HolidayCalendar.department_id == department_id)
    if is_default is not None:
        base_conditions.append(HolidayCalendar.is_default.is_(is_default))

    # Count total
    count_stmt = select(func.count()).select_from(HolidayCalendar).where(*base_conditions)
    total = (await session.execute(count_stmt)).scalar() or 0

    # Data query with left join for count of holidays
    data_stmt = (
        select(
            HolidayCalendar,
            func.count(Holiday.id).label("holiday_count"),
        )
        .outerjoin(
            Holiday,
            (Holiday.calendar_id == HolidayCalendar.id) & (Holiday.tenant_id == tenant_id),
        )
        .where(*base_conditions)
        .group_by(HolidayCalendar.id)
        .order_by(HolidayCalendar.year.desc(), HolidayCalendar.name.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(data_stmt)).all()

    items = [map_calendar_to_response(cal, holiday_count=h_count) for cal, h_count in rows]
    return items, total


async def get_holiday_calendar(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    calendar_id: uuid.UUID,
) -> HolidayCalendar:
    """Retrieves a single holiday calendar with all its holiday entries loaded."""
    stmt = (
        select(HolidayCalendar)
        .options(selectinload(HolidayCalendar.holidays))
        .where(
            HolidayCalendar.id == calendar_id,
            HolidayCalendar.tenant_id == tenant_id,
        )
    )
    calendar = (await session.execute(stmt)).scalar_one_or_none()
    if not calendar:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Holiday calendar '{calendar_id}' not found.",
        )
    return calendar


async def update_holiday_calendar(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    calendar_id: uuid.UUID,
    payload: HolidayCalendarUpdateRequest,
) -> HolidayCalendar:
    """Updates an existing holiday calendar header."""
    calendar = await get_holiday_calendar(session, tenant_id, calendar_id)

    if payload.year is not None:
        calendar.year = payload.year
    if payload.name is not None:
        calendar.name = payload.name.strip()
    if payload.location_id is not None:
        loc_stmt = select(Location).where(
            Location.tenant_id == tenant_id,
            Location.id == payload.location_id,
        )
        if not (await session.execute(loc_stmt)).scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workplace location '{payload.location_id}' not found.",
            )
        calendar.location_id = payload.location_id
    if payload.department_id is not None:
        dept_stmt = select(Department).where(
            Department.tenant_id == tenant_id,
            Department.id == payload.department_id,
        )
        if not (await session.execute(dept_stmt)).scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Department '{payload.department_id}' not found.",
            )
        calendar.department_id = payload.department_id

    if payload.is_default is not None:
        if payload.is_default:
            # Demote existing defaults for same year
            existing_default_stmt = select(HolidayCalendar).where(
                HolidayCalendar.tenant_id == tenant_id,
                HolidayCalendar.year == calendar.year,
                HolidayCalendar.id != calendar.id,
                HolidayCalendar.is_default.is_(True),
            )
            for ed in (await session.execute(existing_default_stmt)).scalars().all():
                ed.is_default = False
        calendar.is_default = payload.is_default

    await session.flush()
    return calendar


async def delete_holiday_calendar(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    calendar_id: uuid.UUID,
) -> None:
    """Deletes a holiday calendar, cascading to its contained holidays."""
    calendar = await get_holiday_calendar(session, tenant_id, calendar_id)
    await session.delete(calendar)
    await session.flush()


# ==============================================================================
# Holiday Entry Management
# ==============================================================================


async def create_holiday_entry(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    calendar_id: uuid.UUID,
    payload: HolidayCreateRequest,
) -> Holiday:
    """Adds a holiday date entry to an existing calendar.

    Validates:
    - Calendar exists and belongs to caller's tenant.
    - Unique constraint: exactly one holiday entry per date per calendar.
    - Overtime multiplier >= 1.0.
    """
    # 1. Verify calendar exists
    calendar = await get_holiday_calendar(session, tenant_id, calendar_id)

    # 2. Check for duplicate date in calendar
    dup_stmt = select(Holiday).where(
        Holiday.tenant_id == tenant_id,
        Holiday.calendar_id == calendar_id,
        Holiday.holiday_date == payload.holiday_date,
    )
    dup = (await session.execute(dup_stmt)).scalar_one_or_none()
    if dup:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"A holiday '{dup.name}' already exists on date "
                f"{payload.holiday_date.isoformat()} in calendar '{calendar.name}'."
            ),
        )

    # 3. Create entry
    now = datetime.now(UTC)
    entry = Holiday(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        calendar_id=calendar_id,
        holiday_date=payload.holiday_date,
        name=payload.name.strip(),
        holiday_type=payload.holiday_type,
        is_optional=payload.is_optional,
        description=payload.description.strip() if payload.description else None,
        created_at=now,
        updated_at=now,
    )

    session.add(entry)
    await session.flush()
    return entry


async def get_holiday_entry(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    calendar_id: uuid.UUID,
    holiday_id: uuid.UUID,
) -> Holiday:
    """Retrieves a single holiday entry."""
    stmt = select(Holiday).where(
        Holiday.id == holiday_id,
        Holiday.calendar_id == calendar_id,
        Holiday.tenant_id == tenant_id,
    )
    entry = (await session.execute(stmt)).scalar_one_or_none()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Holiday entry '{holiday_id}' not found in calendar '{calendar_id}'.",
        )
    return entry


async def update_holiday_entry(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    calendar_id: uuid.UUID,
    holiday_id: uuid.UUID,
    payload: HolidayUpdateRequest,
) -> Holiday:
    """Updates a holiday entry."""
    entry = await get_holiday_entry(session, tenant_id, calendar_id, holiday_id)

    if payload.holiday_date is not None and payload.holiday_date != entry.holiday_date:
        # Check uniqueness for updated date
        dup_stmt = select(Holiday).where(
            Holiday.tenant_id == tenant_id,
            Holiday.calendar_id == calendar_id,
            Holiday.id != holiday_id,
            Holiday.holiday_date == payload.holiday_date,
        )
        dup = (await session.execute(dup_stmt)).scalar_one_or_none()
        if dup:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A holiday already exists on date {payload.holiday_date.isoformat()}.",
            )
        entry.holiday_date = payload.holiday_date

    if payload.name is not None:
        entry.name = payload.name.strip()
    if payload.holiday_type is not None:
        entry.holiday_type = payload.holiday_type
    if payload.is_optional is not None:
        entry.is_optional = payload.is_optional
    if payload.description is not None:
        entry.description = payload.description.strip() if payload.description else None

    await session.flush()
    return entry


async def delete_holiday_entry(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    calendar_id: uuid.UUID,
    holiday_id: uuid.UUID,
) -> None:
    """Deletes a holiday entry."""
    entry = await get_holiday_entry(session, tenant_id, calendar_id, holiday_id)
    await session.delete(entry)
    await session.flush()


async def list_holidays_in_calendar(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    calendar_id: uuid.UUID,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[Holiday]:
    """Lists holidays in a specific calendar, optionally filtered by date range."""
    # Ensure calendar belongs to tenant
    await get_holiday_calendar(session, tenant_id, calendar_id)

    conditions = [
        Holiday.tenant_id == tenant_id,
        Holiday.calendar_id == calendar_id,
    ]
    if start_date is not None:
        conditions.append(Holiday.holiday_date >= start_date)
    if end_date is not None:
        conditions.append(Holiday.holiday_date <= end_date)

    stmt = select(Holiday).where(*conditions).order_by(Holiday.holiday_date.asc())
    return list((await session.execute(stmt)).scalars().all())


# ==============================================================================
# Hierarchical Calendar Resolution Engine
# ==============================================================================


async def resolve_applicable_calendar_for_employee(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    year: int,
) -> tuple[HolidayCalendar | None, str]:
    """Resolves the authoritative holiday calendar for an employee following the strict hierarchy:

    Hierarchy:
    1. Workplace/Location-specific calendar:
       - Looks up employee's primary workplace location assignment from EmployeeLocation.
       - If assigned to an active Location, searches for a HolidayCalendar where location_id == location.id.
       - Inactive locations or calendars for inactive locations are skipped.
    2. Department-specific calendar:
       - If no active location calendar matches, checks employee.department_id.
       - Searches for a HolidayCalendar where department_id == employee.department_id and location_id is NULL.
    3. Tenant Default calendar:
       - If no department calendar matches, searches for a HolidayCalendar where is_default is TRUE.
    4. None if no calendar is configured.

    Returns:
        tuple[HolidayCalendar | None, str]: The matched calendar and resolution source
        ("LOCATION", "DEPARTMENT", "TENANT_DEFAULT", or "NONE").
    """
    # 1. Fetch employee to check validity and department
    emp_stmt = select(Employee).where(
        Employee.tenant_id == tenant_id,
        Employee.id == employee_id,
    )
    employee = (await session.execute(emp_stmt)).scalar_one_or_none()
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee '{employee_id}' not found.",
        )

    # --------------------------------------------------------------------------
    # Tier 1: Workplace Location-Specific Calendar
    # --------------------------------------------------------------------------
    loc_assignment_stmt = (
        select(EmployeeLocation)
        .where(
            EmployeeLocation.tenant_id == tenant_id,
            EmployeeLocation.employee_id == employee_id,
            EmployeeLocation.is_primary.is_(True),
        )
        .order_by(EmployeeLocation.effective_from.desc())
    )
    primary_assignment = (await session.execute(loc_assignment_stmt)).scalar_one_or_none()

    if primary_assignment:
        # Check location active status
        loc_stmt = select(Location).where(
            Location.tenant_id == tenant_id,
            Location.id == primary_assignment.location_id,
            Location.is_active.is_(True),
        )
        active_loc = (await session.execute(loc_stmt)).scalar_one_or_none()
        if active_loc:
            # Query location-specific calendar for this year
            cal_stmt = select(HolidayCalendar).where(
                HolidayCalendar.tenant_id == tenant_id,
                HolidayCalendar.year == year,
                HolidayCalendar.location_id == active_loc.id,
            )
            loc_calendar = (await session.execute(cal_stmt)).scalar_one_or_none()
            if loc_calendar:
                return loc_calendar, "LOCATION"

    # --------------------------------------------------------------------------
    # Tier 2: Department-Specific Calendar
    # --------------------------------------------------------------------------
    if employee.department_id is not None:
        dept_cal_stmt = select(HolidayCalendar).where(
            HolidayCalendar.tenant_id == tenant_id,
            HolidayCalendar.year == year,
            HolidayCalendar.department_id == employee.department_id,
            HolidayCalendar.location_id.is_(None),
        )
        dept_calendar = (await session.execute(dept_cal_stmt)).scalar_one_or_none()
        if dept_calendar:
            return dept_calendar, "DEPARTMENT"

    # --------------------------------------------------------------------------
    # Tier 3: Tenant Default Calendar
    # --------------------------------------------------------------------------
    default_cal_stmt = select(HolidayCalendar).where(
        HolidayCalendar.tenant_id == tenant_id,
        HolidayCalendar.year == year,
        HolidayCalendar.is_default.is_(True),
    )
    default_calendar = (await session.execute(default_cal_stmt)).scalar_one_or_none()
    if default_calendar:
        return default_calendar, "TENANT_DEFAULT"

    return None, "NONE"


async def get_upcoming_holidays_for_employee(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID | None,
    start_date: date,
    end_date: date,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[UpcomingHolidayItem], int, HolidayCalendar | None, str]:
    """Queries upcoming holidays applicable to the employee based on hierarchical calendar resolution.

    If employee_id is None (e.g. platform admin user without employee profile),
    falls back directly to the tenant default calendar.
    """
    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"start_date ({start_date.isoformat()}) must not be after end_date ({end_date.isoformat()}).",
        )

    # Years spanning the query
    years = list(range(start_date.year, end_date.year + 1))

    resolved_cal: HolidayCalendar | None = None
    resolution_source = "NONE"
    calendar_ids: set[uuid.UUID] = set()

    for y in years:
        cal: HolidayCalendar | None = None
        source: str = "NONE"

        if employee_id is not None:
            cal, source = await resolve_applicable_calendar_for_employee(
                session=session,
                tenant_id=tenant_id,
                employee_id=employee_id,
                year=y,
            )
        else:
            # Fallback to tenant default calendar
            stmt = select(HolidayCalendar).where(
                HolidayCalendar.tenant_id == tenant_id,
                HolidayCalendar.year == y,
                HolidayCalendar.is_default.is_(True),
            )
            cal = (await session.execute(stmt)).scalar_one_or_none()
            if cal:
                source = "TENANT_DEFAULT"

        if cal:
            calendar_ids.add(cal.id)
            if resolved_cal is None:
                resolved_cal = cal
                resolution_source = source

    if not calendar_ids:
        return [], 0, None, "NONE"

    # Query holidays in the resolved calendars within date range
    count_stmt = (
        select(func.count())
        .select_from(Holiday)
        .where(
            Holiday.tenant_id == tenant_id,
            Holiday.calendar_id.in_(calendar_ids),
            Holiday.holiday_date >= start_date,
            Holiday.holiday_date <= end_date,
        )
    )
    total = (await session.execute(count_stmt)).scalar() or 0

    data_stmt = (
        select(Holiday, HolidayCalendar.name.label("cal_name"))
        .join(HolidayCalendar, Holiday.calendar_id == HolidayCalendar.id)
        .where(
            Holiday.tenant_id == tenant_id,
            Holiday.calendar_id.in_(calendar_ids),
            Holiday.holiday_date >= start_date,
            Holiday.holiday_date <= end_date,
        )
        .order_by(Holiday.holiday_date.asc(), Holiday.name.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(data_stmt)).all()

    items = [
        UpcomingHolidayItem(
            id=h.id,
            holiday_date=h.holiday_date,
            name=h.name,
            holiday_type=h.holiday_type,
            is_optional=h.is_optional,
            description=h.description,
            calendar_id=h.calendar_id,
            calendar_name=cal_name,
        )
        for h, cal_name in rows
    ]

    return items, total, resolved_cal, resolution_source
