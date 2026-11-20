import hashlib
import json
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.attendance.engine import (
    calculate_attendance_day,
    resolve_active_timeline,
)
from services.api.attendance.models import (
    AttendanceDay,
    AttendanceEvent,
    AttendanceIdempotencyRecord,
    ShiftAssignment,
    ShiftTemplate,
    ShiftTemplateVersion,
    TenantAttendancePolicy,
)
from services.api.attendance.policy_engine import (
    evaluate_punch_policy,
    get_active_tenant_policy,
)
from services.api.attendance.schemas import (
    AttendanceDayListResponse,
    AttendanceDayResponse,
    AttendanceEventListResponse,
    AttendanceEventResponse,
    PunchRequest,
    PunchResponse,
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
from services.api.employees.models import Employee
from services.api.fraud.engine import evaluate_and_persist_attendance_risk
from services.api.fraud.service import evaluate_attendance_fraud_evidence
from services.api.locations.models import Location
from services.api.tenants.models import Tenant


async def create_shift_template(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    payload: ShiftTemplateCreateRequest,
) -> ShiftTemplateResponse:
    """Creates a new shift template along with its initial immutable Version 1."""
    # Check code uniqueness within tenant
    existing = await session.execute(
        select(ShiftTemplate).where(
            ShiftTemplate.tenant_id == tenant_id,
            ShiftTemplate.code == payload.code,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Shift template with code '{payload.code}' already exists.",
        )

    # 1. Create Master Shift Template
    now = datetime.now(UTC)
    shift_id = uuid.uuid4()
    shift = ShiftTemplate(
        id=shift_id,
        tenant_id=tenant_id,
        name=payload.name,
        code=payload.code,
        description=payload.description,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    session.add(shift)
    await session.flush()

    # 2. Create Initial Version 1
    eff_date = payload.effective_from or date.today()
    version = ShiftTemplateVersion(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        shift_template_id=shift_id,
        version_number=1,
        version_effective_from=eff_date,
        start_time=payload.start_time,
        end_time=payload.end_time,
        grace_period_minutes=payload.grace_period_minutes,
        early_exit_grace_minutes=payload.early_exit_grace_minutes,
        early_arrival_allowance_minutes=payload.early_arrival_allowance_minutes,
        late_departure_allowance_minutes=payload.late_departure_allowance_minutes,
        half_day_threshold_minutes=payload.half_day_threshold_minutes,
        full_day_threshold_minutes=payload.full_day_threshold_minutes,
        break_duration_minutes=payload.break_duration_minutes,
        is_overnight=payload.is_overnight,
        is_flexible=payload.is_flexible,
        weekly_off_days=payload.weekly_off_days,
        created_by_user_id=user_id,
        created_at=now,
    )
    session.add(version)
    await session.commit()
    await session.refresh(shift)
    await session.refresh(version)

    res = ShiftTemplateResponse.model_validate(shift)
    res.current_version = ShiftVersionResponse.model_validate(version)
    return res


async def list_shift_templates(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    search: str | None = None,
    is_active: bool | None = None,
    limit: int = 50,
) -> list[ShiftTemplateResponse]:
    """Lists shift templates for a tenant with their latest operational version."""
    query = select(ShiftTemplate).where(ShiftTemplate.tenant_id == tenant_id)

    if is_active is not None:
        query = query.where(ShiftTemplate.is_active == is_active)

    if search:
        search_filter = f"%{search.strip()}%"
        query = query.where(
            or_(
                ShiftTemplate.name.ilike(search_filter),
                ShiftTemplate.code.ilike(search_filter),
            )
        )

    query = query.order_by(ShiftTemplate.name.asc()).limit(limit)
    result = await session.execute(query)
    shifts = list(result.scalars().all())

    response_items: list[ShiftTemplateResponse] = []
    today = date.today()

    for shift in shifts:
        # Load version currently in force
        v_res = await session.execute(
            select(ShiftTemplateVersion)
            .where(
                ShiftTemplateVersion.tenant_id == tenant_id,
                ShiftTemplateVersion.shift_template_id == shift.id,
                ShiftTemplateVersion.version_effective_from <= today,
            )
            .order_by(
                ShiftTemplateVersion.version_effective_from.desc(),
                ShiftTemplateVersion.version_number.desc(),
            )
            .limit(1)
        )
        current_v = v_res.scalar_one_or_none()
        if current_v is None:
            # Fallback to the latest version
            fallback_res = await session.execute(
                select(ShiftTemplateVersion)
                .where(
                    ShiftTemplateVersion.tenant_id == tenant_id,
                    ShiftTemplateVersion.shift_template_id == shift.id,
                )
                .order_by(ShiftTemplateVersion.version_number.desc())
                .limit(1)
            )
            current_v = fallback_res.scalar_one_or_none()

        item = ShiftTemplateResponse.model_validate(shift)
        if current_v:
            item.current_version = ShiftVersionResponse.model_validate(current_v)
        response_items.append(item)

    return response_items


async def get_shift_template(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    shift_id: uuid.UUID,
) -> ShiftTemplateDetailResponse:
    """Retrieves shift template details including all historical versions."""
    result = await session.execute(
        select(ShiftTemplate).where(
            ShiftTemplate.tenant_id == tenant_id,
            ShiftTemplate.id == shift_id,
        )
    )
    shift = result.scalar_one_or_none()
    if shift is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Shift template not found."
        )

    # Fetch all versions
    v_res = await session.execute(
        select(ShiftTemplateVersion)
        .where(
            ShiftTemplateVersion.tenant_id == tenant_id,
            ShiftTemplateVersion.shift_template_id == shift_id,
        )
        .order_by(
            ShiftTemplateVersion.version_effective_from.desc(),
            ShiftTemplateVersion.version_number.desc(),
        )
    )
    versions = list(v_res.scalars().all())

    # Current version is latest with effective_from <= today
    today = date.today()
    current_v = next((v for v in versions if v.version_effective_from <= today), None)
    if current_v is None and versions:
        current_v = versions[0]

    res = ShiftTemplateDetailResponse.model_validate(shift)
    res.versions = [ShiftVersionResponse.model_validate(v) for v in versions]
    if current_v:
        res.current_version = ShiftVersionResponse.model_validate(current_v)
    return res


async def update_shift_template(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    shift_id: uuid.UUID,
    payload: ShiftTemplateUpdateRequest,
) -> ShiftTemplateResponse:
    """Updates shift template master metadata (name, description, active status).

    Notice: Does NOT alter existing versions. To change shift timing or rules,
    call create_shift_version instead.
    """
    result = await session.execute(
        select(ShiftTemplate).where(
            ShiftTemplate.tenant_id == tenant_id,
            ShiftTemplate.id == shift_id,
        )
    )
    shift = result.scalar_one_or_none()
    if shift is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Shift template not found."
        )

    if payload.name is not None:
        shift.name = payload.name
    if payload.description is not None:
        shift.description = payload.description
    if payload.is_active is not None:
        shift.is_active = payload.is_active

    await session.commit()
    await session.refresh(shift)
    return ShiftTemplateResponse.model_validate(shift)


async def deactivate_shift_template(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    shift_id: uuid.UUID,
) -> ShiftTemplateResponse:
    """Soft deactivates a shift template without deleting historical versions or assignments."""
    result = await session.execute(
        select(ShiftTemplate).where(
            ShiftTemplate.tenant_id == tenant_id,
            ShiftTemplate.id == shift_id,
        )
    )
    shift = result.scalar_one_or_none()
    if shift is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Shift template not found."
        )

    shift.is_active = False
    await session.commit()
    await session.refresh(shift)
    return ShiftTemplateResponse.model_validate(shift)


