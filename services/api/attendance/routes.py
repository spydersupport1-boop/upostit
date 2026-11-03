"""FastAPI route handlers for shift templates, immutable versions, and employee assignments."""

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.attendance.correction_service import (
    apply_attendance_correction,
    get_attendance_day_event_audit_trail,
    list_attendance_corrections,
)
from services.api.attendance.reconciliation import run_attendance_reconciliation
from services.api.attendance.schemas import (
    AttendanceCorrectionCreateRequest,
    AttendanceCorrectionListResponse,
    AttendanceCorrectionResponse,
    AttendanceCorrectionType,
    AttendanceDayListResponse,
    AttendanceDayResponse,
    AttendanceEventAuditListResponse,
    AttendanceEventListResponse,
    AttendanceEventResponse,
    AttendanceRecalculateRequest,
    PunchRequest,
    PunchResponse,
    ReconciliationRequest,
    ReconciliationResponse,
    ShiftAssignmentCreateRequest,
    ShiftAssignmentEndRequest,
    ShiftAssignmentResponse,
    ShiftAssignmentUpdateRequest,
    ShiftTemplateCreateRequest,
    ShiftTemplateDetailResponse,
    ShiftTemplateResponse,
    ShiftTemplateUpdateRequest,
    ShiftVersionCreateRequest,
    ShiftVersionResponse,
)
from services.api.attendance.service import (
    assign_shift_to_employee,
    create_shift_template,
    create_shift_version,
    deactivate_shift_template,
    end_shift_assignment,
    get_attendance_day,
    get_attendance_event,
    get_shift_template,
    list_attendance_days,
    list_attendance_events,
    list_shift_assignments,
    list_shift_templates,
    list_shift_versions,
    recalculate_attendance_day,
    record_punch,
    update_shift_assignment,
    update_shift_template,
)
from services.api.auth.dependencies import (
    AuthenticatedContext,
    get_authenticated_context,
    require_permission,
)
from services.api.auth.permissions import Permission
from services.api.database import get_db

shifts_router = APIRouter(prefix="/shifts", tags=["Shifts"])
router = shifts_router  # Backwards compatibility alias
attendance_router = APIRouter(prefix="/attendance", tags=["Attendance"])


# ==============================================================================
# Shift Templates
# ==============================================================================


@router.post(
    "",
    response_model=ShiftTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create shift template with initial Version 1",
    dependencies=[Depends(require_permission(Permission.MANAGE_SHIFTS))],
)
async def create_shift_endpoint(
    payload: ShiftTemplateCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
) -> ShiftTemplateResponse:
    """Creates a new shift template along with its initial operational version."""
    return await create_shift_template(
        session=db,
        tenant_id=ctx.tenant.id,
        user_id=ctx.user.id,
        payload=payload,
    )


