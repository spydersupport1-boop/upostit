"""Service layer for administrative attendance corrections, event audit history, and recalculation."""

import hashlib
import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.attendance.models import (
    AttendanceDay,
    AttendanceEvent,
    AttendanceIdempotencyRecord,
)
from services.api.attendance.schemas import (
    AttendanceCorrectionCreateRequest,
    AttendanceCorrectionListResponse,
    AttendanceCorrectionResponse,
    AttendanceCorrectionType,
    AttendanceDayResponse,
    AttendanceEventAuditListResponse,
    AttendanceEventAuditResponse,
    AttendanceEventResponse,
)
from services.api.attendance.service import (
    determine_shift_date_for_punch,
    recalculate_attendance_day,
    resolve_employee_shift_version,
)
from services.api.employees.models import Employee
from services.api.tenants.models import Tenant

logger = logging.getLogger("attendance.corrections")


def _compute_correction_fingerprint(
    tenant_id: uuid.UUID,
    payload: AttendanceCorrectionCreateRequest,
) -> str:
    """Computes a deterministic SHA-256 hash for a correction request to detect payload divergence."""
    eff_iso = payload.effective_at.isoformat() if payload.effective_at else ""
    target_id_str = str(payload.supersedes_event_id) if payload.supersedes_event_id else ""
    raw = (
        f"{tenant_id}:{payload.employee_id}:{payload.correction_type.value}:"
        f"{payload.event_type}:{eff_iso}:{target_id_str}:{payload.correction_reason.strip()}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _verify_actor_correction_permission(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    actor_role: str,
    target_employee_id: uuid.UUID,
) -> None:
    """Verifies that the actor has permission to correct the target employee's attendance.

    - OWNER, ADMIN, HR: Can correct any employee in the tenant.
    - MANAGER: Can only correct direct reports within their reporting hierarchy.
    - EMPLOYEE: Strictly forbidden from making direct attendance corrections.
    """
    role = actor_role.lower()
    if role == "employee":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employees cannot directly submit attendance corrections.",
        )

    if role in ("owner", "admin", "hr"):
        return

    if role == "manager":
        # Lookup manager's own employee record in the tenant
        mgr_emp_id = (
            await session.execute(
                select(Employee.id).where(
                    Employee.tenant_id == tenant_id,
                    Employee.user_id == actor_user_id,
                )
            )
        ).scalar_one_or_none()

        if mgr_emp_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Manager employee profile not found in tenant.",
            )

        if target_employee_id == mgr_emp_id:
            # Managers cannot administratively correct their own attendance directly
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Managers cannot correct their own attendance records.",
            )

        # Check if target employee reports to this manager
        is_report = (
            await session.execute(
                select(Employee.id).where(
                    Employee.tenant_id == tenant_id,
                    Employee.id == target_employee_id,
                    Employee.reporting_manager_id == mgr_emp_id,
                )
            )
        ).scalar_one_or_none()

        if not is_report:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Managers may only correct attendance records of their direct reports.",
            )
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient privileges to submit attendance corrections.",
    )