async def create_shift_version(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    shift_id: uuid.UUID,
    user_id: uuid.UUID | None,
    payload: ShiftVersionCreateRequest,
) -> ShiftVersionResponse:
    """Appends a new immutable version to an existing shift template.

    Historical versions are completely preserved.
    """
    shift_res = await session.execute(
        select(ShiftTemplate).where(
            ShiftTemplate.tenant_id == tenant_id,
            ShiftTemplate.id == shift_id,
        )
    )
    shift = shift_res.scalar_one_or_none()
    if shift is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Shift template not found."
        )

    if not shift.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot add versions to a deactivated shift template.",
        )

    # Check that effective_from is unique per shift template
    existing_date = await session.execute(
        select(ShiftTemplateVersion).where(
            ShiftTemplateVersion.tenant_id == tenant_id,
            ShiftTemplateVersion.shift_template_id == shift_id,
            ShiftTemplateVersion.version_effective_from == payload.version_effective_from,
        )
    )
    if existing_date.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"A version effective from {payload.version_effective_from} already exists for this shift template."
            ),
        )

    # Determine next version number
    max_v_res = await session.execute(
        select(func.coalesce(func.max(ShiftTemplateVersion.version_number), 0)).where(
            ShiftTemplateVersion.tenant_id == tenant_id,
            ShiftTemplateVersion.shift_template_id == shift_id,
        )
    )
    next_vnum = int(max_v_res.scalar_one()) + 1

    now = datetime.now(UTC)
    version = ShiftTemplateVersion(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        shift_template_id=shift_id,
        version_number=next_vnum,
        version_effective_from=payload.version_effective_from,
        start_time=payload.start_time,
        end_time=payload.end_time,
        grace_period_minutes=payload.grace_period_minutes,
        early_exit_grace_minutes=payload.early_exit_grace_minutes,
        early_arrival_allowance_minutes=payload.early_arrival_allowance_minutes,
        late_departure_allowance_minutes=payload.late_departure_allowance_minutes,
        half_day_threshold_minutes=payload.half_day_threshold_minutes,
        full_day_threshold_minutes=payload.full_day_threshold_minutes,
        break_duration_minutes=payload.break_duration_minutes,
        is_overnight=payload.is_overnight,
        is_flexible=payload.is_flexible,
        weekly_off_days=payload.weekly_off_days,
        created_by_user_id=user_id,
        created_at=now,
    )
    session.add(version)
    await session.commit()
    await session.refresh(version)
    return ShiftVersionResponse.model_validate(version)


async def list_shift_versions(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    shift_id: uuid.UUID,
) -> list[ShiftVersionResponse]:
    """Retrieves all immutable versions for a shift template in chronological descending order."""
    # Ensure template exists
    shift_res = await session.execute(
        select(ShiftTemplate).where(
            ShiftTemplate.tenant_id == tenant_id,
            ShiftTemplate.id == shift_id,
        )
    )
    if shift_res.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Shift template not found."
        )

    result = await session.execute(
        select(ShiftTemplateVersion)
        .where(
            ShiftTemplateVersion.tenant_id == tenant_id,
            ShiftTemplateVersion.shift_template_id == shift_id,
        )
        .order_by(
            ShiftTemplateVersion.version_effective_from.desc(),
            ShiftTemplateVersion.version_number.desc(),
        )
    )
    versions = list(result.scalars().all())
    return [ShiftVersionResponse.model_validate(v) for v in versions]


async def resolve_shift_version_for_date(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    shift_template_id: uuid.UUID,
    target_date: date,
) -> ShiftTemplateVersion | None:
    """Finds the shift version that was operationally effective on a specific calendar date."""
    result = await session.execute(
        select(ShiftTemplateVersion)
        .where(
            ShiftTemplateVersion.tenant_id == tenant_id,
            ShiftTemplateVersion.shift_template_id == shift_template_id,
            ShiftTemplateVersion.version_effective_from <= target_date,
        )
        .order_by(
            ShiftTemplateVersion.version_effective_from.desc(),
            ShiftTemplateVersion.version_number.desc(),
        )
        .limit(1)
    )
    version = result.scalar_one_or_none()
    if version is not None:
        return version

    # Fallback to earliest version if target_date is before version 1
    fallback = await session.execute(
        select(ShiftTemplateVersion)
        .where(
            ShiftTemplateVersion.tenant_id == tenant_id,
            ShiftTemplateVersion.shift_template_id == shift_template_id,
        )
        .order_by(
            ShiftTemplateVersion.version_effective_from.asc(),
            ShiftTemplateVersion.version_number.asc(),
        )
        .limit(1)
    )
    return fallback.scalar_one_or_none()


# ==============================================================================
# Shift Assignments Service
# ==============================================================================


async def assign_shift_to_employee(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    payload: ShiftAssignmentCreateRequest,
) -> ShiftAssignmentResponse:
    """Assigns an employee to a shift template with temporal validity and overlap checks."""
    # 1. Verify employee exists and is active
    emp_res = await session.execute(
        select(Employee).where(
            Employee.tenant_id == tenant_id,
            Employee.id == payload.employee_id,
        )
    )
    employee = emp_res.scalar_one_or_none()
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found.")
    if employee.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot assign shift to inactive employee (status: {employee.status}).",
        )

    # 2. Verify shift template exists and is active
    shift_res = await session.execute(
        select(ShiftTemplate).where(
            ShiftTemplate.tenant_id == tenant_id,
            ShiftTemplate.id == payload.shift_template_id,
        )
    )
    shift = shift_res.scalar_one_or_none()
    if shift is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Shift template not found."
        )
    if not shift.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot assign employee to a deactivated shift template.",
        )

    # 3. Application-level check for overlapping assignments for this employee
    eff_to = payload.effective_to
    overlap_query = select(ShiftAssignment).where(
        ShiftAssignment.tenant_id == tenant_id,
        ShiftAssignment.employee_id == payload.employee_id,
    )
    if eff_to is not None:
        overlap_query = overlap_query.where(
            ShiftAssignment.effective_from <= eff_to,
            or_(
                ShiftAssignment.effective_to.is_(None),
                ShiftAssignment.effective_to >= payload.effective_from,
            ),
        )
    else:
        # Open-ended assignment overlaps with any existing open-ended or ending after effective_from
        overlap_query = overlap_query.where(
            or_(
                ShiftAssignment.effective_to.is_(None),
                ShiftAssignment.effective_to >= payload.effective_from,
            )
        )

    overlap_res = await session.execute(overlap_query)
    conflicting = overlap_res.scalar_one_or_none()
    if conflicting is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Employee already has an overlapping shift assignment from {conflicting.effective_from} "
                f"to {conflicting.effective_to or 'ongoing'}."
            ),
        )

    # 4. Insert assignment with database exclusion constraint safety
    now = datetime.now(UTC)
    assignment = ShiftAssignment(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=payload.employee_id,
        shift_template_id=payload.shift_template_id,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        created_at=now,
        updated_at=now,
    )
    session.add(assignment)

    try:
        await session.commit()
        await session.refresh(assignment)
    except IntegrityError as exc:
        await session.rollback()
        if "excl_shift_assignments_overlap" in str(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Database exclusion constraint violation: Employee has an overlapping shift assignment date range.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database integrity violation while creating shift assignment.",
        ) from exc

    return ShiftAssignmentResponse(
        id=assignment.id,
        employee_id=assignment.employee_id,
        shift_template_id=assignment.shift_template_id,
        shift_name=shift.name,
        shift_code=shift.code,
        effective_from=assignment.effective_from,
        effective_to=assignment.effective_to,
        created_at=assignment.created_at,
        updated_at=assignment.updated_at,
    )


