"""FastAPI route handlers for Phase 9: Leave Types, Holiday Calendars, and Holidays."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.auth.dependencies import (
    AuthenticatedContext,
    get_authenticated_context,
    require_permission,
)
from services.api.auth.permissions import Permission, UserRole
from services.api.database import get_db
from services.api.employees.models import Employee
from services.api.leave.holiday_service import (
    create_holiday_calendar,
    create_holiday_entry,
    delete_holiday_calendar,
    delete_holiday_entry,
    get_holiday_calendar,
    get_upcoming_holidays_for_employee,
    list_holiday_calendars,
    list_holidays_in_calendar,
    map_calendar_to_response,
    map_holiday_to_response,
    update_holiday_calendar,
    update_holiday_entry,
)
from services.api.leave.leave_request_service import (
    adjudicate_leave_request,
    apply_leave_request,
    cancel_leave_request,
    get_employee_leave_balances,
    get_leave_request_detail,
    list_my_leave_requests,
    list_supervisor_leave_requests,
    map_leave_request_to_response,
)
from services.api.leave.leave_type_service import (
    create_leave_type,
    delete_leave_type,
    get_leave_type,
    list_leave_types,
    map_leave_type_to_response,
    update_leave_type,
)
from services.api.leave.overtime_service import (
    adjudicate_overtime_record,
    create_overtime_rule,
    delete_overtime_rule,
    get_overtime_record_detail,
    get_overtime_rule,
    list_overtime_records,
    list_overtime_rules,
    map_overtime_record_to_response,
    map_overtime_rule_to_response,
    update_overtime_rule,
)
from services.api.leave.schemas import (
    HolidayCalendarCreateRequest,
    HolidayCalendarListResponse,
    HolidayCalendarResponse,
    HolidayCalendarUpdateRequest,
    HolidayCreateRequest,
    HolidayListResponse,
    HolidayResponse,
    HolidayUpdateRequest,
    LeaveBalanceListResponse,
    LeaveRequestCancelRequest,
    LeaveRequestCreate,
    LeaveRequestDecisionRequest,
    LeaveRequestListResponse,
    LeaveRequestResponse,
    LeaveTypeCreateRequest,
    LeaveTypeListResponse,
    LeaveTypeResponse,
    LeaveTypeUpdateRequest,
    OvertimeDecisionRequest,
    OvertimeRecordListResponse,
    OvertimeRecordResponse,
    OvertimeRuleCreateRequest,
    OvertimeRuleListResponse,
    OvertimeRuleResponse,
    OvertimeRuleUpdateRequest,
    UpcomingHolidaysResponse,
)

leave_router = APIRouter(prefix="/leave", tags=["Leave Management"])
holidays_router = APIRouter(prefix="/holidays", tags=["Holiday Calendars"])
overtime_router = APIRouter(prefix="/overtime", tags=["Overtime Rules & Records"])


# ==============================================================================
# Leave Types Endpoints
# ==============================================================================


@leave_router.post(
    "/types",
    response_model=LeaveTypeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new leave type",
    dependencies=[Depends(require_permission(Permission.MANAGE_LEAVE_TYPES))],
)
async def create_leave_type_endpoint(
    payload: LeaveTypeCreateRequest,
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    db: AsyncSession = Depends(get_db),
) -> LeaveTypeResponse:
    """Configures a new organization leave type with quota, rollover, and approval rules."""
    leave_type = await create_leave_type(session=db, tenant_id=ctx.tenant.id, payload=payload)
    await db.commit()
    await db.refresh(leave_type)
    return map_leave_type_to_response(leave_type)


@leave_router.get(
    "/types",
    response_model=LeaveTypeListResponse,
    summary="List organization leave types",
    dependencies=[Depends(require_permission(Permission.VIEW_LEAVE_TYPES))],
)
async def list_leave_types_endpoint(
    search: str | None = Query(default=None, description="Search by name or code"),
    is_active: bool | None = Query(default=None, description="Filter active status"),
    is_paid: bool | None = Query(default=None, description="Filter paid status"),
    limit: int = Query(default=50, ge=1, le=100, description="Items per page"),
    offset: int = Query(default=0, ge=0, description="Page offset"),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    db: AsyncSession = Depends(get_db),
) -> LeaveTypeListResponse:
    """Retrieves paginated leave types configured for the tenant."""
    items, total = await list_leave_types(
        session=db,
        tenant_id=ctx.tenant.id,
        search=search,
        is_active=is_active,
        is_paid=is_paid,
        limit=limit,
        offset=offset,
    )
    return LeaveTypeListResponse(
        items=[map_leave_type_to_response(lt) for lt in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@leave_router.get(
    "/types/{leave_type_id}",
    response_model=LeaveTypeResponse,
    summary="Retrieve leave type by ID",
    dependencies=[Depends(require_permission(Permission.VIEW_LEAVE_TYPES))],
)
async def get_leave_type_endpoint(
    leave_type_id: uuid.UUID,
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    db: AsyncSession = Depends(get_db),
) -> LeaveTypeResponse:
    """Retrieves details of a specific leave type within the tenant."""
    leave_type = await get_leave_type(
        session=db,
        tenant_id=ctx.tenant.id,
        leave_type_id=leave_type_id,
    )
    return map_leave_type_to_response(leave_type)


@leave_router.patch(
    "/types/{leave_type_id}",
    response_model=LeaveTypeResponse,
    summary="Update leave type configuration",
    dependencies=[Depends(require_permission(Permission.MANAGE_LEAVE_TYPES))],
)
async def update_leave_type_endpoint(
    leave_type_id: uuid.UUID,
    payload: LeaveTypeUpdateRequest,
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    db: AsyncSession = Depends(get_db),
) -> LeaveTypeResponse:
    """Updates an existing leave type's parameters (e.g. name, quota limits, active status)."""
    updated = await update_leave_type(
        session=db,
        tenant_id=ctx.tenant.id,
        leave_type_id=leave_type_id,
        payload=payload,
    )
    await db.commit()
    await db.refresh(updated)
    return map_leave_type_to_response(updated)