async def apply_attendance_correction(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    actor_role: str,
    payload: AttendanceCorrectionCreateRequest,
) -> AttendanceCorrectionResponse:
    """Applies an administrative attendance correction atomically with full audit history and recalculation.

    Guarantees:
    - Target event immutability (original events are never modified or deleted).
    - Idempotency with payload mismatch protection.
    - Strict validation against cyclic, double-supersede, or void-of-void chains.
    - Pessimistic employee row locking to serialize corrections.
    - Atomic recalculation of all affected shift dates and overnight boundaries.
    """
    # 1. RBAC & Manager Scope Check
    await _verify_actor_correction_permission(
        session, tenant_id, actor_user_id, actor_role, payload.employee_id
    )

    # 2. Acquire pessimistic lock on Employee row to serialize corrections & recalculations
    emp_stmt = (
        select(Employee.id)
        .where(Employee.tenant_id == tenant_id, Employee.id == payload.employee_id)
        .with_for_update()
    )
    emp_exists = (await session.execute(emp_stmt)).scalar_one_or_none()
    if not emp_exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target employee {payload.employee_id} not found in tenant.",
        )

    # 3. Idempotency Check & Fingerprinting
    req_fingerprint = _compute_correction_fingerprint(tenant_id, payload)
    idem_stmt = (
        select(AttendanceIdempotencyRecord)
        .where(
            AttendanceIdempotencyRecord.tenant_id == tenant_id,
            AttendanceIdempotencyRecord.idempotency_key == payload.idempotency_key,
        )
        .with_for_update()
    )
    existing_idem = (await session.execute(idem_stmt)).scalar_one_or_none()

    if existing_idem is not None:
        if existing_idem.request_fingerprint != req_fingerprint:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency key reused with mismatched correction payload.",
            )
        if existing_idem.status == "COMPLETED" and existing_idem.response_payload:
            # Replay cached completed correction response
            cached_data = existing_idem.response_payload
            cached_data["idempotent_replay"] = True
            return AttendanceCorrectionResponse.model_validate(cached_data)
        if existing_idem.status == "IN_PROGRESS":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A concurrent correction request with this idempotency key is already processing.",
            )

    # Register in-progress idempotency record
    if existing_idem is None:
        idem_record = AttendanceIdempotencyRecord(
            tenant_id=tenant_id,
            employee_id=payload.employee_id,
            idempotency_key=payload.idempotency_key,
            request_fingerprint=req_fingerprint,
            status="IN_PROGRESS",
            created_at=datetime.now(UTC),
        )
        session.add(idem_record)
        await session.flush()
    else:
        idem_record = existing_idem

    # 4. Target Event Verification for SUPERSEDE and VOID
    target_event: AttendanceEvent | None = None
    if payload.correction_type in (
        AttendanceCorrectionType.CORRECTION_SUPERSEDE,
        AttendanceCorrectionType.CORRECTION_VOID,
    ):
        target_stmt = select(AttendanceEvent).where(
            AttendanceEvent.tenant_id == tenant_id,
            AttendanceEvent.id == payload.supersedes_event_id,
        )
        target_event = (await session.execute(target_stmt)).scalar_one_or_none()
        if target_event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Target attendance event {payload.supersedes_event_id} not found.",
            )

        # Disallow correcting an event belonging to another employee
        if target_event.employee_id != payload.employee_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot correct an attendance event belonging to a different employee.",
            )

        # Disallow voiding/superseding a voiding tombstone
        if target_event.event_category == AttendanceCorrectionType.CORRECTION_VOID.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot supersede or void an existing voiding tombstone event.",
            )

        # Check if the target event is ALREADY superseded or voided
        chain_stmt = select(AttendanceEvent.id, AttendanceEvent.event_category).where(
            AttendanceEvent.tenant_id == tenant_id,
            AttendanceEvent.supersedes_event_id == target_event.id,
        )
        existing_children = (await session.execute(chain_stmt)).fetchall()
        for child in existing_children:
            if child.event_category == AttendanceCorrectionType.CORRECTION_VOID.value:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot correct an attendance event that has already been voided.",
                )
            if child.event_category == AttendanceCorrectionType.CORRECTION_SUPERSEDE.value:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot correct an attendance event that has already been superseded.",
                )

    # 5. Resolve Effective Timestamps and Event Types
    if payload.correction_type == AttendanceCorrectionType.CORRECTION_VOID:
        eff_timestamp = payload.effective_at or (
            target_event.effective_at if target_event else datetime.now(UTC)
        )
        eff_event_type = (
            payload.event_type
            if payload.event_type
            else (target_event.event_type if target_event else "CHECK_IN")
        )
    else:
        assert payload.effective_at is not None
        eff_timestamp = payload.effective_at
        eff_event_type = payload.event_type

    if eff_timestamp.tzinfo is None:
        eff_timestamp = eff_timestamp.replace(tzinfo=UTC)

    # 6. Append New Immutable Correction Event to the Ledger
    correction_event = AttendanceEvent(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=payload.employee_id,
        event_type=eff_event_type,
        event_category=payload.correction_type.value,
        supersedes_event_id=payload.supersedes_event_id,
        correction_reason=payload.correction_reason.strip(),
        created_at=datetime.now(UTC),
        server_received_at=datetime.now(UTC),
        effective_at=eff_timestamp,
        source="ADMIN",
        review_status="NOT_REQUIRED",
        timestamp_verification_status="SERVER_AUTHORITATIVE",
        idempotency_key=payload.idempotency_key,
        location_id=payload.location_id,
        actor_user_id=actor_user_id,
        metadata_json={
            "actor_user_id": str(actor_user_id),
            "actor_role": actor_role,
            "correction_type": payload.correction_type.value,
            **payload.metadata,
        },
    )
    session.add(correction_event)
    await session.flush()

    # 7. Identify Affected Calendar Shift Dates
    tz_stmt = select(Tenant.timezone).where(Tenant.id == tenant_id)
    tz_name = (await session.execute(tz_stmt)).scalar_one_or_none() or "UTC"

    affected_dates: set[date] = set()

    # Primary date of the correction event
    primary_date = await determine_shift_date_for_punch(
        session=session,
        tenant_id=tenant_id,
        employee_id=payload.employee_id,
        effective_at=eff_timestamp,
        event_type=eff_event_type,
        tenant_timezone=tz_name,
    )
    affected_dates.add(primary_date)

    # If superseding or voiding, also include original target event's shift date
    if target_event is not None:
        target_shift_date = await determine_shift_date_for_punch(
            session=session,
            tenant_id=tenant_id,
            employee_id=payload.employee_id,
            effective_at=target_event.effective_at,
            event_type=target_event.event_type,
            tenant_timezone=tz_name,
        )
        affected_dates.add(target_shift_date)

    # Overnight & adjacent shift protection: if correction occurs near boundary, evaluate adjacent days
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")

    for cand_d in (primary_date - timedelta(days=1), primary_date + timedelta(days=1)):
        _, cand_ver = await resolve_employee_shift_version(
            session, tenant_id, payload.employee_id, cand_d
        )
        if cand_ver is not None:
            c_start = datetime.combine(cand_d, cand_ver.start_time, tzinfo=tz).astimezone(UTC)
            if cand_ver.is_overnight:
                c_end = datetime.combine(
                    cand_d + timedelta(days=1), cand_ver.end_time, tzinfo=tz
                ).astimezone(UTC)
            else:
                c_end = datetime.combine(cand_d, cand_ver.end_time, tzinfo=tz).astimezone(UTC)
            w_start = c_start - timedelta(minutes=cand_ver.early_arrival_allowance_minutes)
            w_end = c_end + timedelta(minutes=cand_ver.late_departure_allowance_minutes)
            if w_start <= eff_timestamp <= w_end:
                affected_dates.add(cand_d)

    # 8. Recalculate Attendance Day Projections Atomically
    recalculated_days: list[AttendanceDay] = []
    for d in sorted(affected_dates):
        day = await recalculate_attendance_day(
            session=session,
            tenant_id=tenant_id,
            employee_id=payload.employee_id,
            attendance_date=d,
        )
        recalculated_days.append(day)

    # 9. Finalize Idempotency Record
    response_data = AttendanceCorrectionResponse(
        correction_event=AttendanceEventResponse.model_validate(correction_event),
        affected_attendance_dates=sorted(affected_dates),
        recalculated_days=[AttendanceDayResponse.model_validate(d) for d in recalculated_days],
        idempotent_replay=False,
    )

    idem_record.status = "COMPLETED"
    idem_record.event_id = correction_event.id
    idem_record.response_payload = response_data.model_dump(mode="json")
    idem_record.expires_at = None  # Permanent retention for audit
    await session.flush()

    return response_data