@router.get(
    "",
    response_model=list[ShiftTemplateResponse],
    summary="List shift templates",
    dependencies=[Depends(require_permission(Permission.VIEW_SHIFTS))],
)
async def list_shifts_endpoint(
    search: str | None = Query(default=None, description="Search by shift name or code"),
    is_active: bool | None = Query(default=None, description="Filter active/inactive shifts"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum items to return"),
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
) -> list[ShiftTemplateResponse]:
    """Retrieves all shift templates with their current active version."""
    return await list_shift_templates(
        session=db,
        tenant_id=ctx.tenant.id,
        search=search,
        is_active=is_active,
        limit=limit,
    )


@router.get(
    "/{id}",
    response_model=ShiftTemplateDetailResponse,
    summary="Get shift template details and version history",
    dependencies=[Depends(require_permission(Permission.VIEW_SHIFTS))],
)
async def get_shift_endpoint(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
) -> ShiftTemplateDetailResponse:
    """Retrieves a single shift template with its complete immutable version history."""
    return await get_shift_template(
        session=db,
        tenant_id=ctx.tenant.id,
        shift_id=id,
    )


@router.put(
    "/{id}",
    response_model=ShiftTemplateResponse,
    summary="Update shift template metadata",
    dependencies=[Depends(require_permission(Permission.MANAGE_SHIFTS))],
)
async def update_shift_endpoint(
    id: uuid.UUID,
    payload: ShiftTemplateUpdateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
) -> ShiftTemplateResponse:
    """Updates master shift metadata (name, description, active status).

    Notice: Does NOT alter existing version rules. To modify operational timing or rules,
    create a new version via POST /api/v1/shifts/{id}/versions.
    """
    return await update_shift_template(
        session=db,
        tenant_id=ctx.tenant.id,
        shift_id=id,
        payload=payload,
    )


@router.delete(
    "/{id}",
    response_model=ShiftTemplateResponse,
    summary="Soft deactivate shift template",
    dependencies=[Depends(require_permission(Permission.MANAGE_SHIFTS))],
)
async def deactivate_shift_endpoint(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
) -> ShiftTemplateResponse:
    """Soft deactivates a shift template while preserving version history and assignments."""
    return await deactivate_shift_template(
        session=db,
        tenant_id=ctx.tenant.id,
        shift_id=id,
    )


# ==============================================================================
# Shift Versions
# ==============================================================================


@router.post(
    "/{id}/versions",
    response_model=ShiftVersionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new immutable shift version",
    dependencies=[Depends(require_permission(Permission.MANAGE_SHIFTS))],
)
async def create_shift_version_endpoint(
    id: uuid.UUID,
    payload: ShiftVersionCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
) -> ShiftVersionResponse:
    """Appends a new immutable version to a shift template starting from an effective date."""
    return await create_shift_version(
        session=db,
        tenant_id=ctx.tenant.id,
        shift_id=id,
        user_id=ctx.user.id,
        payload=payload,
    )


@router.get(
    "/{id}/versions",
    response_model=list[ShiftVersionResponse],
    summary="List shift version history",
    dependencies=[Depends(require_permission(Permission.VIEW_SHIFTS))],
)
async def list_shift_versions_endpoint(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
) -> list[ShiftVersionResponse]:
    """Retrieves all version snapshots for a shift template in descending order."""
    return await list_shift_versions(
        session=db,
        tenant_id=ctx.tenant.id,
        shift_id=id,
    )


# ==============================================================================
# Shift Assignments
# ==============================================================================


@router.post(
    "/assignments",
    response_model=ShiftAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Assign shift template to employee",
    dependencies=[Depends(require_permission(Permission.MANAGE_SHIFTS))],
)
async def assign_shift_endpoint(
    payload: ShiftAssignmentCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
) -> ShiftAssignmentResponse:
    """Assigns an employee to a shift template with temporal overlap protection."""
    return await assign_shift_to_employee(
        session=db,
        tenant_id=ctx.tenant.id,
        payload=payload,
    )


@router.get(
    "/assignments",
    response_model=list[ShiftAssignmentResponse],
    summary="List shift assignments",
    dependencies=[Depends(require_permission(Permission.VIEW_SHIFTS))],
)
async def list_shift_assignments_endpoint(
    employee_id: uuid.UUID | None = Query(default=None, description="Filter by employee UUID"),
    shift_template_id: uuid.UUID | None = Query(
        default=None, description="Filter by shift template UUID"
    ),
    effective_date: date | None = Query(
        default=None, description="Filter assignments active on this date"
    ),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum items to return"),
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
) -> list[ShiftAssignmentResponse]:
    """Lists employee shift assignments with optional filters."""
    return await list_shift_assignments(
        session=db,
        tenant_id=ctx.tenant.id,
        employee_id=employee_id,
        shift_template_id=shift_template_id,
        effective_date=effective_date,
        limit=limit,
    )


@router.put(
    "/assignments/{id}",
    response_model=ShiftAssignmentResponse,
    summary="Update shift assignment end date",
    dependencies=[Depends(require_permission(Permission.MANAGE_SHIFTS))],
)
async def update_shift_assignment_endpoint(
    id: uuid.UUID,
    payload: ShiftAssignmentUpdateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
) -> ShiftAssignmentResponse:
    """Updates an existing assignment's end date without destroying historical records."""
    return await update_shift_assignment(
        session=db,
        tenant_id=ctx.tenant.id,
        assignment_id=id,
        payload=payload,
    )


@router.post(
    "/assignments/{id}/end",
    response_model=ShiftAssignmentResponse,
    summary="End an active shift assignment",
    dependencies=[Depends(require_permission(Permission.MANAGE_SHIFTS))],
)
async def end_shift_assignment_endpoint(
    id: uuid.UUID,
    payload: ShiftAssignmentEndRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
) -> ShiftAssignmentResponse:
    """Ends an ongoing shift assignment on a given date without deleting history."""
    return await end_shift_assignment(
        session=db,
        tenant_id=ctx.tenant.id,
        assignment_id=id,
        payload=payload,
    )


# ==============================================================================
# Attendance Ledger & Punch Endpoints
# ==============================================================================


@attendance_router.post(
    "/punch",
    response_model=PunchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record attendance punch (Check-in, Check-out, Break start, Break end)",
    dependencies=[Depends(require_permission(Permission.RECORD_PUNCH))],
)
async def punch_endpoint(
    payload: PunchRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
) -> PunchResponse:
    """Records an attendance presence punch into the append-only ledger with idempotency."""
    return await record_punch(
        session=db,
        tenant_id=ctx.tenant.id,
        user_id=ctx.user.id,
        user_role=ctx.user.role,
        payload=payload,
    )


@attendance_router.get(
    "/events",
    response_model=AttendanceEventListResponse,
    summary="List attendance events with pagination and filters",
    dependencies=[Depends(require_permission(Permission.VIEW_ATTENDANCE))],
)
async def list_attendance_events_endpoint(
    employee_id: uuid.UUID | None = Query(default=None, description="Filter by employee UUID"),
    event_type: str | None = Query(default=None, description="Filter by event type"),
    start_date: datetime | None = Query(default=None, description="Filter by start timestamp"),
    end_date: datetime | None = Query(default=None, description="Filter by end timestamp"),
    limit: int = Query(default=50, ge=1, le=100, description="Items per page"),
    cursor: str | None = Query(default=None, description="Pagination cursor (ISO timestamp)"),
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
) -> AttendanceEventListResponse:
    """Lists append-only attendance events with tenant isolation and role restrictions."""
    return await list_attendance_events(
        session=db,
        tenant_id=ctx.tenant.id,
        user_id=ctx.user.id,
        user_role=ctx.user.role,
        employee_id=employee_id,
        event_type=event_type,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        cursor=cursor,
    )


@attendance_router.get(
    "/events/{event_id}",
    response_model=AttendanceEventResponse,
    summary="Get single attendance event by ID",
    dependencies=[Depends(require_permission(Permission.VIEW_ATTENDANCE))],
)
async def get_attendance_event_endpoint(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
) -> AttendanceEventResponse:
    """Fetches details of an attendance event with tenant isolation and authorization checks."""
    return await get_attendance_event(
        session=db,
        tenant_id=ctx.tenant.id,
        user_id=ctx.user.id,
        user_role=ctx.user.role,
        event_id=event_id,
    )


# ==============================================================================
# Milestone 3: Daily Attendance Projections & Recalculation
# ==============================================================================


@attendance_router.get(
    "/days",
    response_model=AttendanceDayListResponse,
    summary="List attendance day summary records",
    dependencies=[Depends(require_permission(Permission.VIEW_ATTENDANCE))],
)
async def list_attendance_days_endpoint(
    employee_id: uuid.UUID | None = Query(default=None, description="Filter by employee ID"),
    start_date: date | None = Query(default=None, description="Filter by start date (YYYY-MM-DD)"),
    end_date: date | None = Query(default=None, description="Filter by end date (YYYY-MM-DD)"),
    attendance_status: str | None = Query(
        default=None,
        description="Filter by status (PRESENT, LATE, HALF_DAY, ABSENT, INCOMPLETE, PENDING_REVIEW)",
    ),
    limit: int = Query(default=50, ge=1, le=100, description="Items per page"),
    cursor: str | None = Query(default=None, description="Pagination cursor (ISO date string)"),
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
) -> AttendanceDayListResponse:
    """Lists daily attendance projection summaries with tenant isolation and role scoping."""
    return await list_attendance_days(
        session=db,
        tenant_id=ctx.tenant.id,
        user_id=ctx.user.id,
        user_role=ctx.user.role,
        employee_id=employee_id,
        start_date=start_date,
        end_date=end_date,
        attendance_status=attendance_status,
        limit=limit,
        cursor=cursor,
    )


@attendance_router.get(
    "/days/{employee_id}/{attendance_date}",
    response_model=AttendanceDayResponse,
    summary="Get single daily attendance summary",
    dependencies=[Depends(require_permission(Permission.VIEW_ATTENDANCE))],
)
async def get_attendance_day_endpoint(
    employee_id: uuid.UUID,
    attendance_date: date,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
) -> AttendanceDayResponse:
    """Fetches a single employee's daily attendance record with role scoping and tenant isolation."""
    return await get_attendance_day(
        session=db,
        tenant_id=ctx.tenant.id,
        user_id=ctx.user.id,
        user_role=ctx.user.role,
        employee_id=employee_id,
        attendance_date=attendance_date,
    )


@attendance_router.post(
    "/recalculate",
    response_model=AttendanceDayResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger daily attendance summary recalculation",
    dependencies=[Depends(require_permission(Permission.MANAGE_ATTENDANCE))],
)
async def recalculate_attendance_day_endpoint(
    payload: AttendanceRecalculateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
) -> AttendanceDayResponse:
    """Manually recalculates an employee's daily attendance projection safely and idempotently."""
    day = await recalculate_attendance_day(
        session=db,
        tenant_id=ctx.tenant.id,
        employee_id=payload.employee_id,
        attendance_date=payload.attendance_date,
    )
    await db.commit()
    await db.refresh(day)
    return AttendanceDayResponse.model_validate(day)


# ==============================================================================
# Milestone 4: Attendance Corrections, Audit History & Reconciliation Endpoints
# ==============================================================================


@attendance_router.post(
    "/corrections",
    response_model=AttendanceCorrectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create administrative attendance correction",
    dependencies=[Depends(require_permission(Permission.CORRECT_ATTENDANCE))],
)
async def create_attendance_correction_endpoint(
    payload: AttendanceCorrectionCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
) -> AttendanceCorrectionResponse:
    """Submits an explicit administrative attendance correction (INSERT, SUPERSEDE, VOID).

    Guarantees:
    - Target event immutability.
    - Mandatory audit reason (minimum 5 non-whitespace characters).
    - Idempotency with payload divergence detection.
    - Role-based scoping (Owner/Admin/HR full tenant, Manager direct reports only).
    - Atomic projection recalculation and rollback safety.
    """
    res = await apply_attendance_correction(
        session=db,
        tenant_id=ctx.tenant.id,
        actor_user_id=ctx.user.id,
        actor_role=ctx.user.role,
        payload=payload,
    )
    await db.commit()
    return res


@attendance_router.get(
    "/corrections",
    response_model=AttendanceCorrectionListResponse,
    summary="List administrative attendance corrections",
    dependencies=[Depends(require_permission(Permission.VIEW_ATTENDANCE))],
)
async def list_attendance_corrections_endpoint(
    employee_id: uuid.UUID | None = Query(default=None, description="Filter by employee UUID"),
    correction_type: AttendanceCorrectionType | None = Query(
        default=None, description="Filter by correction action type"
    ),
    start_date: date | None = Query(default=None, description="Filter start date"),
    end_date: date | None = Query(default=None, description="Filter end date"),
    limit: int = Query(default=50, ge=1, le=100, description="Items per page"),
    cursor: str | None = Query(default=None, description="Pagination cursor"),
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
) -> AttendanceCorrectionListResponse:
    """Lists attendance correction records with tenant isolation and role-based scoping."""
    return await list_attendance_corrections(
        session=db,
        tenant_id=ctx.tenant.id,
        user_id=ctx.user.id,
        user_role=ctx.user.role,
        employee_id=employee_id,
        correction_type=correction_type,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        cursor=cursor,
    )


@attendance_router.get(
    "/records/{record_id}/events",
    response_model=AttendanceEventAuditListResponse,
    summary="Get complete event audit trail for an attendance day record",
    dependencies=[Depends(require_permission(Permission.VIEW_ATTENDANCE))],
)
@attendance_router.get(
    "/days/{record_id}/events",
    response_model=AttendanceEventAuditListResponse,
    summary="Get complete event audit trail for an attendance day record (alias)",
    dependencies=[Depends(require_permission(Permission.VIEW_ATTENDANCE))],
    include_in_schema=False,
)
async def get_attendance_record_events_endpoint(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
) -> AttendanceEventAuditListResponse:
    """Retrieves the complete immutable audit trail of presence and correction events for an attendance day."""
    return await get_attendance_day_event_audit_trail(
        session=db,
        tenant_id=ctx.tenant.id,
        user_id=ctx.user.id,
        user_role=ctx.user.role,
        record_id=record_id,
    )


@attendance_router.post(
    "/reconcile",
    response_model=ReconciliationResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger attendance reconciliation batch",
    dependencies=[Depends(require_permission(Permission.MANAGE_ATTENDANCE))],
)
async def reconcile_attendance_endpoint(
    payload: ReconciliationRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
) -> ReconciliationResponse:
    """Runs a batch attendance reconciliation job identifying unclosed sessions and recomputing projections."""
    res = await run_attendance_reconciliation(
        session=db,
        tenant_id=ctx.tenant.id,
        payload=payload,
    )
    await db.commit()
    return res
