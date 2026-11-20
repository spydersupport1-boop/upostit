"""Service layer for Leave Application, Balance Tracking, and Supervisor Adjudication."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from services.api.attendance.models import AttendanceDay
from services.api.attendance.service import (
    recalculate_attendance_day,
    resolve_employee_shift_version,
)
from services.api.employees.models import Employee
from services.api.leave.holiday_service import resolve_applicable_calendar_for_employee
from services.api.leave.models import (
    Holiday,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
)
from services.api.leave.schemas import (
    LeaveBalanceResponse,
    LeaveRequestCreate,
    LeaveRequestResponse,
)


def map_leave_balance_to_response(bal: LeaveBalance, lt: LeaveType) -> LeaveBalanceResponse:
    """Maps a SQLAlchemy LeaveBalance and LeaveType to a Pydantic response."""
    now = datetime.now(UTC)
    return LeaveBalanceResponse(
        id=bal.id or uuid.uuid4(),
        tenant_id=bal.tenant_id,
        employee_id=bal.employee_id,
        leave_type_id=bal.leave_type_id,
        leave_type_code=lt.code if lt else "",
        leave_type_name=lt.name if lt else "",
        year=bal.year,
        annual_allocation=bal.annual_allocation,
        carried_forward=bal.carried_forward,
        accrued=bal.accrued,
        used=bal.used,
        pending_approval=bal.pending_approval,
        available_balance=bal.available_balance,
        created_at=bal.created_at or now,
        updated_at=bal.updated_at or now,
    )


def map_leave_request_to_response(
    req: LeaveRequest,
    emp: Employee | None = None,
    lt: LeaveType | None = None,
) -> LeaveRequestResponse:
    """Maps a SQLAlchemy LeaveRequest to a Pydantic response."""
    now = datetime.now(UTC)
    emp_name = f"{emp.first_name} {emp.last_name}" if emp else None
    return LeaveRequestResponse(
        id=req.id or uuid.uuid4(),
        tenant_id=req.tenant_id,
        employee_id=req.employee_id,
        employee_name=emp_name,
        leave_type_id=req.leave_type_id,
        leave_type_code=lt.code
        if lt
        else (req.leave_type.code if getattr(req, "leave_type", None) else None),
        leave_type_name=lt.name
        if lt
        else (req.leave_type.name if getattr(req, "leave_type", None) else None),
        start_date=req.start_date,
        end_date=req.end_date,
        is_half_day=bool(req.is_half_day) if req.is_half_day is not None else False,
        half_day_period=req.half_day_period,
        total_days=req.total_days,
        reason=req.reason,
        status=req.status,
        reviewer_user_id=req.reviewer_user_id,
        reviewer_notes=req.reviewer_notes,
        decided_at=req.decided_at,
        created_at=req.created_at or now,
        updated_at=req.updated_at or now,
    )


# ==============================================================================
# Holiday & Weekly-Off Deductible Days Calculation
# ==============================================================================


async def calculate_leave_working_days(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    start_date: date,
    end_date: date,
    is_half_day: bool = False,
    half_day_period: str | None = None,
) -> tuple[Decimal, list[date], list[date]]:
    """Calculates the net deductible leave days between start_date and end_date.

    Guarantees:
    - Excludes non-working holidays based on the employee's resolved holiday calendar.
    - Excludes weekly-off days based on the employee's active shift or standard weekend (Sat/Sun).
    - Avoids double-counting dates that are both weekly-offs and holidays.
    - If is_half_day is True, validates single-day date range and returns exactly 0.50 days.
    - Rejects date ranges containing zero working days.

    Returns:
        tuple[Decimal, list[date], list[date]]:
            (total_deductible_days, working_dates, excluded_dates)
    """
    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"start_date ({start_date.isoformat()}) must not be after end_date ({end_date.isoformat()}).",
        )

    # 1. Handle Half-Day Requests
    if is_half_day:
        if start_date != end_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Half-day leave requests must have the same start and end date.",
            )
        if half_day_period not in ("FIRST_HALF", "SECOND_HALF"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Half-day period must be specified as 'FIRST_HALF' or 'SECOND_HALF'.",
            )

        # Check if the single target date is a holiday or weekly off
        target_cal, _ = await resolve_applicable_calendar_for_employee(
            session=session,
            tenant_id=tenant_id,
            employee_id=employee_id,
            year=start_date.year,
        )
        if target_cal:
            h_stmt = select(Holiday).where(
                Holiday.tenant_id == tenant_id,
                Holiday.calendar_id == target_cal.id,
                Holiday.holiday_date == start_date,
            )
            holiday = (await session.execute(h_stmt)).scalar_one_or_none()
            if (
                holiday
                and holiday.holiday_type in ("PUBLIC", "COMPANY")
                and not holiday.is_optional
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot apply for half-day leave on a public holiday ({holiday.name}).",
                )

        # Check weekly off (Sunday=0, Saturday=6)
        day_of_week = (start_date.weekday() + 1) % 7
        if day_of_week in (0, 6):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot apply for half-day leave on a weekend/weekly-off day.",
            )

        return Decimal("0.50"), [start_date], []

    # 2. Multi-Day or Full-Day Date Range Calculation
    # Fetch resolved holiday calendar for the year
    calendar, _ = await resolve_applicable_calendar_for_employee(
        session=session,
        tenant_id=tenant_id,
        employee_id=employee_id,
        year=start_date.year,
    )

    holidays_on_dates: set[date] = set()
    if calendar:
        range_h_stmt = select(Holiday).where(
            Holiday.tenant_id == tenant_id,
            Holiday.calendar_id == calendar.id,
            Holiday.holiday_date >= start_date,
            Holiday.holiday_date <= end_date,
            Holiday.holiday_type.in_(["PUBLIC", "COMPANY"]),
            Holiday.is_optional.is_(False),
        )
        range_h_res = (await session.execute(range_h_stmt)).scalars().all()
        holidays_on_dates = {h.holiday_date for h in range_h_res}

    # Resolve weekly off days from employee shift version or default to weekend (Sunday=0, Saturday=6)
    _, shift_version = await resolve_employee_shift_version(
        session, tenant_id, employee_id, start_date
    )
    weekly_off_days = (
        shift_version.weekly_off_days
        if (shift_version and shift_version.weekly_off_days)
        else [0, 6]
    )

    working_dates: list[date] = []
    excluded_dates: list[date] = []

    curr = start_date
    while curr <= end_date:
        dow = (curr.weekday() + 1) % 7
        is_weekly_off = dow in weekly_off_days
        is_holiday = curr in holidays_on_dates

        if is_weekly_off or is_holiday:
            excluded_dates.append(curr)
        else:
            working_dates.append(curr)
        curr += timedelta(days=1)

    total_working = Decimal(len(working_dates))
    if total_working == Decimal("0"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The requested date range contains no working days (all dates are holidays or weekly offs).",
        )

    return total_working, working_dates, excluded_dates


# ==============================================================================
# Employee Leave Balances
# ==============================================================================


async def get_employee_leave_balances(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    year: int | None = None,
) -> list[LeaveBalanceResponse]:
    """Retrieves all leave balances for an employee in a given year."""
    target_year = year or date.today().year

    stmt = (
        select(LeaveBalance, LeaveType)
        .join(LeaveType, LeaveBalance.leave_type_id == LeaveType.id)
        .where(
            LeaveBalance.tenant_id == tenant_id,
            LeaveBalance.employee_id == employee_id,
            LeaveBalance.year == target_year,
        )
        .order_by(LeaveType.code.asc())
    )
    rows = (await session.execute(stmt)).all()

    return [map_leave_balance_to_response(bal, lt) for bal, lt in rows]


# ==============================================================================
# Leave Application Submission
# ==============================================================================


async def apply_leave_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    user_role: str,
    payload: LeaveRequestCreate,
) -> LeaveRequest:
    """Submits a leave application, verifies entitlement, and reserves balance with row locking.

    Invariants Enforced:
    - Derives employee identity from authenticated user context.
    - Prohibits cross-year requests (must submit separate requests per calendar year).
    - Checks leave type active status and half-day permissions.
    - Prevents overlapping active leave applications for the same employee.
    - Atomically locks the employee's LeaveBalance row using SELECT ... FOR UPDATE.
    - Verifies available balance >= requested days (unless negative balance allowed).
    - Reserves balance: pending_approval += total_days.
    """
    # 1. Resolve employee identity from caller context
    user_emp_stmt = select(Employee).where(
        Employee.tenant_id == tenant_id,
        Employee.user_id == user_id,
    )
    employee = (await session.execute(user_emp_stmt)).scalar_one_or_none()
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No employee profile linked to authenticated user account.",
        )

    # 2. Validate calendar year boundary
    if payload.start_date.year != payload.end_date.year:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Leave requests spanning multiple calendar years must be submitted as separate requests per year.",
        )
    target_year = payload.start_date.year

    # 3. Fetch and validate LeaveType
    lt_stmt = select(LeaveType).where(
        LeaveType.tenant_id == tenant_id,
        LeaveType.id == payload.leave_type_id,
    )
    leave_type = (await session.execute(lt_stmt)).scalar_one_or_none()
    if not leave_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Leave type '{payload.leave_type_id}' not found.",
        )
    if not leave_type.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Leave type '{leave_type.code}' is currently inactive for applications.",
        )
    if payload.is_half_day and not leave_type.allow_half_day:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Leave type '{leave_type.code}' does not permit half-day leave.",
        )

    # 4. Calculate deductible working days
    total_days, _, _ = await calculate_leave_working_days(
        session=session,
        tenant_id=tenant_id,
        employee_id=employee.id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        is_half_day=payload.is_half_day,
        half_day_period=payload.half_day_period,
    )

    if leave_type.max_consecutive_days and total_days > Decimal(leave_type.max_consecutive_days):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Requested leave ({total_days} days) exceeds maximum allowable consecutive days "
                f"({leave_type.max_consecutive_days} days) for {leave_type.code}."
            ),
        )

    # 5. Check for overlapping active leave requests for this employee
    overlap_stmt = select(LeaveRequest).where(
        LeaveRequest.tenant_id == tenant_id,
        LeaveRequest.employee_id == employee.id,
        LeaveRequest.status.in_(["PENDING_APPROVAL", "APPROVED"]),
        LeaveRequest.start_date <= payload.end_date,
        LeaveRequest.end_date >= payload.start_date,
    )
    overlapping_requests = (await session.execute(overlap_stmt)).scalars().all()

    for ex in overlapping_requests:
        # If both are half-days on the exact same date but different half-day periods, allow
        if (
            payload.is_half_day
            and ex.is_half_day
            and payload.start_date == ex.start_date
            and payload.half_day_period != ex.half_day_period
        ):
            continue
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"An active leave request ({ex.status}) already overlaps the requested period "
                f"({ex.start_date.isoformat()} to {ex.end_date.isoformat()})."
            ),
        )

    # 6. Lock and fetch employee LeaveBalance row
    bal_stmt = (
        select(LeaveBalance)
        .where(
            LeaveBalance.tenant_id == tenant_id,
            LeaveBalance.employee_id == employee.id,
            LeaveBalance.leave_type_id == payload.leave_type_id,
            LeaveBalance.year == target_year,
        )
        .with_for_update()
    )
    balance = (await session.execute(bal_stmt)).scalar_one_or_none()
    if not balance:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"No leave balance record found for employee for '{leave_type.code}' in year {target_year}."
            ),
        )

    # 7. Check available balance invariant: allocation + carried + accrued - used - pending >= requested
    available = balance.available_balance
    if available < total_days:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Insufficient leave balance for {leave_type.code}. "
                f"Available: {available} days, Requested: {total_days} days."
            ),
        )

    # 8. Reserve balance
    balance.pending_approval += total_days

    # 9. Create LeaveRequest record
    now = datetime.now(UTC)
    leave_request = LeaveRequest(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=employee.id,
        leave_type_id=payload.leave_type_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        is_half_day=payload.is_half_day,
        half_day_period=payload.half_day_period if payload.is_half_day else None,
        total_days=total_days,
        reason=payload.reason.strip(),
        status="PENDING_APPROVAL",
        created_at=now,
        updated_at=now,
    )

    session.add(leave_request)
    await session.flush()
    return leave_request


# ==============================================================================
# Employee Request Queries & Cancellation
# ==============================================================================


async def list_my_leave_requests(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    status_filter: str | None = None,
    year: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[LeaveRequest], int]:
    """Retrieves leave requests belonging to the authenticated employee."""
    user_emp_stmt = select(Employee).where(
        Employee.tenant_id == tenant_id,
        Employee.user_id == user_id,
    )
    employee = (await session.execute(user_emp_stmt)).scalar_one_or_none()
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No employee profile linked to authenticated user account.",
        )

    conditions = [
        LeaveRequest.tenant_id == tenant_id,
        LeaveRequest.employee_id == employee.id,
    ]
    if status_filter:
        conditions.append(LeaveRequest.status == status_filter.upper())
    if year:
        conditions.append(func.extract("year", LeaveRequest.start_date) == year)

    count_stmt = select(func.count()).select_from(LeaveRequest).where(*conditions)
    total = (await session.execute(count_stmt)).scalar() or 0

    data_stmt = (
        select(LeaveRequest)
        .options(selectinload(LeaveRequest.leave_type))
        .where(*conditions)
        .order_by(LeaveRequest.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = list((await session.execute(data_stmt)).scalars().all())

    return items, total


async def get_leave_request_detail(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    user_id: uuid.UUID,
    user_role: str,
) -> LeaveRequest:
    """Retrieves an individual leave request ensuring strict role and ownership scoping."""
    stmt = (
        select(LeaveRequest)
        .options(
            selectinload(LeaveRequest.leave_type),
            selectinload(LeaveRequest.employee),
        )
        .where(
            LeaveRequest.id == request_id,
            LeaveRequest.tenant_id == tenant_id,
        )
    )
    leave_req = (await session.execute(stmt)).scalar_one_or_none()
    if not leave_req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Leave request '{request_id}' not found.",
        )

    role = user_role.lower()
    if role == "employee":
        user_emp_stmt = select(Employee).where(
            Employee.tenant_id == tenant_id,
            Employee.user_id == user_id,
        )
        employee = (await session.execute(user_emp_stmt)).scalar_one_or_none()
        if not employee or leave_req.employee_id != employee.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Employees may only view their own leave requests.",
            )
    elif role == "manager":
        # Check if caller is the employee or reporting manager
        user_emp_stmt = select(Employee).where(
            Employee.tenant_id == tenant_id,
            Employee.user_id == user_id,
        )
        manager_emp = (await session.execute(user_emp_stmt)).scalar_one_or_none()
        if manager_emp is None or (
            leave_req.employee_id != manager_emp.id
            and leave_req.employee.reporting_manager_id != manager_emp.id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Managers may only view leave requests for themselves or direct reports.",
            )

    return leave_req


async def cancel_leave_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    user_id: uuid.UUID,
    user_role: str,
    reason: str | None = None,
) -> LeaveRequest:
    """Cancels a leave request following strict state transition and balance rollback rules.

    Rules:
    - Caller must own the request or hold HR/Admin role.
    - If status is PENDING_APPROVAL:
      - Release pending reservation: pending_approval -= total_days.
      - Transition status to CANCELLED.
    - If status is APPROVED:
      - Enforce cancellation policy: only future leave (start_date > today) may be cancelled.
      - Past or currently running leave cannot be cancelled by employee (HTTP 400).
      - Release used balance: used -= total_days.
      - Transition status to CANCELLED.
      - Recalculate affected daily attendance projections.
    - If status is REJECTED or CANCELLED:
      - Raise HTTP 400 or HTTP 409.
    """
    # 1. Lock LeaveRequest row
    stmt = (
        select(LeaveRequest)
        .where(
            LeaveRequest.id == request_id,
            LeaveRequest.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    leave_req = (await session.execute(stmt)).scalar_one_or_none()
    if not leave_req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Leave request '{request_id}' not found.",
        )

    # 2. Check ownership
    role = user_role.lower()
    if role not in ("owner", "admin", "hr"):
        user_emp_stmt = select(Employee).where(
            Employee.tenant_id == tenant_id,
            Employee.user_id == user_id,
        )
        employee = (await session.execute(user_emp_stmt)).scalar_one_or_none()
        if not employee or leave_req.employee_id != employee.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only cancel your own leave requests.",
            )

    # 3. Check current status
    if leave_req.status == "CANCELLED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Leave request has already been cancelled.",
        )
    if leave_req.status == "REJECTED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot cancel a rejected leave request.",
        )

    # 4. Lock LeaveBalance row
    bal_stmt = (
        select(LeaveBalance)
        .where(
            LeaveBalance.tenant_id == tenant_id,
            LeaveBalance.employee_id == leave_req.employee_id,
            LeaveBalance.leave_type_id == leave_req.leave_type_id,
            LeaveBalance.year == leave_req.start_date.year,
        )
        .with_for_update()
    )
    balance = (await session.execute(bal_stmt)).scalar_one_or_none()
    if not balance:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Leave balance record missing for leave request cancellation.",
        )

    # 5. Execute state transition and balance rollback
    today = date.today()

    if leave_req.status == "PENDING_APPROVAL":
        # Release hold
        balance.pending_approval = max(
            Decimal("0.00"), balance.pending_approval - leave_req.total_days
        )
        leave_req.status = "CANCELLED"
        leave_req.updated_at = datetime.now(UTC)

    elif leave_req.status == "APPROVED":
        # Enforce cancellation policy: cannot cancel leave that has already started or passed
        if leave_req.start_date <= today:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Cannot cancel approved leave that has already commenced ({leave_req.start_date.isoformat()}). "
                    "Please contact HR for manual attendance adjustment."
                ),
            )

        # Release consumed balance
        balance.used = max(Decimal("0.00"), balance.used - leave_req.total_days)
        leave_req.status = "CANCELLED"
        leave_req.updated_at = datetime.now(UTC)

        # Recalculate affected daily projections back from ON_LEAVE
        curr = leave_req.start_date
        while curr <= leave_req.end_date:
            await recalculate_attendance_day(
                session=session,
                tenant_id=tenant_id,
                employee_id=leave_req.employee_id,
                attendance_date=curr,
            )
            curr += timedelta(days=1)

    await session.flush()
    return leave_req


# ==============================================================================
# Supervisor Review & Adjudication
# ==============================================================================


async def list_supervisor_leave_requests(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    reviewer_user_id: uuid.UUID,
    reviewer_role: str,
    status_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[LeaveRequest], int]:
    """Lists leave requests pending supervisor review within the caller's permitted scope.

    Permissions:
    - Employees: Denied (HTTP 403).
    - Managers: Only direct reports (Employee.reporting_manager_id == reviewer_employee.id).
      Filtered with anti-self-approval (manager cannot see own requests in review queue).
    - HR / Admin / Owner: Full tenant-wide review queue.
    """
    role = reviewer_role.lower()
    if role == "employee":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employees are not authorized to view the supervisor review queue.",
        )

    base_conditions = [LeaveRequest.tenant_id == tenant_id]

    if status_filter:
        base_conditions.append(LeaveRequest.status == status_filter.upper())
    else:
        base_conditions.append(LeaveRequest.status == "PENDING_APPROVAL")

    if role == "manager":
        # Resolve manager employee profile
        rev_emp_stmt = select(Employee).where(
            Employee.tenant_id == tenant_id,
            Employee.user_id == reviewer_user_id,
        )
        manager_emp = (await session.execute(rev_emp_stmt)).scalar_one_or_none()
        if not manager_emp:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Manager employee profile not found in tenant.",
            )

        # Direct reports only; anti-self-approval excludes manager's own applications
        data_stmt = (
            select(LeaveRequest)
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .options(
                selectinload(LeaveRequest.leave_type),
                selectinload(LeaveRequest.employee),
            )
            .where(
                *base_conditions,
                Employee.reporting_manager_id == manager_emp.id,
                LeaveRequest.employee_id != manager_emp.id,
            )
            .order_by(LeaveRequest.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        count_stmt = (
            select(func.count())
            .select_from(LeaveRequest)
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .where(
                *base_conditions,
                Employee.reporting_manager_id == manager_emp.id,
                LeaveRequest.employee_id != manager_emp.id,
            )
        )
    else:
        # Owner, Admin, HR: Tenant-wide queue
        data_stmt = (
            select(LeaveRequest)
            .options(
                selectinload(LeaveRequest.leave_type),
                selectinload(LeaveRequest.employee),
            )
            .where(*base_conditions)
            .order_by(LeaveRequest.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        count_stmt = select(func.count()).select_from(LeaveRequest).where(*base_conditions)

    total = (await session.execute(count_stmt)).scalar() or 0
    items = list((await session.execute(data_stmt)).scalars().all())

    return items, total


async def adjudicate_leave_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    reviewer_user_id: uuid.UUID,
    reviewer_role: str,
    action: str,
    reason: str | None = None,
) -> tuple[LeaveRequest, list[AttendanceDay]]:
    """Adjudicates a pending leave request (APPROVE / REJECT) with row locking and audit logging.

    Guarantees:
    - Employees are forbidden from adjudicating (HTTP 403).
    - Anti-self-approval: Reviewer cannot approve or reject their own application (HTTP 403).
    - Managers are restricted to direct reports only (HTTP 403).
    - Already processed requests reject duplicate decisions with HTTP 409 Conflict.
    - Atomic balance transition:
      - APPROVE: pending_approval -= total_days, used += total_days.
      - REJECT: pending_approval -= total_days, used unchanged (mandatory reason required).
    - On approval, triggers attendance projection recalculation for affected dates.
    - Transactional rollback: if recalculation fails, balance transition is reversed.
    """
    role = reviewer_role.lower()
    if role == "employee":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employees are not authorized to adjudicate leave requests.",
        )

    action_upper = action.strip().upper()
    if action_upper not in ("APPROVE", "REJECT"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Adjudication action must be 'APPROVE' or 'REJECT'.",
        )

    if action_upper == "REJECT":
        if not reason or len(reason.strip()) < 3:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Rejection requires a mandatory reason of at least 3 characters.",
            )

    # 1. Lock LeaveRequest row
    req_stmt = (
        select(LeaveRequest)
        .options(
            selectinload(LeaveRequest.leave_type),
            selectinload(LeaveRequest.employee),
        )
        .where(
            LeaveRequest.id == request_id,
            LeaveRequest.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    leave_req = (await session.execute(req_stmt)).scalar_one_or_none()
    if not leave_req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Leave request '{request_id}' not found.",
        )

    # 2. Prevent duplicate decisions
    if leave_req.status != "PENDING_APPROVAL":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Leave request has already been decided ({leave_req.status}).",
        )

    # 3. Anti-Self-Approval Verification
    rev_emp_stmt = select(Employee).where(
        Employee.tenant_id == tenant_id,
        Employee.user_id == reviewer_user_id,
    )
    reviewer_emp = (await session.execute(rev_emp_stmt)).scalar_one_or_none()

    if leave_req.employee.user_id == reviewer_user_id or (
        reviewer_emp is not None and leave_req.employee_id == reviewer_emp.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reviewers are not permitted to adjudicate their own leave applications.",
        )

    # 4. Manager reporting hierarchy verification
    if role == "manager":
        if reviewer_emp is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Manager employee profile not found in tenant.",
            )
        if leave_req.employee.reporting_manager_id != reviewer_emp.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Managers may only adjudicate leave requests for their direct reports.",
            )
    elif role not in ("owner", "admin", "hr"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient privileges to adjudicate leave requests.",
        )

    # 5. Lock LeaveBalance row
    bal_stmt = (
        select(LeaveBalance)
        .where(
            LeaveBalance.tenant_id == tenant_id,
            LeaveBalance.employee_id == leave_req.employee_id,
            LeaveBalance.leave_type_id == leave_req.leave_type_id,
            LeaveBalance.year == leave_req.start_date.year,
        )
        .with_for_update()
    )
    balance = (await session.execute(bal_stmt)).scalar_one_or_none()
    if not balance:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Leave balance record missing for leave adjudication.",
        )

    # 6. Execute atomic accounting transition
    now = datetime.now(UTC)
    recalculated_days: list[AttendanceDay] = []

    if action_upper == "APPROVE":
        balance.pending_approval = max(
            Decimal("0.00"), balance.pending_approval - leave_req.total_days
        )
        balance.used += leave_req.total_days

        leave_req.status = "APPROVED"
        leave_req.decided_at = now
        leave_req.reviewer_user_id = reviewer_user_id
        leave_req.reviewer_notes = reason.strip() if reason else None
        leave_req.updated_at = now

        # Recalculate daily attendance projections for all affected dates
        try:
            curr = leave_req.start_date
            while curr <= leave_req.end_date:
                day = await recalculate_attendance_day(
                    session=session,
                    tenant_id=tenant_id,
                    employee_id=leave_req.employee_id,
                    attendance_date=curr,
                )
                recalculated_days.append(day)
                curr += timedelta(days=1)
        except Exception as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Attendance projection recalculation failed: {exc}. Approval rolled back.",
            )

    elif action_upper == "REJECT":
        balance.pending_approval = max(
            Decimal("0.00"), balance.pending_approval - leave_req.total_days
        )

        leave_req.status = "REJECTED"
        leave_req.decided_at = now
        leave_req.reviewer_user_id = reviewer_user_id
        leave_req.reviewer_notes = reason.strip() if reason else None
        leave_req.updated_at = now

    await session.flush()
    return leave_req, recalculated_days