async def list_attendance_corrections(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    user_role: str,
    employee_id: uuid.UUID | None = None,
    correction_type: AttendanceCorrectionType | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> AttendanceCorrectionListResponse:
    """Lists administrative attendance corrections with tenant isolation, pagination, and RBAC scoping."""
    role = user_role.lower()

    stmt = select(AttendanceEvent).where(
        AttendanceEvent.tenant_id == tenant_id,
        AttendanceEvent.event_category.in_(
            [
                AttendanceCorrectionType.CORRECTION_INSERT.value,
                AttendanceCorrectionType.CORRECTION_SUPERSEDE.value,
                AttendanceCorrectionType.CORRECTION_VOID.value,
            ]
        ),
    )

    # RBAC Filtering
    if role == "employee":
        user_emp = (
            await session.execute(
                select(Employee.id).where(
                    Employee.tenant_id == tenant_id, Employee.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if user_emp is None:
            return AttendanceCorrectionListResponse(items=[], total=0, next_cursor=None)
        if employee_id is not None and employee_id != user_emp:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Employees may only view corrections on their own record.",
            )
        stmt = stmt.where(AttendanceEvent.employee_id == user_emp)

    elif role == "manager":
        mgr_emp = (
            await session.execute(
                select(Employee.id).where(
                    Employee.tenant_id == tenant_id, Employee.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if mgr_emp is None:
            return AttendanceCorrectionListResponse(items=[], total=0, next_cursor=None)

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
        team_ids = set(reports)

        if employee_id is not None:
            if employee_id not in team_ids and employee_id != mgr_emp:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Managers may only view corrections for their direct reports.",
                )
            stmt = stmt.where(AttendanceEvent.employee_id == employee_id)
        else:
            stmt = stmt.where(AttendanceEvent.employee_id.in_(list(team_ids)))

    elif employee_id is not None:
        stmt = stmt.where(AttendanceEvent.employee_id == employee_id)

    if correction_type is not None:
        stmt = stmt.where(AttendanceEvent.event_category == correction_type.value)

    if start_date is not None:
        dt_start = datetime.combine(start_date, datetime.min.time(), tzinfo=UTC)
        stmt = stmt.where(AttendanceEvent.effective_at >= dt_start)

    if end_date is not None:
        dt_end = datetime.combine(end_date, datetime.max.time(), tzinfo=UTC)
        stmt = stmt.where(AttendanceEvent.effective_at <= dt_end)

    # Cursor pagination
    if cursor is not None:
        try:
            cursor_dt = datetime.fromisoformat(cursor)
            stmt = stmt.where(AttendanceEvent.created_at < cursor_dt)
        except ValueError:
            pass

    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(AttendanceEvent.created_at.desc()).limit(limit + 1)
    rows = (await session.execute(stmt)).scalars().all()

    items = rows[:limit]
    next_cursor = items[-1].created_at.isoformat() if len(rows) > limit else None

    return AttendanceCorrectionListResponse(
        items=[AttendanceEventResponse.model_validate(r) for r in items],
        total=total,
        next_cursor=next_cursor,
    )


async def get_attendance_day_event_audit_trail(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    user_role: str,
    record_id: uuid.UUID,
) -> AttendanceEventAuditListResponse:
    """Retrieves the complete immutable audit trail of presence and correction events for an attendance day.

    Annotates events with active, superseded, or voided statuses.
    """
    # 1. Fetch target AttendanceDay
    day_stmt = select(AttendanceDay).where(
        AttendanceDay.tenant_id == tenant_id,
        AttendanceDay.id == record_id,
    )
    day = (await session.execute(day_stmt)).scalar_one_or_none()
    if day is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Attendance record {record_id} not found in tenant.",
        )

    # 2. RBAC Verification
    role = user_role.lower()
    if role == "employee":
        user_emp = (
            await session.execute(
                select(Employee.id).where(
                    Employee.tenant_id == tenant_id, Employee.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if user_emp != day.employee_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Employees may only inspect their own attendance event audit trail.",
            )

    elif role == "manager":
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
                detail="Manager profile not found in tenant.",
            )
        if day.employee_id != mgr_emp:
            is_report = (
                await session.execute(
                    select(Employee.id).where(
                        Employee.tenant_id == tenant_id,
                        Employee.id == day.employee_id,
                        Employee.reporting_manager_id == mgr_emp,
                    )
                )
            ).scalar_one_or_none()
            if not is_report:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Managers may only inspect attendance records of their direct reports.",
                )

    # 3. Determine Shift Resolution Window for the date
    tz_stmt = select(Tenant.timezone).where(Tenant.id == tenant_id)
    tz_name = (await session.execute(tz_stmt)).scalar_one_or_none() or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")

    _, version = await resolve_employee_shift_version(
        session, tenant_id, day.employee_id, day.attendance_date
    )

    if version is not None:
        c_start = datetime.combine(day.attendance_date, version.start_time, tzinfo=tz).astimezone(
            UTC
        )
        if version.is_overnight:
            c_end = datetime.combine(
                day.attendance_date + timedelta(days=1), version.end_time, tzinfo=tz
            ).astimezone(UTC)
        else:
            c_end = datetime.combine(day.attendance_date, version.end_time, tzinfo=tz).astimezone(
                UTC
            )
        w_start = c_start - timedelta(minutes=version.early_arrival_allowance_minutes)
        w_end = c_end + timedelta(minutes=version.late_departure_allowance_minutes)
    else:
        w_start = datetime.combine(day.attendance_date, datetime.min.time(), tzinfo=tz).astimezone(
            UTC
        )
        w_end = datetime.combine(day.attendance_date, datetime.max.time(), tzinfo=tz).astimezone(
            UTC
        )

    # 4. Fetch All Events Contributing to this Day (by window or by source_event_ids)
    source_uuids: list[uuid.UUID] = []
    if day.source_event_ids:
        for sid in day.source_event_ids:
            try:
                source_uuids.append(uuid.UUID(sid))
            except (ValueError, TypeError):
                pass

    ev_stmt = (
        select(AttendanceEvent)
        .where(
            AttendanceEvent.tenant_id == tenant_id,
            AttendanceEvent.employee_id == day.employee_id,
            ((AttendanceEvent.effective_at >= w_start) & (AttendanceEvent.effective_at <= w_end))
            | (AttendanceEvent.id.in_(source_uuids) if source_uuids else False),
        )
        .order_by(AttendanceEvent.server_received_at.asc(), AttendanceEvent.created_at.asc())
    )
    all_events = list((await session.execute(ev_stmt)).scalars().all())

    # Map supersessions and voids
    superseded_by_map: dict[uuid.UUID, uuid.UUID] = {}
    voided_by_map: dict[uuid.UUID, uuid.UUID] = {}

    for e in all_events:
        if e.supersedes_event_id:
            if e.event_category == AttendanceCorrectionType.CORRECTION_VOID.value:
                voided_by_map[e.supersedes_event_id] = e.id
            elif e.event_category == AttendanceCorrectionType.CORRECTION_SUPERSEDE.value:
                superseded_by_map[e.supersedes_event_id] = e.id

    # 5. Build Annotated Audit DTOs
    audit_items: list[AttendanceEventAuditResponse] = []
    for e in all_events:
        is_active = True
        sup_by = superseded_by_map.get(e.id)
        void_by = voided_by_map.get(e.id)
        if (
            sup_by
            or void_by
            or e.event_category == AttendanceCorrectionType.CORRECTION_VOID.value
            or e.review_status == "REJECTED"
        ):
            is_active = False

        audit_items.append(
            AttendanceEventAuditResponse(
                id=e.id,
                tenant_id=e.tenant_id,
                employee_id=e.employee_id,
                event_type=e.event_type,
                event_category=e.event_category,
                effective_at=e.effective_at,
                server_received_at=e.server_received_at,
                supersedes_event_id=e.supersedes_event_id,
                correction_reason=e.correction_reason,
                actor_user_id=e.actor_user_id,
                source=e.source,
                review_status=e.review_status,
                timestamp_verification_status=e.timestamp_verification_status,
                is_active=is_active,
                superseded_by_event_id=sup_by,
                voided_by_event_id=void_by,
                created_at=e.created_at,
            )
        )

    return AttendanceEventAuditListResponse(
        items=audit_items,
        total=len(audit_items),
    )