@leave_router.delete(
    "/types/{leave_type_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a leave type",
    dependencies=[Depends(require_permission(Permission.MANAGE_LEAVE_TYPES))],
)
async def delete_leave_type_endpoint(
    leave_type_id: uuid.UUID,
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Deletes a leave type. Fails with HTTP 409 if active employee balances or requests exist."""
    await delete_leave_type(session=db, tenant_id=ctx.tenant.id, leave_type_id=leave_type_id)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==============================================================================
# Leave Balances & Leave Requests Endpoints
# ==============================================================================


@leave_router.get(
    "/balances/my",
    response_model=LeaveBalanceListResponse,
    summary="Get authenticated employee's leave balances",
    dependencies=[Depends(require_permission(Permission.APPLY_LEAVE))],
)
async def get_my_balances_endpoint(
    year: int | None = Query(default=None, ge=2000, le=2100, description="Calendar year"),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    db: AsyncSession = Depends(get_db),
) -> LeaveBalanceListResponse:
    """Retrieves current leave balance entitlement, usage, and available days for caller."""
    user_emp_stmt = select(Employee).where(
        Employee.tenant_id == ctx.tenant.id,
        Employee.user_id == ctx.user.id,
    )
    employee = (await db.execute(user_emp_stmt)).scalar_one_or_none()
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No employee profile linked to authenticated user account.",
        )

    balances = await get_employee_leave_balances(
        session=db,
        tenant_id=ctx.tenant.id,
        employee_id=employee.id,
        year=year,
    )
    return LeaveBalanceListResponse(items=balances, total=len(balances))


@leave_router.post(
    "/requests",
    response_model=LeaveRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Apply for leave",
    dependencies=[Depends(require_permission(Permission.APPLY_LEAVE))],
)
async def submit_leave_request_endpoint(
    payload: LeaveRequestCreate,
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    db: AsyncSession = Depends(get_db),
) -> LeaveRequestResponse:
    """Submits a leave request with balance reservation and date validation."""
    leave_req = await apply_leave_request(
        session=db,
        tenant_id=ctx.tenant.id,
        user_id=ctx.user.id,
        user_role=ctx.user.role,
        payload=payload,
    )
    await db.commit()
    await db.refresh(leave_req)
    return map_leave_request_to_response(leave_req)


@leave_router.get(
    "/requests/my",
    response_model=LeaveRequestListResponse,
    summary="List authenticated employee's own leave requests",
    dependencies=[Depends(require_permission(Permission.VIEW_LEAVE_REQUESTS))],
)
async def list_my_leave_requests_endpoint(
    status_filter: str | None = Query(default=None, alias="status", description="Filter by status"),
    year: int | None = Query(
        default=None, ge=2000, le=2100, description="Filter by start date year"
    ),
    limit: int = Query(default=50, ge=1, le=100, description="Items per page"),
    offset: int = Query(default=0, ge=0, description="Page offset"),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    db: AsyncSession = Depends(get_db),
) -> LeaveRequestListResponse:
    """Retrieves paginated leave requests submitted by the caller."""
    items, total = await list_my_leave_requests(
        session=db,
        tenant_id=ctx.tenant.id,
        user_id=ctx.user.id,
        status_filter=status_filter,
        year=year,
        limit=limit,
        offset=offset,
    )
    return LeaveRequestListResponse(
        items=[map_leave_request_to_response(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@leave_router.get(
    "/requests",
    response_model=LeaveRequestListResponse,
    summary="List leave requests for supervisor review",
    dependencies=[Depends(require_permission(Permission.APPROVE_LEAVE))],
)
async def list_supervisor_leave_requests_endpoint(
    status_filter: str | None = Query(
        default=None, alias="status", description="Filter by status (default: PENDING_APPROVAL)"
    ),
    limit: int = Query(default=50, ge=1, le=100, description="Items per page"),
    offset: int = Query(default=0, ge=0, description="Page offset"),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    db: AsyncSession = Depends(get_db),
) -> LeaveRequestListResponse:
    """Lists leave requests pending supervisor adjudication within caller's managerial authority."""
    items, total = await list_supervisor_leave_requests(
        session=db,
        tenant_id=ctx.tenant.id,
        reviewer_user_id=ctx.user.id,
        reviewer_role=ctx.user.role,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )
    return LeaveRequestListResponse(
        items=[map_leave_request_to_response(r, emp=r.employee, lt=r.leave_type) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@leave_router.get(
    "/requests/{request_id}",
    response_model=LeaveRequestResponse,
    summary="Retrieve leave request by ID",
    dependencies=[Depends(require_permission(Permission.VIEW_LEAVE_REQUESTS))],
)
async def get_leave_request_endpoint(
    request_id: uuid.UUID,
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    db: AsyncSession = Depends(get_db),
) -> LeaveRequestResponse:
    """Retrieves single leave request details with ownership and manager scope checks."""
    req = await get_leave_request_detail(
        session=db,
        tenant_id=ctx.tenant.id,
        request_id=request_id,
        user_id=ctx.user.id,
        user_role=ctx.user.role,
    )
    return map_leave_request_to_response(req, emp=req.employee, lt=req.leave_type)


@leave_router.post(
    "/requests/{request_id}/cancel",
    response_model=LeaveRequestResponse,
    summary="Cancel a leave request",
    dependencies=[Depends(require_permission(Permission.APPLY_LEAVE))],
)
async def cancel_leave_request_endpoint(
    request_id: uuid.UUID,
    payload: LeaveRequestCancelRequest | None = None,
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    db: AsyncSession = Depends(get_db),
) -> LeaveRequestResponse:
    """Cancels a pending or future approved leave request, executing balance rollback."""
    reason = payload.reason if payload else None
    cancelled_req = await cancel_leave_request(
        session=db,
        tenant_id=ctx.tenant.id,
        request_id=request_id,
        user_id=ctx.user.id,
        user_role=ctx.user.role,
        reason=reason,
    )
    await db.commit()
    await db.refresh(cancelled_req)
    return map_leave_request_to_response(cancelled_req)


@leave_router.post(
    "/requests/{request_id}/decision",
    response_model=LeaveRequestResponse,
    summary="Adjudicate leave request (Approve/Reject)",
    dependencies=[Depends(require_permission(Permission.APPROVE_LEAVE))],
)
async def adjudicate_leave_request_endpoint(
    request_id: uuid.UUID,
    payload: LeaveRequestDecisionRequest,
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    db: AsyncSession = Depends(get_db),
) -> LeaveRequestResponse:
    """Approves or rejects a leave request, atomically transitioning balances and recalculating projections."""
    decided_req, _ = await adjudicate_leave_request(
        session=db,
        tenant_id=ctx.tenant.id,
        request_id=request_id,
        reviewer_user_id=ctx.user.id,
        reviewer_role=ctx.user.role,
        action=payload.action,
        reason=payload.reason,
    )
    await db.commit()
    await db.refresh(decided_req)
    return map_leave_request_to_response(
        decided_req, emp=decided_req.employee, lt=decided_req.leave_type
    )


# ==============================================================================
# Holiday Calendars Endpoints
# ==============================================================================


@holidays_router.post(
    "/calendars",
    response_model=HolidayCalendarResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new annual holiday calendar",
    dependencies=[Depends(require_permission(Permission.MANAGE_HOLIDAYS))],
)
async def create_calendar_endpoint(
    payload: HolidayCalendarCreateRequest,
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    db: AsyncSession = Depends(get_db),
) -> HolidayCalendarResponse:
    """Creates a holiday calendar with optional workplace location or department scoping."""
    calendar = await create_holiday_calendar(
        session=db,
        tenant_id=ctx.tenant.id,
        payload=payload,
    )
    await db.commit()
    await db.refresh(calendar)
    return map_calendar_to_response(calendar, holidays=[], holiday_count=0)


@holidays_router.get(
    "/calendars",
    response_model=HolidayCalendarListResponse,
    summary="List holiday calendars",
    dependencies=[Depends(require_permission(Permission.VIEW_HOLIDAYS))],
)
async def list_calendars_endpoint(
    year: int | None = Query(default=None, ge=2000, le=2100, description="Filter by year"),
    location_id: uuid.UUID | None = Query(default=None, description="Filter by workplace"),
    department_id: uuid.UUID | None = Query(default=None, description="Filter by department"),
    is_default: bool | None = Query(default=None, description="Filter default calendars"),
    limit: int = Query(default=50, ge=1, le=100, description="Items per page"),
    offset: int = Query(default=0, ge=0, description="Page offset"),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    db: AsyncSession = Depends(get_db),
) -> HolidayCalendarListResponse:
    """Retrieves paginated holiday calendars with current holiday counts."""
    items, total = await list_holiday_calendars(
        session=db,
        tenant_id=ctx.tenant.id,
        year=year,
        location_id=location_id,
        department_id=department_id,
        is_default=is_default,
        limit=limit,
        offset=offset,
    )
    return HolidayCalendarListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@holidays_router.get(
    "/calendars/{calendar_id}",
    response_model=HolidayCalendarResponse,
    summary="Retrieve holiday calendar by ID with all entries",
    dependencies=[Depends(require_permission(Permission.VIEW_HOLIDAYS))],
)
async def get_calendar_endpoint(
    calendar_id: uuid.UUID,
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    db: AsyncSession = Depends(get_db),
) -> HolidayCalendarResponse:
    """Retrieves details of a calendar including all scheduled holidays."""
    calendar = await get_holiday_calendar(
        session=db,
        tenant_id=ctx.tenant.id,
        calendar_id=calendar_id,
    )
    return map_calendar_to_response(calendar, holidays=list(calendar.holidays))


@holidays_router.patch(
    "/calendars/{calendar_id}",
    response_model=HolidayCalendarResponse,
    summary="Update holiday calendar header",
    dependencies=[Depends(require_permission(Permission.MANAGE_HOLIDAYS))],
)
async def update_calendar_endpoint(
    calendar_id: uuid.UUID,
    payload: HolidayCalendarUpdateRequest,
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    db: AsyncSession = Depends(get_db),
) -> HolidayCalendarResponse:
    """Updates calendar metadata (name, year, location, department, default flag)."""
    updated = await update_holiday_calendar(
        session=db,
        tenant_id=ctx.tenant.id,
        calendar_id=calendar_id,
        payload=payload,
    )
    await db.commit()
    await db.refresh(updated)
    return map_calendar_to_response(updated, holidays=list(updated.holidays))


@holidays_router.delete(
    "/calendars/{calendar_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a holiday calendar",
    dependencies=[Depends(require_permission(Permission.MANAGE_HOLIDAYS))],
)
async def delete_calendar_endpoint(
    calendar_id: uuid.UUID,
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Deletes a holiday calendar and all associated holidays."""
    await delete_holiday_calendar(
        session=db,
        tenant_id=ctx.tenant.id,
        calendar_id=calendar_id,
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==============================================================================
# Holiday Entries within Calendar
# ==============================================================================


@holidays_router.post(
    "/calendars/{calendar_id}/holidays",
    response_model=HolidayResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a holiday to a calendar",
    dependencies=[Depends(require_permission(Permission.MANAGE_HOLIDAYS))],
)
async def create_holiday_entry_endpoint(
    calendar_id: uuid.UUID,
    payload: HolidayCreateRequest,
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    db: AsyncSession = Depends(get_db),
) -> HolidayResponse:
    """Adds a holiday date entry to the calendar."""
    entry = await create_holiday_entry(
        session=db,
        tenant_id=ctx.tenant.id,
        calendar_id=calendar_id,
        payload=payload,
    )
    await db.commit()
    await db.refresh(entry)
    return map_holiday_to_response(entry)


@holidays_router.get(
    "/calendars/{calendar_id}/holidays",
    response_model=HolidayListResponse,
    summary="List holidays in a calendar",
    dependencies=[Depends(require_permission(Permission.VIEW_HOLIDAYS))],
)
async def list_calendar_holidays_endpoint(
    calendar_id: uuid.UUID,
    start_date: date | None = Query(default=None, description="Start date filter"),
    end_date: date | None = Query(default=None, description="End date filter"),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    db: AsyncSession = Depends(get_db),
) -> HolidayListResponse:
    """Lists holidays scheduled in the calendar, optionally filtered by date range."""
    entries = await list_holidays_in_calendar(
        session=db,
        tenant_id=ctx.tenant.id,
        calendar_id=calendar_id,
        start_date=start_date,
        end_date=end_date,
    )
    return HolidayListResponse(
        items=[map_holiday_to_response(h) for h in entries],
        total=len(entries),
    )


@holidays_router.patch(
    "/calendars/{calendar_id}/holidays/{holiday_id}",
    response_model=HolidayResponse,
    summary="Update a holiday entry",
    dependencies=[Depends(require_permission(Permission.MANAGE_HOLIDAYS))],
)
async def update_holiday_entry_endpoint(
    calendar_id: uuid.UUID,
    holiday_id: uuid.UUID,
    payload: HolidayUpdateRequest,
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    db: AsyncSession = Depends(get_db),
) -> HolidayResponse:
    """Updates a holiday entry's details."""
    updated = await update_holiday_entry(
        session=db,
        tenant_id=ctx.tenant.id,
        calendar_id=calendar_id,
        holiday_id=holiday_id,
        payload=payload,
    )
    await db.commit()
    await db.refresh(updated)
    return map_holiday_to_response(updated)


@holidays_router.delete(
    "/calendars/{calendar_id}/holidays/{holiday_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a holiday entry",
    dependencies=[Depends(require_permission(Permission.MANAGE_HOLIDAYS))],
)
async def delete_holiday_entry_endpoint(
    calendar_id: uuid.UUID,
    holiday_id: uuid.UUID,
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Deletes a holiday entry from the calendar."""
    await delete_holiday_entry(
        session=db,
        tenant_id=ctx.tenant.id,
        calendar_id=calendar_id,
        holiday_id=holiday_id,
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==============================================================================
# Employee Upcoming Holidays Inquiry
# ==============================================================================


@holidays_router.get(
    "/upcoming",
    response_model=UpcomingHolidaysResponse,
    summary="Query upcoming holidays for employee",
    dependencies=[Depends(require_permission(Permission.VIEW_HOLIDAYS))],
)
async def get_upcoming_holidays_endpoint(
    employee_id: uuid.UUID | None = Query(
        default=None,
        description="Target employee ID (Managers/HR/Admin only; Employees self-scoped)",
    ),
    start_date: date | None = Query(
        default=None,
        description="Start date for upcoming inquiry (defaults to today)",
    ),
    end_date: date | None = Query(
        default=None,
        description="End date for upcoming inquiry (defaults to end of year)",
    ),
    limit: int = Query(default=50, ge=1, le=100, description="Items per page"),
    offset: int = Query(default=0, ge=0, description="Page offset"),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    db: AsyncSession = Depends(get_db),
) -> UpcomingHolidaysResponse:
    """Retrieves upcoming holidays applicable to the authenticated employee using the authoritative
    hierarchical calendar resolution engine (Workplace Location -> Department -> Tenant Default).

    Guarantees:
    - Derives caller employee identity from user context.
    - Prevents employees from querying other employees' holiday calendars (HTTP 403).
    - Falls back to tenant default calendar if caller has no employee profile.
    """
    today = date.today()
    q_start = start_date if start_date is not None else today
    q_end = end_date if end_date is not None else date(today.year, 12, 31)

    # 1. Resolve employee identity and verify access
    target_emp_id: uuid.UUID | None = None

    # Fetch employee record linked to current user
    user_emp_stmt = select(Employee).where(
        Employee.tenant_id == ctx.tenant.id,
        Employee.user_id == ctx.user.id,
    )
    user_emp = (await db.execute(user_emp_stmt)).scalar_one_or_none()

    caller_role = ctx.user.role.lower()

    if caller_role == UserRole.EMPLOYEE:
        if not user_emp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Employee profile not found for authenticated user.",
            )
        if employee_id is not None and employee_id != user_emp.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Employees cannot query holiday schedules of other employees.",
            )
        target_emp_id = user_emp.id
    else:
        # Administrative / Manager roles
        if employee_id is not None:
            target_emp_id = employee_id
        elif user_emp is not None:
            target_emp_id = user_emp.id
        else:
            target_emp_id = None

    items, total, resolved_cal, source = await get_upcoming_holidays_for_employee(
        session=db,
        tenant_id=ctx.tenant.id,
        employee_id=target_emp_id,
        start_date=q_start,
        end_date=q_end,
        limit=limit,
        offset=offset,
    )

    return UpcomingHolidaysResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        resolved_calendar_id=resolved_cal.id if resolved_cal else None,
        resolved_calendar_name=resolved_cal.name if resolved_cal else None,
        resolution_source=source,
    )


# ==============================================================================
# Overtime Rules & Records Endpoints (Milestone 9.4)
# ==============================================================================


@overtime_router.post(
    "/rules",
    response_model=OvertimeRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new tenant overtime rule",
    dependencies=[Depends(require_permission(Permission.MANAGE_OVERTIME_RULES))],
)
async def create_overtime_rule_endpoint(
    payload: OvertimeRuleCreateRequest,
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    db: AsyncSession = Depends(get_db),
) -> OvertimeRuleResponse:
    """Configures a new overtime rule including thresholds, multipliers, and approval requirements."""
    rule = await create_overtime_rule(
        session=db,
        tenant_id=ctx.tenant.id,
        payload=payload,
    )
    await db.commit()
    await db.refresh(rule)
    return map_overtime_rule_to_response(rule)


@overtime_router.get(
    "/rules",
    response_model=OvertimeRuleListResponse,
    summary="List tenant overtime rules",
    dependencies=[Depends(require_permission(Permission.VIEW_OVERTIME_RULES))],
)
async def list_overtime_rules_endpoint(
    is_active: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    db: AsyncSession = Depends(get_db),
) -> OvertimeRuleListResponse:
    """Lists configured overtime rules for tenant with pagination."""
    items, total = await list_overtime_rules(
        session=db,
        tenant_id=ctx.tenant.id,
        is_active=is_active,
        limit=limit,
        offset=offset,
    )
    return OvertimeRuleListResponse(
        items=[map_overtime_rule_to_response(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@overtime_router.get(
    "/rules/{rule_id}",
    response_model=OvertimeRuleResponse,
    summary="Retrieve an overtime rule",
    dependencies=[Depends(require_permission(Permission.VIEW_OVERTIME_RULES))],
)
async def get_overtime_rule_endpoint(
    rule_id: uuid.UUID,
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    db: AsyncSession = Depends(get_db),
) -> OvertimeRuleResponse:
    """Retrieves single overtime rule configuration."""
    rule = await get_overtime_rule(
        session=db,
        tenant_id=ctx.tenant.id,
        rule_id=rule_id,
    )
    return map_overtime_rule_to_response(rule)


@overtime_router.patch(
    "/rules/{rule_id}",
    response_model=OvertimeRuleResponse,
    summary="Update an overtime rule",
    dependencies=[Depends(require_permission(Permission.MANAGE_OVERTIME_RULES))],
)
async def update_overtime_rule_endpoint(
    rule_id: uuid.UUID,
    payload: OvertimeRuleUpdateRequest,
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    db: AsyncSession = Depends(get_db),
) -> OvertimeRuleResponse:
    """Updates overtime rule parameters."""
    rule = await update_overtime_rule(
        session=db,
        tenant_id=ctx.tenant.id,
        rule_id=rule_id,
        payload=payload,
    )
    await db.commit()
    await db.refresh(rule)
    return map_overtime_rule_to_response(rule)


@overtime_router.delete(
    "/rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an overtime rule",
    dependencies=[Depends(require_permission(Permission.MANAGE_OVERTIME_RULES))],
)
async def delete_overtime_rule_endpoint(
    rule_id: uuid.UUID,
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Deletes an unreferenced overtime rule."""
    await delete_overtime_rule(
        session=db,
        tenant_id=ctx.tenant.id,
        rule_id=rule_id,
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@overtime_router.get(
    "/records",
    response_model=OvertimeRecordListResponse,
    summary="List overtime review queue (Supervisors / Admin)",
    dependencies=[Depends(require_permission(Permission.APPROVE_OVERTIME))],
)
async def list_overtime_records_endpoint(
    employee_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    overtime_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    db: AsyncSession = Depends(get_db),
) -> OvertimeRecordListResponse:
    """Queries overtime records for review queue. Managers see only direct reports."""
    items, total = await list_overtime_records(
        session=db,
        tenant_id=ctx.tenant.id,
        user_id=ctx.user.id,
        user_role=ctx.user.role,
        employee_id=employee_id,
        status_filter=status_filter,
        start_date=start_date,
        end_date=end_date,
        overtime_type=overtime_type,
        limit=limit,
        offset=offset,
    )
    return OvertimeRecordListResponse(
        items=[map_overtime_record_to_response(rec, emp) for rec, emp in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@overtime_router.get(
    "/records/my",
    response_model=OvertimeRecordListResponse,
    summary="List my personal overtime records",
    dependencies=[Depends(require_permission(Permission.VIEW_OVERTIME_RECORDS))],
)
async def list_my_overtime_records_endpoint(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    db: AsyncSession = Depends(get_db),
) -> OvertimeRecordListResponse:
    """Inquiry of authenticated employee's personal overtime records."""
    items, total = await list_overtime_records(
        session=db,
        tenant_id=ctx.tenant.id,
        user_id=ctx.user.id,
        user_role=UserRole.EMPLOYEE,
        status_filter=status_filter,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
    return OvertimeRecordListResponse(
        items=[map_overtime_record_to_response(rec, emp) for rec, emp in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@overtime_router.get(
    "/records/{record_id}",
    response_model=OvertimeRecordResponse,
    summary="Retrieve overtime record detail",
    dependencies=[Depends(require_permission(Permission.VIEW_OVERTIME_RECORDS))],
)
async def get_overtime_record_endpoint(
    record_id: uuid.UUID,
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    db: AsyncSession = Depends(get_db),
) -> OvertimeRecordResponse:
    """Retrieves single overtime record with RBAC scoping."""
    rec, emp = await get_overtime_record_detail(
        session=db,
        tenant_id=ctx.tenant.id,
        record_id=record_id,
        user_id=ctx.user.id,
        user_role=ctx.user.role,
    )
    return map_overtime_record_to_response(rec, emp)


@overtime_router.post(
    "/records/{record_id}/decision",
    response_model=OvertimeRecordResponse,
    summary="Adjudicate overtime record (Approve/Reject)",
    dependencies=[Depends(require_permission(Permission.APPROVE_OVERTIME))],
)
async def adjudicate_overtime_record_endpoint(
    record_id: uuid.UUID,
    payload: OvertimeDecisionRequest,
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    db: AsyncSession = Depends(get_db),
) -> OvertimeRecordResponse:
    """Adjudicates an overtime record with anti-self-approval and direct-report scoping."""
    record = await adjudicate_overtime_record(
        session=db,
        tenant_id=ctx.tenant.id,
        record_id=record_id,
        reviewer_user_id=ctx.user.id,
        reviewer_role=ctx.user.role,
        payload=payload,
    )
    await db.commit()
    await db.refresh(record)
    return map_overtime_record_to_response(record)