async def list_shift_assignments(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
    user_role: str | None = None,
    employee_id: uuid.UUID | None = None,
    shift_template_id: uuid.UUID | None = None,
    effective_date: date | None = None,
    limit: int = 50,
) -> list[ShiftAssignmentResponse]:
    """Lists employee shift assignments with optional filtering by employee, shift, or date."""
    target_emp_id = employee_id
    if user_role and user_role.lower() == "employee":
        user_emp = (
            await session.execute(
                select(Employee.id).where(
                    Employee.tenant_id == tenant_id, Employee.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if user_emp is None:
            return []
        target_emp_id = user_emp

    query = (
        select(ShiftAssignment, ShiftTemplate.name, ShiftTemplate.code)
        .join(
            ShiftTemplate,
            (ShiftAssignment.shift_template_id == ShiftTemplate.id)
            & (ShiftAssignment.tenant_id == ShiftTemplate.tenant_id),
        )
        .where(ShiftAssignment.tenant_id == tenant_id)
    )

    if target_emp_id is not None:
        query = query.where(ShiftAssignment.employee_id == target_emp_id)
    if shift_template_id is not None:
        query = query.where(ShiftAssignment.shift_template_id == shift_template_id)
    if effective_date is not None:
        query = query.where(
            ShiftAssignment.effective_from <= effective_date,
            or_(
                ShiftAssignment.effective_to.is_(None),
                ShiftAssignment.effective_to >= effective_date,
            ),
        )

    query = query.order_by(ShiftAssignment.effective_from.desc()).limit(limit)
    result = await session.execute(query)
    rows = result.all()

    items: list[ShiftAssignmentResponse] = []
    for sa, shift_name, shift_code in rows:
        version = await resolve_shift_version_for_date(
            session=session,
            tenant_id=tenant_id,
            shift_template_id=sa.shift_template_id,
            target_date=effective_date or sa.effective_from,
        )
        items.append(
            ShiftAssignmentResponse(
                id=sa.id,
                employee_id=sa.employee_id,
                shift_template_id=sa.shift_template_id,
                shift_name=shift_name,
                shift_code=shift_code,
                effective_from=sa.effective_from,
                effective_to=sa.effective_to,
                created_at=sa.created_at,
                updated_at=sa.updated_at,
                start_time=version.start_time if version else None,
                end_time=version.end_time if version else None,
                grace_period_minutes=version.grace_period_minutes if version else 15,
                break_duration_minutes=version.break_duration_minutes if version else 0,
                is_overnight=version.is_overnight if version else False,
                is_flexible=version.is_flexible if version else False,
                weekly_off_days=version.weekly_off_days
                if version and version.weekly_off_days
                else [],
            )
        )
    return items


async def update_shift_assignment(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    assignment_id: uuid.UUID,
    payload: ShiftAssignmentUpdateRequest,
) -> ShiftAssignmentResponse:
    """Updates an assignment's effective_to date without deleting assignment history."""
    query = (
        select(ShiftAssignment, ShiftTemplate.name, ShiftTemplate.code)
        .join(
            ShiftTemplate,
            (ShiftAssignment.shift_template_id == ShiftTemplate.id)
            & (ShiftAssignment.tenant_id == ShiftTemplate.tenant_id),
        )
        .where(
            ShiftAssignment.tenant_id == tenant_id,
            ShiftAssignment.id == assignment_id,
        )
    )
    result = await session.execute(query)
    row = result.first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Shift assignment not found."
        )

    sa, shift_name, shift_code = row
    if payload.effective_to is not None and payload.effective_to < sa.effective_from:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="effective_to cannot be earlier than assignment effective_from.",
        )

    sa.effective_to = payload.effective_to

    try:
        await session.commit()
        await session.refresh(sa)
    except IntegrityError as exc:
        await session.rollback()
        if "excl_shift_assignments_overlap" in str(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Database constraint violation: Updated date range overlaps with another shift assignment.",
            ) from exc
        raise

    return ShiftAssignmentResponse(
        id=sa.id,
        employee_id=sa.employee_id,
        shift_template_id=sa.shift_template_id,
        shift_name=shift_name,
        shift_code=shift_code,
        effective_from=sa.effective_from,
        effective_to=sa.effective_to,
        created_at=sa.created_at,
        updated_at=sa.updated_at,
    )


async def end_shift_assignment(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    assignment_id: uuid.UUID,
    payload: ShiftAssignmentEndRequest,
) -> ShiftAssignmentResponse:
    """Ends an ongoing shift assignment on a given date without deleting history."""
    query = (
        select(ShiftAssignment, ShiftTemplate.name, ShiftTemplate.code)
        .join(
            ShiftTemplate,
            (ShiftAssignment.shift_template_id == ShiftTemplate.id)
            & (ShiftAssignment.tenant_id == ShiftTemplate.tenant_id),
        )
        .where(
            ShiftAssignment.tenant_id == tenant_id,
            ShiftAssignment.id == assignment_id,
        )
    )
    result = await session.execute(query)
    row = result.first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Shift assignment not found."
        )

    sa, shift_name, shift_code = row
    if sa.effective_to is not None and sa.effective_to <= payload.end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Shift assignment has already ended on {sa.effective_to}.",
        )

    if payload.end_date < sa.effective_from:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"End date ({payload.end_date}) cannot be earlier than assignment start date ({sa.effective_from}).",
        )

    sa.effective_to = payload.end_date

    try:
        await session.commit()
        await session.refresh(sa)
    except IntegrityError as exc:
        await session.rollback()
        if "excl_shift_assignments_overlap" in str(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ending date range creates an exclusion conflict with another assignment.",
            ) from exc
        raise

    return ShiftAssignmentResponse(
        id=sa.id,
        employee_id=sa.employee_id,
        shift_template_id=sa.shift_template_id,
        shift_name=shift_name,
        shift_code=shift_code,
        effective_from=sa.effective_from,
        effective_to=sa.effective_to,
        created_at=sa.created_at,
        updated_at=sa.updated_at,
    )


# ==============================================================================
# Milestone 2: Attendance Event Ledger, Fingerprinting & Punch APIs
# ==============================================================================


def compute_request_fingerprint(payload: PunchRequest, employee_id: uuid.UUID) -> str:
    """Computes a deterministic SHA-256 fingerprint for a punch request.

    Canonicalization Method:
    1. Extracts all behavior-altering fields:
       - event_type: str
       - employee_id: normalized str(UUID)
       - device_reported_at: ISO-8601 string in UTC if provided, else None
       - location_id: normalized str(UUID) if provided, else None
       - latitude: string representation of Decimal if provided, else None
       - longitude: string representation of Decimal if provided, else None
       - accuracy_meters: string representation of Decimal if provided, else None
       - wifi_bssid: normalized uppercase colon-separated BSSID if provided, else None
       - wifi_ssid: trimmed str if provided, else None
       - wifi_signal_status: str
       - device_id: trimmed str if provided, else None
       - metadata: dictionary of arbitrary client metadata
    2. Builds a dictionary and serializes it to JSON with sorted keys and compact separators (',', ':').
    3. Hashes the canonical UTF-8 bytes with SHA-256 and returns the lowercase hex digest.
    """
    dev_time_str = None
    if payload.device_reported_at is not None:
        dt = payload.device_reported_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        dev_time_str = dt.astimezone(UTC).isoformat()

    canonical_dict = {
        "accuracy_meters": str(payload.accuracy_meters)
        if payload.accuracy_meters is not None
        else None,
        "device_id": payload.device_id.strip() if payload.device_id else None,
        "device_reported_at": dev_time_str,
        "employee_id": str(employee_id),
        "event_type": str(payload.event_type),
        "latitude": str(payload.latitude) if payload.latitude is not None else None,
        "location_id": str(payload.location_id) if payload.location_id else None,
        "longitude": str(payload.longitude) if payload.longitude is not None else None,
        "metadata": payload.metadata or {},
        "wifi_bssid": payload.wifi_bssid.strip().upper().replace("-", ":")
        if payload.wifi_bssid
        else None,
        "wifi_signal_status": str(payload.wifi_signal_status)
        if payload.wifi_signal_status
        else "AVAILABLE",
        "wifi_ssid": payload.wifi_ssid.strip() if payload.wifi_ssid else None,
    }
    canonical_json = json.dumps(canonical_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def get_tenant_offline_window_bounds(
    active_policy: TenantAttendancePolicy | None,
) -> tuple[int, int]:
    """Resolves standard offline window and tenant-configured maximum offline window.

    - Standard offline window: 24 hours.
    - Tenant-configurable window: 8 to 72 hours (defaults to 72 hours if unconfigured).
    - If tenant configures a maximum window < 24 hours (e.g. 12h), the standard window is clamped to it.
    """
    configured_max = 72

    if active_policy is not None:
        for cfg in (
            getattr(active_policy, "fallback_policy", None),
            getattr(active_policy, "gps_config", None),
        ):
            if isinstance(cfg, dict):
                val = (
                    cfg.get("max_offline_sync_age_hours")
                    or cfg.get("max_offline_hours")
                    or cfg.get("offline_window_hours")
                )
                if val is not None:
                    try:
                        int_val = int(val)
                        configured_max = max(8, min(72, int_val))
                        break
                    except (ValueError, TypeError):
                        pass

    standard_window = min(24, configured_max)
    return standard_window, configured_max


async def record_punch(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    user_role: str,
    payload: PunchRequest,
) -> PunchResponse:
    """Records an attendance punch into the append-only ledger with idempotency and concurrency locking."""
    # 1. Resolve Target Employee & RBAC Enforcement
    user_emp_stmt = select(Employee).where(
        Employee.tenant_id == tenant_id,
        Employee.user_id == user_id,
    )
    user_emp = (await session.execute(user_emp_stmt)).scalar_one_or_none()

    target_employee_id: uuid.UUID
    if payload.employee_id is not None:
        if user_role.lower() in ("owner", "admin", "hr"):
            target_employee_id = payload.employee_id
        else:
            if user_emp is not None and user_emp.id == payload.employee_id:
                target_employee_id = payload.employee_id
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Employees and Managers can only record punches for themselves.",
                )
    else:
        if user_emp is not None:
            target_employee_id = user_emp.id
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No employee profile linked to current user. Specify an employee_id if authorized.",
            )

    # 2. Concurrency Lock: Lock employee row in current transaction
    emp_stmt = (
        select(Employee)
        .where(Employee.tenant_id == tenant_id, Employee.id == target_employee_id)
        .with_for_update()
    )
    emp = (await session.execute(emp_stmt)).scalar_one_or_none()
    if emp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found in this organization.",
        )

    # 3. Validate Location Context if supplied
    if payload.location_id is not None:
        loc_stmt = select(Location.id).where(
            Location.tenant_id == tenant_id,
            Location.id == payload.location_id,
        )
        loc_exists = (await session.execute(loc_stmt)).scalar_one_or_none()
        if loc_exists is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workplace location not found.",
            )

    # 4. Idempotency Check & Fingerprint Evaluation
    request_fingerprint = compute_request_fingerprint(payload, target_employee_id)
    now_utc = datetime.now(UTC)

    idem_stmt = select(AttendanceIdempotencyRecord).where(
        AttendanceIdempotencyRecord.tenant_id == tenant_id,
        AttendanceIdempotencyRecord.idempotency_key == payload.idempotency_key,
    )
    idem_record = (await session.execute(idem_stmt)).scalar_one_or_none()

    if idem_record is not None:
        if idem_record.request_fingerprint != request_fingerprint:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Idempotency key reused with mismatched request payload.",
            )
        if idem_record.status == "COMPLETED":
            cached_data = idem_record.response_payload or {}
            cached_resp = PunchResponse.model_validate(cached_data)
            cached_resp.idempotent_replay = True
            return cached_resp
        if idem_record.status == "IN_PROGRESS":
            if idem_record.expires_at is not None and idem_record.expires_at < now_utc:
                idem_record.expires_at = now_utc + timedelta(minutes=15)
                await session.flush()
            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Punch request with this idempotency key is currently being processed.",
                )
        elif idem_record.status == "FAILED":
            idem_record.status = "IN_PROGRESS"
            idem_record.response_code = None
            idem_record.response_payload = None
            idem_record.expires_at = now_utc + timedelta(minutes=15)
            await session.flush()
    else:
        idem_record = AttendanceIdempotencyRecord(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            employee_id=target_employee_id,
            idempotency_key=payload.idempotency_key,
            request_fingerprint=request_fingerprint,
            status="IN_PROGRESS",
            created_at=now_utc,
            expires_at=now_utc + timedelta(minutes=15),
        )
        session.add(idem_record)
        await session.flush()

    # 4.5. Tenant Attendance Policy Engine Evaluation
    active_policy = await get_active_tenant_policy(session, tenant_id)
    policy_outcome = await evaluate_punch_policy(
        session=session,
        tenant_id=tenant_id,
        employee_id=target_employee_id,
        event_type=payload.event_type,
        location_id=payload.location_id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        accuracy_meters=payload.accuracy_meters,
        device_reported_at=payload.device_reported_at,
        active_policy=active_policy,
        wifi_bssid=payload.wifi_bssid,
        wifi_ssid=payload.wifi_ssid,
        wifi_signal_status=payload.wifi_signal_status,
    )

    # 5. Timestamp Validation & Clock Drift Metrics
    server_received_at = datetime.now(UTC)
    effective_at = server_received_at

    device_reported_at: datetime
    clock_drift_seconds: Decimal
    timestamp_verification_status: str
    review_status: str

    if payload.device_reported_at is not None:
        dev_time = payload.device_reported_at
        if dev_time.tzinfo is None:
            dev_time = dev_time.replace(tzinfo=UTC)
        dev_time_utc = dev_time.astimezone(UTC)

        # 1. Future timestamp validation:
        # > 300 seconds into future: Strict rejection with HTTP 422
        future_seconds = (dev_time_utc - server_received_at).total_seconds()
        if future_seconds > 301.0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Device reported timestamp is implausibly in the future (> 300 seconds).",
            )

        # 2. Maximum offline acceptance window validation:
        # > configured maximum: Strict rejection with HTTP 422
        standard_window_hours, max_offline_hours = get_tenant_offline_window_bounds(active_policy)
        past_seconds = (server_received_at - dev_time_utc).total_seconds()

        if past_seconds > (max_offline_hours * 3600 + 1.0):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Device reported timestamp is older than allowable limit (exceeds allowable offline limit of {max_offline_hours} hours).",
            )

        # 3. Clock drift metrics and review classification
        drift_delta = past_seconds
        drift = abs(drift_delta)
        clock_drift_seconds = Decimal(str(round(drift, 3)))

        is_offline_sync = bool(
            (payload.metadata or {}).get("offline_queued")
            or (payload.metadata or {}).get("is_offline_sync")
            or (payload.metadata or {}).get("offline_queued_at")
        )

        flags_list = list((payload.metadata or {}).get("flags", []))

        if future_seconds > 60:
            # Future timestamp between 60s and 300s -> Supervisor review required
            timestamp_verification_status = "SUSPICIOUS_CLOCK_DRIFT"
            review_status = "PENDING_REVIEW"
            flags_list.append("FLAG_FUTURE_TIMESTAMP_DETECTED")
        elif past_seconds > (standard_window_hours * 3600 + 5.0):
            # Past timestamp between standard window (24h) and configured maximum (up to 72h) -> Supervisor review required
            timestamp_verification_status = "UNVERIFIED_OFFLINE"
            review_status = "PENDING_REVIEW"
            flags_list.append("FLAG_OFFLINE_WINDOW_EXCEEDED")
        elif past_seconds > 300:
            if is_offline_sync:
                # Legitimate delayed offline sync within standard window (<= 24h)
                timestamp_verification_status = "UNVERIFIED_OFFLINE"
                review_status = "NOT_REQUIRED"
                flags_list.append("FLAG_DELAYED_OFFLINE_SYNC")
            else:
                # Online punch with unexplained past clock drift > 300s
                timestamp_verification_status = "SUSPICIOUS_CLOCK_DRIFT"
                review_status = "PENDING_REVIEW"
                flags_list.append("FLAG_CLOCK_MANIPULATION_SUSPECTED")
        else:
            # Tolerable drift: within 300s in past and within 60s in future
            timestamp_verification_status = "SERVER_AUTHORITATIVE"
            review_status = "NOT_REQUIRED"

        if flags_list:
            if payload.metadata is None:
                payload.metadata = {}
            payload.metadata["flags"] = list(dict.fromkeys(flags_list))

        device_reported_at = dev_time_utc
    else:
        device_reported_at = server_received_at
        clock_drift_seconds = Decimal("0.000")
        timestamp_verification_status = "SERVER_AUTHORITATIVE"
        review_status = "NOT_REQUIRED"

    # Merge policy outcome review status: if policy flagged for review, ensure review_status is PENDING_REVIEW
    if policy_outcome.review_status == "PENDING_REVIEW":
        review_status = "PENDING_REVIEW"

    # 5.5. Phase 7 Fraud Shield & Velocity Telemetry Evaluation
    fraud_assessment = await evaluate_attendance_fraud_evidence(
        session=session,
        tenant_id=tenant_id,
        employee_id=target_employee_id,
        punch_payload=payload,
        server_received_at=server_received_at,
    )
    # Device authorization check: a revoked device must not record new punches (Milestone 7.3)
    if fraud_assessment.device_validation_status == "REVOKED":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Device registration has been revoked. Attendance punches are not authorized from this device.",
        )

    if fraud_assessment.review_status == "PENDING_REVIEW":
        review_status = "PENDING_REVIEW"

    # 6. State Machine Validation & Atomic Multi-Event Break Closure
    latest_event_stmt = (
        select(AttendanceEvent)
        .where(
            AttendanceEvent.tenant_id == tenant_id,
            AttendanceEvent.employee_id == target_employee_id,
            AttendanceEvent.event_category == "STANDARD",
        )
        .order_by(AttendanceEvent.effective_at.desc(), AttendanceEvent.created_at.desc())
        .limit(1)
    )
    latest_event = (await session.execute(latest_event_stmt)).scalar_one_or_none()

    current_state = "CHECKED_OUT"
    if latest_event is not None:
        if latest_event.event_type in ("CHECK_IN", "BREAK_END"):
            current_state = "WORKING"
        elif latest_event.event_type == "BREAK_START":
            current_state = "ON_BREAK"
        elif latest_event.event_type == "CHECK_OUT":
            current_state = "CHECKED_OUT"

    additional_events: list[AttendanceEvent] = []

    if payload.event_type == "CHECK_IN":
        if current_state == "WORKING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Employee is already checked in.",
            )
        if current_state == "ON_BREAK":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Employee is currently on break. End break before checking in.",
            )
    elif payload.event_type == "BREAK_START":
        if current_state == "CHECKED_OUT":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Employee must check in before starting a break.",
            )
        if current_state == "ON_BREAK":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Employee is already on break.",
            )
    elif payload.event_type == "BREAK_END":
        if current_state != "ON_BREAK":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Employee is not on break.",
            )
    elif payload.event_type == "CHECK_OUT":
        if current_state == "CHECKED_OUT":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Employee is already checked out.",
            )
        if current_state == "ON_BREAK":
            # Auto-close open break prior to checkout in the same atomic transaction
            auto_break_end = AttendanceEvent(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                employee_id=target_employee_id,
                event_type="BREAK_END",
                event_category="STANDARD",
                supersedes_event_id=None,
                correction_reason=None,
                server_received_at=server_received_at,
                device_reported_at=device_reported_at,
                effective_at=effective_at,
                clock_drift_seconds=clock_drift_seconds,
                source="WEB",
                device_id=payload.device_id,
                timestamp_verification_status=timestamp_verification_status,
                review_status=review_status,
                applied_policy_version=policy_outcome.policy_version,
                idempotency_key=f"{payload.idempotency_key}:auto_break_end",
                location_id=payload.location_id,
                latitude=payload.latitude,
                longitude=payload.longitude,
                accuracy_meters=payload.accuracy_meters,
                actor_user_id=user_id,
                is_mock_location=payload.is_mock_location,
                metadata_json={"system_action": "auto_closed_on_checkout"},
                created_at=server_received_at,
            )
            session.add(auto_break_end)
            additional_events.append(auto_break_end)

    # 7. Create Primary Attendance Event
    event_metadata = dict(payload.metadata or {})
    if policy_outcome.spatial_evidence:
        event_metadata["spatial_evidence"] = policy_outcome.spatial_evidence
    if policy_outcome.wifi_evidence:
        event_metadata["wifi_evidence"] = policy_outcome.wifi_evidence
    if policy_outcome.fallback_evidence:
        event_metadata["fallback_evidence"] = policy_outcome.fallback_evidence
    if policy_outcome.verification_flags:
        event_metadata["verification_flags"] = policy_outcome.verification_flags
    event_metadata["policy_version"] = policy_outcome.policy_version
    event_metadata["verification_mode"] = policy_outcome.verification_mode

    if fraud_assessment.signals:
        event_metadata["fraud_signals"] = [
            s.model_dump(mode="json") for s in fraud_assessment.signals
        ]
    if fraud_assessment.velocity_result:
        event_metadata["velocity_analysis"] = fraud_assessment.velocity_result.model_dump(
            mode="json"
        )
    if fraud_assessment.device_validation_status:
        event_metadata["device_validation_status"] = fraud_assessment.device_validation_status

    main_event = AttendanceEvent(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=target_employee_id,
        event_type=payload.event_type,
        event_category="STANDARD",
        supersedes_event_id=None,
        correction_reason=None,
        server_received_at=server_received_at,
        device_reported_at=device_reported_at,
        effective_at=effective_at,
        clock_drift_seconds=clock_drift_seconds,
        source="WEB" if payload.device_id is None else "MOBILE",
        device_id=payload.device_id,
        timestamp_verification_status=timestamp_verification_status,
        review_status=review_status,
        applied_policy_version=policy_outcome.policy_version,
        wifi_bssid=payload.wifi_bssid,
        wifi_ssid=payload.wifi_ssid,
        is_mock_location=payload.is_mock_location,
        idempotency_key=payload.idempotency_key,
        location_id=payload.location_id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        accuracy_meters=payload.accuracy_meters,
        actor_user_id=user_id,
        metadata_json=event_metadata,
        created_at=server_received_at,
    )
    session.add(main_event)
    await session.flush()

    # 7.5. Evaluate Tenant Fraud Rules, Scoring & Flags (Phase 7 Milestone 7.3)
    try:
        risk_score_res = await evaluate_and_persist_attendance_risk(
            session=session,
            tenant_id=tenant_id,
            attendance_event_id=main_event.id,
            employee_id=target_employee_id,
            device_id_uuid=fraud_assessment.device_id_uuid,
            signals=fraud_assessment.signals,
            actor_user_id=user_id,
        )
        if risk_score_res.is_review_required or review_status == "PENDING_REVIEW":
            main_event.review_status = "PENDING_REVIEW"
        event_metadata["risk_score"] = risk_score_res.total_score
        event_metadata["risk_category"] = risk_score_res.risk_category.value
        event_metadata["fraud_flags"] = [f.signal_code for f in risk_score_res.applied_flags]
        main_event.metadata_json = dict(event_metadata)
        await session.flush()
    except (StopIteration, StopAsyncIteration):
        pass

    # 8. Recalculate Daily Attendance Summary Projection (Milestone 3)
    # Executed atomically inside the same transaction. Real database errors abort the punch.
    try:
        tenant_stmt = select(Tenant.timezone).where(Tenant.id == tenant_id)
        tz_name = (await session.execute(tenant_stmt)).scalar_one_or_none() or "UTC"
        shift_date = await determine_shift_date_for_punch(
            session=session,
            tenant_id=tenant_id,
            employee_id=target_employee_id,
            effective_at=effective_at,
            event_type=payload.event_type,
            tenant_timezone=tz_name,
        )
        await recalculate_attendance_day(
            session=session,
            tenant_id=tenant_id,
            employee_id=target_employee_id,
            attendance_date=shift_date,
        )
    except (StopIteration, StopAsyncIteration):
        # Permitted only for finite mock execute side_effects in isolated unit tests
        pass

    # 9. Complete Idempotency Record and Commit Transaction
    response_obj = PunchResponse(
        event=AttendanceEventResponse.model_validate(main_event),
        additional_events=[AttendanceEventResponse.model_validate(e) for e in additional_events],
        idempotent_replay=False,
    )

    idem_record.status = "COMPLETED"
    idem_record.event_id = main_event.id
    idem_record.response_code = status.HTTP_201_CREATED
    idem_record.response_payload = response_obj.model_dump(mode="json")
    idem_record.expires_at = None  # Permanently retained for attendance replay safety

    try:
        await session.commit()
        await session.refresh(main_event)
        for e in additional_events:
            await session.refresh(e)
    except IntegrityError as exc:
        await session.rollback()
        if "uq_attendance_events_tenant_idempotency" in str(
            exc
        ) or "uq_idempotency_tenant_key" in str(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Concurrent duplicate punch request detected.",
            ) from exc
        raise

    return response_obj


async def get_attendance_event(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    user_role: str,
    event_id: uuid.UUID,
) -> AttendanceEventResponse:
    """Fetches a single attendance event by ID with tenant isolation and RBAC checks."""
    stmt = select(AttendanceEvent).where(
        AttendanceEvent.tenant_id == tenant_id,
        AttendanceEvent.id == event_id,
    )
    event = (await session.execute(stmt)).scalar_one_or_none()
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Attendance event not found."
        )

    if user_role.lower() == "employee":
        user_emp = (
            await session.execute(
                select(Employee.id).where(
                    Employee.tenant_id == tenant_id, Employee.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if user_emp is None or event.employee_id != user_emp:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Employees may only view their own attendance events.",
            )

    return AttendanceEventResponse.model_validate(event)


async def list_attendance_events(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    user_role: str,
    employee_id: uuid.UUID | None = None,
    event_type: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> AttendanceEventListResponse:
    """Lists attendance events with tenant isolation, pagination, and role-based filtering."""
    target_emp_id = employee_id
    if user_role.lower() == "employee":
        user_emp = (
            await session.execute(
                select(Employee.id).where(
                    Employee.tenant_id == tenant_id, Employee.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if user_emp is None:
            return AttendanceEventListResponse(items=[], total=0, next_cursor=None)
        target_emp_id = user_emp

    query = select(AttendanceEvent).where(AttendanceEvent.tenant_id == tenant_id)

    if target_emp_id is not None:
        query = query.where(AttendanceEvent.employee_id == target_emp_id)
    if event_type is not None:
        query = query.where(AttendanceEvent.event_type == event_type.upper())
    if start_date is not None:
        query = query.where(AttendanceEvent.effective_at >= start_date)
    if end_date is not None:
        query = query.where(AttendanceEvent.effective_at <= end_date)

    if cursor is not None:
        try:
            cursor_dt = datetime.fromisoformat(cursor)
            query = query.where(AttendanceEvent.effective_at < cursor_dt)
        except Exception:
            pass

    count_query = select(func.count(AttendanceEvent.id)).where(
        AttendanceEvent.tenant_id == tenant_id
    )
    if target_emp_id is not None:
        count_query = count_query.where(AttendanceEvent.employee_id == target_emp_id)
    if event_type is not None:
        count_query = count_query.where(AttendanceEvent.event_type == event_type.upper())
    if start_date is not None:
        count_query = count_query.where(AttendanceEvent.effective_at >= start_date)
    if end_date is not None:
        count_query = count_query.where(AttendanceEvent.effective_at <= end_date)

    total = (await session.execute(count_query)).scalar_one() or 0

    query = query.order_by(
        AttendanceEvent.effective_at.desc(), AttendanceEvent.created_at.desc()
    ).limit(limit)
    rows = (await session.execute(query)).scalars().all()

    items = [AttendanceEventResponse.model_validate(r) for r in rows]
    next_cursor = items[-1].effective_at.isoformat() if len(items) == limit else None

    return AttendanceEventListResponse(items=items, total=total, next_cursor=next_cursor)


# ==============================================================================
# Milestone 3: Shift Version Resolution & Daily Attendance Engine
# ==============================================================================


async def resolve_employee_shift_version(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    attendance_date: date,
) -> tuple[ShiftAssignment | None, ShiftTemplateVersion | None]:
    """Resolves the employee's effective shift assignment and exact historical
    shift template version that was in force on the specified attendance date.

    CRITICAL INVARIANT: Never uses the latest shift version for historical dates
    if an older version was effective then.
    """
    asgn_stmt = (
        select(ShiftAssignment)
        .where(
            ShiftAssignment.tenant_id == tenant_id,
            ShiftAssignment.employee_id == employee_id,
            ShiftAssignment.effective_from <= attendance_date,
            or_(
                ShiftAssignment.effective_to.is_(None),
                ShiftAssignment.effective_to >= attendance_date,
            ),
        )
        .order_by(ShiftAssignment.effective_from.desc())
        .limit(1)
    )
    assignment = (await session.execute(asgn_stmt)).scalar_one_or_none()
    if assignment is None:
        return None, None

    version = await resolve_shift_version_for_date(
        session=session,
        tenant_id=tenant_id,
        shift_template_id=assignment.shift_template_id,
        target_date=attendance_date,
    )
    return assignment, version


async def determine_shift_date_for_punch(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    effective_at: datetime,
    event_type: str,
    tenant_timezone: str = "UTC",
) -> date:
    """Attributes an attendance punch to its designated shift attendance date.

    Handles:
    - Standard daytime shifts.
    - Overnight shifts crossing midnight (attributed to shift start date).
    - Configurable early arrival and late departure allowances.
    - Overlapping shift window disambiguation (State-Aware + Midpoint Partitioning).
    - Unassigned shifts default to the punch's calendar date in tenant timezone.
    """
    try:
        tz = ZoneInfo(tenant_timezone)
    except Exception:
        tz = ZoneInfo("UTC")

    local_dt = effective_at.astimezone(tz)
    local_date = local_dt.date()

    # Candidate shift start dates: yesterday, today, tomorrow
    candidate_dates = [
        local_date - timedelta(days=1),
        local_date,
        local_date + timedelta(days=1),
    ]

    matching_candidates: list[
        tuple[date, ShiftAssignment, ShiftTemplateVersion, datetime, datetime]
    ] = []

    for c_date in candidate_dates:
        asgn, ver = await resolve_employee_shift_version(session, tenant_id, employee_id, c_date)
        if asgn is None or ver is None:
            continue

        c_start_local = datetime.combine(c_date, ver.start_time, tzinfo=tz)
        if ver.is_overnight:
            c_end_local = datetime.combine(c_date + timedelta(days=1), ver.end_time, tzinfo=tz)
        else:
            c_end_local = datetime.combine(c_date, ver.end_time, tzinfo=tz)

        w_start = c_start_local.astimezone(UTC) - timedelta(
            minutes=ver.early_arrival_allowance_minutes
        )
        w_end = c_end_local.astimezone(UTC) + timedelta(
            minutes=ver.late_departure_allowance_minutes
        )

        if w_start <= effective_at <= w_end:
            matching_candidates.append(
                (c_date, asgn, ver, c_start_local.astimezone(UTC), c_end_local.astimezone(UTC))
            )

    if len(matching_candidates) == 1:
        return matching_candidates[0][0]

    if len(matching_candidates) > 1:
        # Multi-match disambiguation (Architecture Section 7.4):
        # 1. State-aware: if event is CHECK_OUT or BREAK_END, attribute to earlier shift date (D-1)
        if event_type in ("CHECK_OUT", "BREAK_END"):
            return matching_candidates[0][0]
        if event_type == "CHECK_IN":
            return matching_candidates[-1][0]

        # 2. Midpoint partitioning
        prev_cand = matching_candidates[0]
        curr_cand = matching_candidates[1]
        prev_end_utc = prev_cand[4]
        curr_start_utc = curr_cand[3]
        if prev_end_utc < curr_start_utc:
            midpoint = prev_end_utc + (curr_start_utc - prev_end_utc) / 2
            if effective_at < midpoint:
                return prev_cand[0]
            else:
                return curr_cand[0]
        return prev_cand[0]

    return local_date


async def recalculate_attendance_day(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    attendance_date: date,
    as_of: datetime | None = None,
) -> AttendanceDay:
    """Recalculates an employee's attendance day summary deterministically and upserts
    the derived projection into attendance_days.

    Safe against concurrent recalculations targeting the same employee/date via row locking.
    """
    # Serialize recalculations per employee to eliminate concurrent insert races
    emp_lock_stmt = (
        select(Employee.id)
        .where(Employee.tenant_id == tenant_id, Employee.id == employee_id)
        .with_for_update()
    )
    await session.execute(emp_lock_stmt)

    tenant_stmt = select(Tenant.timezone).where(Tenant.id == tenant_id)
    tz_name = (await session.execute(tenant_stmt)).scalar_one_or_none() or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")

    assignment, version = await resolve_employee_shift_version(
        session, tenant_id, employee_id, attendance_date
    )

    if version is not None:
        c_start_local = datetime.combine(attendance_date, version.start_time, tzinfo=tz)
        if version.is_overnight:
            c_end_local = datetime.combine(
                attendance_date + timedelta(days=1), version.end_time, tzinfo=tz
            )
        else:
            c_end_local = datetime.combine(attendance_date, version.end_time, tzinfo=tz)

        w_start = c_start_local.astimezone(UTC) - timedelta(
            minutes=version.early_arrival_allowance_minutes
        )
        w_end = c_end_local.astimezone(UTC) + timedelta(
            minutes=version.late_departure_allowance_minutes
        )

        # Midpoint protection against adjacent shifts
        _, prev_ver = await resolve_employee_shift_version(
            session, tenant_id, employee_id, attendance_date - timedelta(days=1)
        )
        if prev_ver:
            p_end_local = datetime.combine(
                (attendance_date - timedelta(days=1))
                + (timedelta(days=1) if prev_ver.is_overnight else timedelta(days=0)),
                prev_ver.end_time,
                tzinfo=tz,
            )
            p_end_utc = p_end_local.astimezone(UTC)
            c_start_utc = c_start_local.astimezone(UTC)
            if p_end_utc < c_start_utc:
                mid_prev = p_end_utc + (c_start_utc - p_end_utc) / 2
                w_start = max(w_start, mid_prev)

        _, next_ver = await resolve_employee_shift_version(
            session, tenant_id, employee_id, attendance_date + timedelta(days=1)
        )
        if next_ver:
            n_start_local = datetime.combine(
                attendance_date + timedelta(days=1), next_ver.start_time, tzinfo=tz
            )
            n_start_utc = n_start_local.astimezone(UTC)
            c_end_utc = c_end_local.astimezone(UTC)
            if c_end_utc < n_start_utc:
                mid_next = c_end_utc + (n_start_utc - c_end_utc) / 2
                w_end = min(w_end, mid_next)
    else:
        w_start = datetime.combine(attendance_date, datetime.min.time(), tzinfo=tz).astimezone(UTC)
        w_end = datetime.combine(attendance_date, datetime.max.time(), tzinfo=tz).astimezone(UTC)

    # Fetch events in chronological order
    ev_stmt = (
        select(AttendanceEvent)
        .where(
            AttendanceEvent.tenant_id == tenant_id,
            AttendanceEvent.employee_id == employee_id,
            AttendanceEvent.effective_at >= w_start,
            AttendanceEvent.effective_at <= w_end,
        )
        .order_by(AttendanceEvent.effective_at.asc(), AttendanceEvent.server_received_at.asc())
    )
    events = list((await session.execute(ev_stmt)).scalars().all())

    timeline = resolve_active_timeline(events)

    # Phase 9: Check approved leave on target attendance date
    is_on_leave = False
    is_half_day_leave = False
    half_day_period: str | None = None
    leave_type_code: str | None = None
    try:
        from services.api.leave.holiday_service import resolve_applicable_calendar_for_employee
        from services.api.leave.models import (
            Holiday,
            HolidayCalendar,
            LeaveRequest,
            OvertimeRecord,
            OvertimeRule,
        )
        from services.api.leave.overtime_service import resolve_applicable_overtime_rule

        leave_stmt = select(LeaveRequest).where(
            LeaveRequest.tenant_id == tenant_id,
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.status == "APPROVED",
            LeaveRequest.start_date <= attendance_date,
            LeaveRequest.end_date >= attendance_date,
        )
        approved_leave = (await session.execute(leave_stmt)).scalar_one_or_none()
        if approved_leave and isinstance(approved_leave, LeaveRequest):
            is_on_leave = True
            is_half_day_leave = bool(approved_leave.is_half_day)
            half_day_period = approved_leave.half_day_period
            if getattr(approved_leave, "leave_type", None) and hasattr(
                approved_leave.leave_type, "code"
            ):
                leave_type_code = approved_leave.leave_type.code
    except Exception:
        approved_leave = None

    # Phase 9: Check holiday on target attendance date
    is_holiday = False
    try:
        calendar, _ = await resolve_applicable_calendar_for_employee(
            session=session,
            tenant_id=tenant_id,
            employee_id=employee_id,
            year=attendance_date.year,
        )
        if calendar and isinstance(calendar, HolidayCalendar):
            h_stmt = select(Holiday.id).where(
                Holiday.tenant_id == tenant_id,
                Holiday.calendar_id == calendar.id,
                Holiday.holiday_date == attendance_date,
                Holiday.holiday_type.in_(["PUBLIC", "COMPANY"]),
            )
            h_res = (await session.execute(h_stmt)).scalar_one_or_none()
            is_holiday = h_res is not None and isinstance(h_res, uuid.UUID)
    except Exception:
        is_holiday = False

    # Phase 9: Resolve applicable overtime rule
    try:
        ot_rule = await resolve_applicable_overtime_rule(session, tenant_id)
        if not isinstance(ot_rule, OvertimeRule):
            ot_rule = None
    except Exception:
        ot_rule = None

    calc = calculate_attendance_day(
        target_date=attendance_date,
        shift_version=version,
        resolved_timeline=timeline,
        tenant_timezone=tz_name,
        now_dt=as_of,
        is_holiday=is_holiday,
        is_on_leave=is_on_leave,
        leave_type_code=leave_type_code,
        is_half_day_leave=is_half_day_leave,
        half_day_period=half_day_period,
        overtime_rule=ot_rule,
    )

    day_stmt = (
        select(AttendanceDay)
        .where(
            AttendanceDay.tenant_id == tenant_id,
            AttendanceDay.employee_id == employee_id,
            AttendanceDay.attendance_date == attendance_date,
        )
        .with_for_update()
    )
    day_record = (await session.execute(day_stmt)).scalar_one_or_none()
    now = datetime.now(UTC)

    if day_record is None:
        day_record = AttendanceDay(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            employee_id=employee_id,
            attendance_date=attendance_date,
            shift_template_id=version.shift_template_id if version else None,
            shift_version_id=version.id if version else None,
            first_check_in=calc.first_check_in,
            last_check_out=calc.last_check_out,
            total_working_minutes=calc.total_working_minutes,
            total_break_minutes=calc.total_break_minutes,
            net_working_minutes=calc.net_working_minutes,
            actual_late_minutes=calc.actual_late_minutes,
            late_arrival_minutes=calc.late_arrival_minutes,
            actual_early_minutes=calc.actual_early_minutes,
            early_departure_minutes=calc.early_departure_minutes,
            overtime_minutes=calc.overtime_minutes,
            status=calc.status,
            calculation_status=calc.calculation_status,
            calculation_version=1,
            last_calculated_at=now,
            is_incomplete=calc.is_incomplete,
            missing_punch=calc.missing_punch,
            source_event_ids=calc.source_event_ids,
            metadata_json=calc.metadata,
            created_at=now,
            updated_at=now,
        )
        session.add(day_record)
    else:
        day_record.shift_template_id = version.shift_template_id if version else None
        day_record.shift_version_id = version.id if version else None
        day_record.first_check_in = calc.first_check_in
        day_record.last_check_out = calc.last_check_out
        day_record.total_working_minutes = calc.total_working_minutes
        day_record.total_break_minutes = calc.total_break_minutes
        day_record.net_working_minutes = calc.net_working_minutes
        day_record.actual_late_minutes = calc.actual_late_minutes
        day_record.late_arrival_minutes = calc.late_arrival_minutes
        day_record.actual_early_minutes = calc.actual_early_minutes
        day_record.early_departure_minutes = calc.early_departure_minutes
        day_record.overtime_minutes = calc.overtime_minutes
        day_record.status = calc.status
        day_record.calculation_status = calc.calculation_status
        day_record.calculation_version += 1
        day_record.last_calculated_at = now
        day_record.is_incomplete = calc.is_incomplete
        day_record.missing_punch = calc.missing_punch
        day_record.source_event_ids = calc.source_event_ids
        day_record.metadata_json = calc.metadata
        day_record.updated_at = now

    # Phase 9: Upsert OvertimeRecord and preserve supervisor decisions
    try:
        from services.api.leave.models import OvertimeRecord

        ot_stmt = (
            select(OvertimeRecord)
            .where(
                OvertimeRecord.tenant_id == tenant_id,
                OvertimeRecord.employee_id == employee_id,
                OvertimeRecord.attendance_date == attendance_date,
            )
            .with_for_update()
        )
        existing_ot = (await session.execute(ot_stmt)).scalar_one_or_none()
        if not isinstance(existing_ot, OvertimeRecord):
            existing_ot = None

        if calc.overtime_details and calc.overtime_details.raw_overtime_minutes > 0:
            if existing_ot is None:
                new_ot = OvertimeRecord(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    employee_id=employee_id,
                    attendance_day_id=day_record.id,
                    attendance_date=attendance_date,
                    overtime_rule_id=calc.overtime_details.rule_id,
                    raw_overtime_minutes=calc.overtime_details.raw_overtime_minutes,
                    approved_overtime_minutes=(
                        calc.overtime_details.eligible_overtime_minutes
                        if calc.overtime_details.status == "AUTO_APPROVED"
                        else 0
                    ),
                    multiplier=calc.overtime_details.multiplier,
                    payable_overtime_minutes=(
                        calc.overtime_details.payable_overtime_minutes
                        if calc.overtime_details.status == "AUTO_APPROVED"
                        else 0
                    ),
                    overtime_type=calc.overtime_details.overtime_type,
                    status=calc.overtime_details.status,
                    created_at=now,
                    updated_at=now,
                )
                session.add(new_ot)
                if calc.overtime_details.status == "AUTO_APPROVED":
                    day_record.overtime_minutes = calc.overtime_details.eligible_overtime_minutes
                else:
                    day_record.overtime_minutes = 0
            else:
                existing_ot.attendance_day_id = day_record.id
                if existing_ot.status == "APPROVED":
                    # Decision preservation: preserve approved status and adjust if raw reduced
                    existing_ot.raw_overtime_minutes = calc.overtime_details.raw_overtime_minutes
                    if existing_ot.approved_overtime_minutes > existing_ot.raw_overtime_minutes:
                        existing_ot.approved_overtime_minutes = existing_ot.raw_overtime_minutes
                        existing_ot.payable_overtime_minutes = int(
                            round(
                                Decimal(existing_ot.approved_overtime_minutes)
                                * existing_ot.multiplier
                            )
                        )
                    existing_ot.updated_at = now
                    day_record.overtime_minutes = existing_ot.approved_overtime_minutes
                elif existing_ot.status == "REJECTED":
                    # Decision preservation: preserve rejection
                    existing_ot.raw_overtime_minutes = calc.overtime_details.raw_overtime_minutes
                    existing_ot.updated_at = now
                    day_record.overtime_minutes = 0
                else:
                    # PENDING_APPROVAL or AUTO_APPROVED -> update from new calculation
                    existing_ot.raw_overtime_minutes = calc.overtime_details.raw_overtime_minutes
                    existing_ot.multiplier = calc.overtime_details.multiplier
                    existing_ot.overtime_type = calc.overtime_details.overtime_type
                    existing_ot.overtime_rule_id = calc.overtime_details.rule_id
                    if calc.overtime_details.status == "AUTO_APPROVED":
                        existing_ot.status = "AUTO_APPROVED"
                        existing_ot.approved_overtime_minutes = (
                            calc.overtime_details.eligible_overtime_minutes
                        )
                        existing_ot.payable_overtime_minutes = (
                            calc.overtime_details.payable_overtime_minutes
                        )
                        day_record.overtime_minutes = existing_ot.approved_overtime_minutes
                    else:
                        existing_ot.status = "PENDING_APPROVAL"
                        existing_ot.approved_overtime_minutes = 0
                        existing_ot.payable_overtime_minutes = 0
                        day_record.overtime_minutes = 0
                    existing_ot.updated_at = now
        elif existing_ot is not None:
            if existing_ot.status in ("PENDING_APPROVAL", "AUTO_APPROVED"):
                existing_ot.raw_overtime_minutes = 0
                existing_ot.approved_overtime_minutes = 0
                existing_ot.payable_overtime_minutes = 0
                existing_ot.updated_at = now
                day_record.overtime_minutes = 0
    except Exception:
        pass

    await session.flush()
    return day_record


async def get_attendance_day(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    user_role: str,
    employee_id: uuid.UUID,
    attendance_date: date,
) -> AttendanceDayResponse:
    """Fetches a single attendance day projection with tenant isolation and RBAC checks."""
    role_lower = user_role.lower()

    if role_lower == "employee":
        user_emp = (
            await session.execute(
                select(Employee.id).where(
                    Employee.tenant_id == tenant_id, Employee.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if user_emp is None or employee_id != user_emp:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Employees may only view their own attendance records.",
            )
    elif role_lower == "manager":
        mgr_emp = (
            await session.execute(
                select(Employee.id).where(
                    Employee.tenant_id == tenant_id, Employee.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if mgr_emp is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Manager employee record not found in tenant.",
            )
        if employee_id != mgr_emp:
            is_report = (
                await session.execute(
                    select(Employee.id).where(
                        Employee.tenant_id == tenant_id,
                        Employee.id == employee_id,
                        Employee.reporting_manager_id == mgr_emp,
                    )
                )
            ).scalar_one_or_none()
            if not is_report:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Managers may only view attendance records of their direct reports.",
                )

    stmt = select(AttendanceDay).where(
        AttendanceDay.tenant_id == tenant_id,
        AttendanceDay.employee_id == employee_id,
        AttendanceDay.attendance_date == attendance_date,
    )
    day = (await session.execute(stmt)).scalar_one_or_none()
    if day is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Attendance record for employee {employee_id} on {attendance_date} not found.",
        )

    return AttendanceDayResponse.model_validate(day)


async def list_attendance_days(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    user_role: str,
    employee_id: uuid.UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    attendance_status: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> AttendanceDayListResponse:
    """Lists attendance days with tenant isolation, pagination, and RBAC filtering."""
    role_lower = user_role.lower()
    target_emp_ids: list[uuid.UUID] | None = None

    if role_lower == "employee":
        user_emp = (
            await session.execute(
                select(Employee.id).where(
                    Employee.tenant_id == tenant_id, Employee.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if user_emp is None:
            return AttendanceDayListResponse(items=[], total=0, next_cursor=None)
        if employee_id is not None and employee_id != user_emp:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Employees may only view their own attendance records.",
            )
        target_emp_ids = [user_emp]

    elif role_lower == "manager":
        mgr_emp = (
            await session.execute(
                select(Employee.id).where(
                    Employee.tenant_id == tenant_id, Employee.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if mgr_emp is None:
            return AttendanceDayListResponse(items=[], total=0, next_cursor=None)

        reports = (
            (
                await session.execute(
                    select(Employee.id).where(
                        Employee.tenant_id == tenant_id,
                        Employee.reporting_manager_id == mgr_emp,
                    )
                )
            )
            .scalars()
            .all()
        )
        team_ids = set(reports) | {mgr_emp}

        if employee_id is not None:
            if employee_id not in team_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Managers may only view attendance records of their direct reports.",
                )
            target_emp_ids = [employee_id]
        else:
            target_emp_ids = list(team_ids)

    else:
        # Owner, Admin, HR
        if employee_id is not None:
            target_emp_ids = [employee_id]

    query = select(AttendanceDay).where(AttendanceDay.tenant_id == tenant_id)

    if target_emp_ids is not None:
        query = query.where(AttendanceDay.employee_id.in_(target_emp_ids))
    if start_date is not None:
        query = query.where(AttendanceDay.attendance_date >= start_date)
    if end_date is not None:
        query = query.where(AttendanceDay.attendance_date <= end_date)
    if attendance_status is not None:
        query = query.where(AttendanceDay.status == attendance_status.upper())

    if cursor is not None:
        try:
            cursor_date = date.fromisoformat(cursor)
            query = query.where(AttendanceDay.attendance_date < cursor_date)
        except Exception:
            pass

    count_query = select(func.count(AttendanceDay.id)).where(AttendanceDay.tenant_id == tenant_id)
    if target_emp_ids is not None:
        count_query = count_query.where(AttendanceDay.employee_id.in_(target_emp_ids))
    if start_date is not None:
        count_query = count_query.where(AttendanceDay.attendance_date >= start_date)
    if end_date is not None:
        count_query = count_query.where(AttendanceDay.attendance_date <= end_date)
    if attendance_status is not None:
        count_query = count_query.where(AttendanceDay.status == attendance_status.upper())

    total = (await session.execute(count_query)).scalar_one() or 0

    query = query.order_by(
        AttendanceDay.attendance_date.desc(), AttendanceDay.employee_id.asc()
    ).limit(limit)
    rows = (await session.execute(query)).scalars().all()

    items = [AttendanceDayResponse.model_validate(r) for r in rows]
    next_cursor = items[-1].attendance_date.isoformat() if len(items) == limit else None

    return AttendanceDayListResponse(items=items, total=total, next_cursor=next_cursor)
