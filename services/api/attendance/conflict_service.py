"""Service layer for Phase 8 Offline Attendance Conflict Resolution and Employee APIs.

Handles:
1. Validating and packaging employee-submitted OfflineSequenceConflictBundle payloads.
2. Canonical SHA-256 fingerprinting for idempotency replay and tampering prevention.
3. Concurrency-safe incident persistence in attendance_conflict_incidents.
4. Sanitized employee query endpoint for tracking conflict status and decisions.
"""

import hashlib
import json
import uuid
from datetime import UTC, date, datetime, time
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.attendance.correction_service import apply_attendance_correction
from services.api.attendance.models import AttendanceConflictIncident
from services.api.attendance.schemas import (
    AttendanceConflictDecisionRequest,
    AttendanceConflictDecisionResponse,
    AttendanceConflictIncidentDetailResponse,
    AttendanceCorrectionCreateRequest,
    AttendanceCorrectionType,
    ConflictIncidentEmployeeDetail,
    EmployeeConflictIncidentListResponse,
    EmployeeConflictIncidentSummary,
    OfflineConflictBundleSubmitRequest,
    OfflineConflictIncidentResponse,
    SupervisorConflictQueueItem,
    SupervisorConflictQueueListResponse,
)
from services.api.employees.models import Employee
from services.api.locations.models import Location
from services.api.organization.models import Department


def compute_conflict_bundle_fingerprint(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    payload: OfflineConflictBundleSubmitRequest,
) -> str:
    """Computes a deterministic SHA-256 fingerprint for conflict bundle deduplication and tampering detection.

    Canonicalizes:
    - tenant_id
    - employee_id
    - bundle_id
    - session_id
    - primary_rejected_event core telemetry (event_type, idempotency_key, device_reported_at UTC, coordinates, device hash)
    - dependent_events core telemetry (ordered, event_type, idempotency_key, device_reported_at UTC, coordinates)

    Excludes volatile transport metadata (e.g. client network retry timestamps).
    """
    prim = payload.primary_rejected_event
    prim_dict = {
        "event_type": prim.event_type,
        "idempotency_key": prim.idempotency_key.strip(),
        "device_reported_at": prim.device_reported_at.astimezone(UTC).isoformat(),
        "latitude": round(prim.latitude, 6) if prim.latitude is not None else None,
        "longitude": round(prim.longitude, 6) if prim.longitude is not None else None,
        "device_id_hash": prim.device_id_hash.strip() if prim.device_id_hash else None,
    }

    deps_list = [
        {
            "event_type": dep.event_type,
            "idempotency_key": dep.idempotency_key.strip(),
            "device_reported_at": dep.device_reported_at.astimezone(UTC).isoformat(),
            "latitude": round(dep.latitude, 6) if dep.latitude is not None else None,
            "longitude": round(dep.longitude, 6) if dep.longitude is not None else None,
            "device_id_hash": dep.device_id_hash.strip() if dep.device_id_hash else None,
        }
        for dep in payload.dependent_events
    ]

    canonical_obj: dict[str, Any] = {
        "tenant_id": str(tenant_id),
        "employee_id": str(employee_id),
        "bundle_id": payload.bundle_id.strip(),
        "session_id": payload.session_id.strip() if payload.session_id else None,
        "primary_rejected_event": prim_dict,
        "dependent_events": deps_list,
    }

    encoded = json.dumps(canonical_obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


async def submit_offline_conflict_bundle(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    user_role: str,
    payload: OfflineConflictBundleSubmitRequest,
) -> OfflineConflictIncidentResponse:
    """Ingests and validates an employee-submitted offline attendance conflict bundle.

    Guarantees:
    - Authenticated employee identity derivation (never trusts client-supplied ownership).
    - Idempotent replay on identical retries.
    - Rejection (HTTP 409) if bundle_id is reused with mismatched payload.
    - Concurrency-safe unique constraint race handling.
    - Zero modification of the raw attendance ledger (attendance_events).
    """
    # 1. Resolve Target Employee & Verify Caller Ownership
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
                    detail="Employees and Managers can only submit conflict bundles for their own attendance.",
                )
    else:
        if user_emp is not None:
            target_employee_id = user_emp.id
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No employee profile linked to current user.",
            )

    # Verify target employee exists in tenant
    emp_exists = (
        await session.execute(
            select(Employee.id).where(
                Employee.tenant_id == tenant_id,
                Employee.id == target_employee_id,
            )
        )
    ).scalar_one_or_none()
    if not emp_exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target employee not found in this organization.",
        )

    # 2. Compute Canonical Request Fingerprint
    clean_bundle_id = payload.bundle_id.strip()
    fingerprint = compute_conflict_bundle_fingerprint(tenant_id, target_employee_id, payload)

    # 3. Idempotency Check: Existing Incident with same bundle_id
    existing_stmt = select(AttendanceConflictIncident).where(
        AttendanceConflictIncident.tenant_id == tenant_id,
        AttendanceConflictIncident.bundle_id == clean_bundle_id,
    )
    existing_incident = (await session.execute(existing_stmt)).scalar_one_or_none()

    if existing_incident is not None:
        stored_fingerprint = existing_incident.metadata_json.get("request_fingerprint")
        if stored_fingerprint == fingerprint:
            # Replay existing incident idempotently
            res = OfflineConflictIncidentResponse.model_validate(existing_incident)
            res.idempotent_replay = True
            return res
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bundle ID reused with mismatched conflict payload.",
        )

    # 4. Prepare New Incident Record
    total_events = 1 + len(payload.dependent_events)
    rejection_summary = payload.primary_rejected_event.server_rejection_reason
    if not rejection_summary and payload.primary_rejected_event.server_rejection_code:
        rejection_summary = (
            f"Rejected with HTTP {payload.primary_rejected_event.server_rejection_code}"
        )

    new_incident = AttendanceConflictIncident(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=target_employee_id,
        user_id=user_id,
        bundle_id=clean_bundle_id,
        session_id=payload.session_id.strip() if payload.session_id else None,
        status="PENDING_REVIEW",
        primary_rejected_event=payload.primary_rejected_event.model_dump(mode="json"),
        dependent_events=[d.model_dump(mode="json") for d in payload.dependent_events],
        total_events_count=total_events,
        rejection_summary=rejection_summary[:255] if rejection_summary else None,
        employee_notes=payload.employee_notes.strip() if payload.employee_notes else None,
        submitted_at=datetime.now(UTC),
        metadata_json={
            "request_fingerprint": fingerprint,
            "submitted_by_role": user_role,
        },
        resolved_correction_event_ids=[],
    )

    session.add(new_incident)

    # 5. Flush with Concurrency Race Catch
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        # Handle concurrent race: re-check if bundle_id was just inserted
        race_incident = (await session.execute(existing_stmt)).scalar_one_or_none()
        if race_incident is not None:
            if race_incident.metadata_json.get("request_fingerprint") == fingerprint:
                res = OfflineConflictIncidentResponse.model_validate(race_incident)
                res.idempotent_replay = True
                return res
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Bundle ID reused with mismatched conflict payload.",
            )
        raise

    res = OfflineConflictIncidentResponse.model_validate(new_incident)
    res.idempotent_replay = False
    return res


async def list_my_offline_conflict_incidents(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    status_filter: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 20,
    cursor: str | None = None,
) -> EmployeeConflictIncidentListResponse:
    """Lists attendance conflict incidents for the authenticated employee with cursor pagination.

    Enforces strict employee isolation: callers never see other employees' incidents.
    Sanitizes response to omit internal reviewer user IDs and supervisor notes.
    """
    # 1. Resolve Employee ID for caller
    emp_stmt = select(Employee.id).where(
        Employee.tenant_id == tenant_id,
        Employee.user_id == user_id,
    )
    emp_id = (await session.execute(emp_stmt)).scalar_one_or_none()

    if emp_id is None:
        return EmployeeConflictIncidentListResponse(
            items=[],
            total=0,
            limit=limit,
            cursor=None,
            has_more=False,
        )

    # 2. Build Base Query
    base_conditions = [
        AttendanceConflictIncident.tenant_id == tenant_id,
        AttendanceConflictIncident.employee_id == emp_id,
    ]

    if status_filter:
        clean_status = status_filter.strip().upper()
        base_conditions.append(AttendanceConflictIncident.status == clean_status)

    if start_date:
        start_dt = datetime.combine(start_date, time.min, tzinfo=UTC)
        base_conditions.append(AttendanceConflictIncident.submitted_at >= start_dt)

    if end_date:
        end_dt = datetime.combine(end_date, time.max, tzinfo=UTC)
        base_conditions.append(AttendanceConflictIncident.submitted_at <= end_dt)

    # Total Count Query
    count_stmt = select(func.count(AttendanceConflictIncident.id)).where(*base_conditions)
    total_count = (await session.execute(count_stmt)).scalar() or 0

    # Paginated Query
    query = select(AttendanceConflictIncident).where(*base_conditions)

    if cursor:
        try:
            cursor_dt = datetime.fromisoformat(cursor)
            query = query.where(AttendanceConflictIncident.submitted_at < cursor_dt)
        except (ValueError, TypeError):
            pass

    query = query.order_by(
        AttendanceConflictIncident.submitted_at.desc(),
        AttendanceConflictIncident.id.desc(),
    ).limit(limit + 1)

    records = (await session.execute(query)).scalars().all()

    has_more = len(records) > limit
    page_records = records[:limit]

    # Generate next cursor
    next_cursor = page_records[-1].submitted_at.isoformat() if has_more and page_records else None

    # Map to sanitized summary DTOs
    items: list[EmployeeConflictIncidentSummary] = []
    for r in page_records:
        prim = r.primary_rejected_event or {}
        p_type = prim.get("event_type", "CHECK_IN")
        p_time_raw = prim.get("device_reported_at")
        if isinstance(p_time_raw, str):
            try:
                p_time = datetime.fromisoformat(p_time_raw)
            except ValueError:
                p_time = r.submitted_at
        elif isinstance(p_time_raw, datetime):
            p_time = p_time_raw
        else:
            p_time = r.submitted_at

        items.append(
            EmployeeConflictIncidentSummary(
                id=r.id,
                bundle_id=r.bundle_id,
                session_id=r.session_id,
                status=r.status,
                total_events_count=r.total_events_count,
                primary_event_type=p_type,
                primary_event_timestamp=p_time,
                rejection_summary=r.rejection_summary,
                employee_notes=r.employee_notes,
                submitted_at=r.submitted_at,
                decision=r.decision,
                decision_reason=r.decision_reason,
                decided_at=r.decided_at,
                resolved_events_count=len(r.resolved_correction_event_ids or []),
            )
        )

    return EmployeeConflictIncidentListResponse(
        items=items,
        total=total_count,
        limit=limit,
        cursor=next_cursor,
        has_more=has_more,
    )


async def list_supervisor_conflict_queue(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    user_role: str,
    status_filter: str | None = None,
    employee_id: uuid.UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> SupervisorConflictQueueListResponse:
    """Lists attendance conflict incidents for supervisor review with tenant and reporting isolation.

    Enforces:
    - EMPLOYEE is denied (HTTP 403 Forbidden).
    - MANAGER sees only direct reports (Employee.reporting_manager_id == mgr_emp_id).
    - HR, ADMIN, and OWNER see all tenant incidents.
    - Tenant isolation at query level.
    """
    role = user_role.lower()
    if role == "employee":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employees cannot access the supervisor conflict review queue.",
        )

    mgr_emp_id: uuid.UUID | None = None
    if role == "manager":
        mgr_stmt = select(Employee.id).where(
            Employee.tenant_id == tenant_id,
            Employee.user_id == user_id,
        )
        mgr_emp_id = (await session.execute(mgr_stmt)).scalar_one_or_none()
        if mgr_emp_id is None:
            # Manager has no employee profile in this tenant, thus no direct reports
            return SupervisorConflictQueueListResponse(
                items=[],
                total=0,
                limit=limit,
                cursor=None,
                has_more=False,
            )

    # Build filter conditions
    conditions = [AttendanceConflictIncident.tenant_id == tenant_id]

    if status_filter:
        conditions.append(AttendanceConflictIncident.status == status_filter.strip().upper())

    if employee_id:
        conditions.append(AttendanceConflictIncident.employee_id == employee_id)

    if start_date:
        start_dt = datetime.combine(start_date, time.min, tzinfo=UTC)
        conditions.append(AttendanceConflictIncident.submitted_at >= start_dt)

    if end_date:
        end_dt = datetime.combine(end_date, time.max, tzinfo=UTC)
        conditions.append(AttendanceConflictIncident.submitted_at <= end_dt)

    # Manager reporting hierarchy filter
    if role == "manager":
        conditions.append(Employee.reporting_manager_id == mgr_emp_id)

    # Total Count Query
    count_stmt = (
        select(func.count(AttendanceConflictIncident.id))
        .join(
            Employee,
            (AttendanceConflictIncident.tenant_id == Employee.tenant_id)
            & (AttendanceConflictIncident.employee_id == Employee.id),
        )
        .where(*conditions)
    )
    total_count = (await session.execute(count_stmt)).scalar() or 0

    # Paginated Query
    query = (
        select(
            AttendanceConflictIncident,
            Employee.first_name,
            Employee.last_name,
            Employee.employee_id.label("employee_code"),
            Department.name.label("department_name"),
        )
        .join(
            Employee,
            (AttendanceConflictIncident.tenant_id == Employee.tenant_id)
            & (AttendanceConflictIncident.employee_id == Employee.id),
        )
        .outerjoin(
            Department,
            (Employee.tenant_id == Department.tenant_id)
            & (Employee.department_id == Department.id),
        )
        .where(*conditions)
    )

    if cursor:
        try:
            cursor_dt = datetime.fromisoformat(cursor)
            query = query.where(AttendanceConflictIncident.submitted_at < cursor_dt)
        except (ValueError, TypeError):
            pass

    query = query.order_by(
        AttendanceConflictIncident.submitted_at.desc(),
        AttendanceConflictIncident.id.desc(),
    ).limit(limit + 1)

    records = (await session.execute(query)).all()

    has_more = len(records) > limit
    page_records = records[:limit]

    items: list[SupervisorConflictQueueItem] = []
    for row in page_records:
        if hasattr(row, "AttendanceConflictIncident"):
            inc = row.AttendanceConflictIncident
            fn = row.first_name
            ln = row.last_name
            code = row.employee_code
            dept = row.department_name
        elif isinstance(row, tuple) or hasattr(row, "__getitem__"):
            inc = row[0]
            fn = row[1] if len(row) > 1 else ""
            ln = row[2] if len(row) > 2 else ""
            code = row[3] if len(row) > 3 else ""
            dept = row[4] if len(row) > 4 else None
        else:
            inc = row
            fn = ""
            ln = ""
            code = ""
            dept = None

        prim = inc.primary_rejected_event or {}
        p_type = prim.get("event_type", "CHECK_IN")
        p_time_raw = prim.get("device_reported_at")
        if isinstance(p_time_raw, str):
            try:
                p_time = datetime.fromisoformat(p_time_raw)
            except ValueError:
                p_time = inc.submitted_at
        elif isinstance(p_time_raw, datetime):
            p_time = p_time_raw
        else:
            p_time = inc.submitted_at

        items.append(
            SupervisorConflictQueueItem(
                id=inc.id,
                tenant_id=inc.tenant_id,
                employee_id=inc.employee_id,
                employee_name=f"{fn} {ln}".strip(),
                employee_code=code,
                department_name=dept,
                bundle_id=inc.bundle_id,
                session_id=inc.session_id,
                status=inc.status,
                total_events_count=inc.total_events_count,
                primary_event_type=p_type,
                primary_device_reported_at=p_time,
                rejection_summary=inc.rejection_summary,
                employee_notes=inc.employee_notes,
                submitted_at=inc.submitted_at,
                decision=inc.decision,
                decision_reason=inc.decision_reason,
                reviewer_user_id=inc.reviewer_user_id,
                decided_at=inc.decided_at,
                resolved_correction_event_ids=inc.resolved_correction_event_ids or [],
            )
        )

    next_cursor = items[-1].submitted_at.isoformat() if has_more and items else None

    return SupervisorConflictQueueListResponse(
        items=items,
        total=total_count,
        limit=limit,
        cursor=next_cursor,
        has_more=has_more,
    )


async def get_conflict_incident_detail(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    user_role: str,
    incident_id: uuid.UUID,
) -> AttendanceConflictIncidentDetailResponse:
    """Returns detailed forensic telemetry and metadata for a single conflict incident.

    Enforces:
    - Cross-tenant access is denied (HTTP 404 Not Found).
    - EMPLOYEE can only inspect their own incidents (HTTP 403 Forbidden).
    - MANAGER can inspect their direct reports and their own incidents (HTTP 403 Forbidden).
    - HR, ADMIN, and OWNER can inspect all tenant incidents.
    """
    stmt = select(AttendanceConflictIncident).where(
        AttendanceConflictIncident.tenant_id == tenant_id,
        AttendanceConflictIncident.id == incident_id,
    )
    incident = (await session.execute(stmt)).scalar_one_or_none()
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attendance conflict incident not found.",
        )

    # Fetch employee profile details
    emp_stmt = (
        select(
            Employee,
            Department.name.label("department_name"),
        )
        .outerjoin(
            Department,
            (Employee.tenant_id == Department.tenant_id)
            & (Employee.department_id == Department.id),
        )
        .where(
            Employee.tenant_id == tenant_id,
            Employee.id == incident.employee_id,
        )
    )
    emp_row = (await session.execute(emp_stmt)).first()
    if emp_row is not None:
        if hasattr(emp_row, "Employee"):
            target_emp = emp_row.Employee
            dept_name = emp_row.department_name
        elif isinstance(emp_row, tuple) or hasattr(emp_row, "__getitem__"):
            target_emp = emp_row[0]
            dept_name = emp_row[1] if len(emp_row) > 1 else None
        else:
            target_emp = emp_row
            dept_name = None
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee profile not found.",
        )

    # Check caller access permissions
    role = user_role.lower()
    if role == "employee":
        caller_emp_stmt = select(Employee.id).where(
            Employee.tenant_id == tenant_id,
            Employee.user_id == user_id,
        )
        caller_emp_id = (await session.execute(caller_emp_stmt)).scalar_one_or_none()
        if caller_emp_id is None or caller_emp_id != incident.employee_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Employees may only inspect their own attendance conflicts.",
            )
    elif role == "manager":
        caller_emp_stmt = select(Employee.id).where(
            Employee.tenant_id == tenant_id,
            Employee.user_id == user_id,
        )
        caller_emp_id = (await session.execute(caller_emp_stmt)).scalar_one_or_none()
        is_self = caller_emp_id is not None and caller_emp_id == incident.employee_id
        is_direct_report = (
            caller_emp_id is not None and target_emp.reporting_manager_id == caller_emp_id
        )
        if not (is_self or is_direct_report):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Managers may only inspect attendance conflicts of their direct reports.",
            )
    elif role not in ("owner", "admin", "hr"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to view conflict incident details.",
        )

    emp_detail = ConflictIncidentEmployeeDetail(
        id=target_emp.id,
        employee_code=target_emp.employee_id,
        first_name=target_emp.first_name,
        last_name=target_emp.last_name,
        work_email=target_emp.work_email,
        department_name=dept_name,
        reporting_manager_id=target_emp.reporting_manager_id,
    )

    return AttendanceConflictIncidentDetailResponse(
        id=incident.id,
        tenant_id=incident.tenant_id,
        bundle_id=incident.bundle_id,
        session_id=incident.session_id,
        status=incident.status,
        employee=emp_detail,
        primary_rejected_event=incident.primary_rejected_event,
        dependent_events=incident.dependent_events or [],
        total_events_count=incident.total_events_count,
        rejection_summary=incident.rejection_summary,
        employee_notes=incident.employee_notes,
        submitted_at=incident.submitted_at,
        assigned_reviewer_id=incident.assigned_reviewer_id,
        decision=incident.decision,
        decision_reason=incident.decision_reason,
        reviewer_user_id=incident.reviewer_user_id,
        decided_at=incident.decided_at,
        resolved_correction_event_ids=incident.resolved_correction_event_ids or [],
        metadata_json=incident.metadata_json or {},
        created_at=incident.created_at,
        updated_at=incident.updated_at,
    )


async def adjudicate_conflict_incident(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    incident_id: uuid.UUID,
    reviewer_user_id: uuid.UUID,
    reviewer_role: str,
    payload: AttendanceConflictDecisionRequest,
) -> AttendanceConflictDecisionResponse:
    """Adjudicates an attendance conflict incident with pessimistic row locking and atomic correction insertion.

    Atomicity Guarantees:
    1. Locks the incident row with `SELECT ... FOR UPDATE`.
    2. Verifies status is PENDING_REVIEW (409 Conflict if already decided).
    3. Verifies reviewer RBAC, reporting manager scoping, and anti-self-approval (403 Forbidden).
    4. If REJECT: records rejection decision and reason, zero ledger writes, zero recalculations.
    5. If APPROVE:
       - Validates optional override_location_id in tenant.
       - Re-validates the complete event bundle.
       - Atomically executes `apply_attendance_correction(CORRECTION_INSERT)` for each event.
       - Preserves original forensic timestamps and metadata.
       - Injects audit references (incident_id, bundle_id, original idempotency keys).
       - Recalculates all affected attendance day projections.
       - Records resolved correction event IDs and decision metadata.
       - Commits atomically or rolls back completely on any error.
    """
    try:
        # 1. Pessimistic row-level lock on the conflict incident
        stmt = (
            select(AttendanceConflictIncident)
            .where(
                AttendanceConflictIncident.tenant_id == tenant_id,
                AttendanceConflictIncident.id == incident_id,
            )
            .with_for_update()
        )
        incident = (await session.execute(stmt)).scalar_one_or_none()
        if incident is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Attendance conflict incident not found.",
            )

        # 2. Check if incident has already been decided
        if incident.status != "PENDING_REVIEW":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Conflict incident has already been resolved ({incident.status}).",
            )

        # 3. RBAC & Anti-Self-Approval Verification
        role = reviewer_role.lower()
        if role == "employee":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Employees are not authorized to adjudicate attendance conflicts.",
            )

        rev_emp_stmt = select(Employee).where(
            Employee.tenant_id == tenant_id,
            Employee.user_id == reviewer_user_id,
        )
        reviewer_emp = (await session.execute(rev_emp_stmt)).scalar_one_or_none()

        # Anti-self-approval rule: Reviewers cannot adjudicate their own attendance conflicts
        if incident.user_id == reviewer_user_id or (
            reviewer_emp is not None and reviewer_emp.id == incident.employee_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Reviewers cannot adjudicate their own attendance conflicts.",
            )

        target_emp_stmt = select(Employee).where(
            Employee.tenant_id == tenant_id,
            Employee.id == incident.employee_id,
        )
        target_emp = (await session.execute(target_emp_stmt)).scalar_one_or_none()
        if not target_emp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target employee not found.",
            )

        if role == "manager":
            if reviewer_emp is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Manager employee profile not found in tenant.",
                )
            if target_emp.reporting_manager_id != reviewer_emp.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Managers may only adjudicate attendance conflicts for their direct reports.",
                )
        elif role not in ("owner", "admin", "hr"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient privileges to adjudicate attendance conflicts.",
            )

        # 4. Handle Rejection
        if payload.action == "REJECT":
            incident.status = "REJECTED"
            incident.decision = "REJECTED"
            incident.decision_reason = payload.reason.strip()
            incident.reviewer_user_id = reviewer_user_id
            incident.decided_at = datetime.now(UTC)
            incident.resolved_correction_event_ids = []
            await session.flush()

            return AttendanceConflictDecisionResponse(
                id=incident.id,
                tenant_id=incident.tenant_id,
                employee_id=incident.employee_id,
                bundle_id=incident.bundle_id,
                status="REJECTED",
                decision="REJECTED",
                decision_reason=incident.decision_reason,
                reviewer_user_id=reviewer_user_id,
                decided_at=incident.decided_at,
                resolved_correction_event_ids=[],
                affected_attendance_dates=[],
                recalculated_days_count=0,
            )

        # 5. Handle Approval (Atomic Ledger Insertion via apply_attendance_correction)
        if payload.override_location_id:
            loc_exists = (
                await session.execute(
                    select(Location.id).where(
                        Location.tenant_id == tenant_id,
                        Location.id == payload.override_location_id,
                    )
                )
            ).scalar_one_or_none()
            if not loc_exists:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Override location not found in this organization.",
                )

        if not incident.primary_rejected_event:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Conflict incident has no primary rejected event data.",
            )

        all_events_to_insert = [
            incident.primary_rejected_event,
            *(incident.dependent_events or []),
        ]

        resolved_event_ids: list[str] = []
        affected_dates: set[date] = set()

        for idx, event_data in enumerate(all_events_to_insert):
            dev_rep_raw = event_data.get("device_reported_at")
            if not dev_rep_raw:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Event at index {idx} is missing device_reported_at.",
                )
            if isinstance(dev_rep_raw, datetime):
                eff_at = dev_rep_raw
            else:
                try:
                    eff_at = datetime.fromisoformat(str(dev_rep_raw))
                except Exception as e:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"Invalid timestamp in event at index {idx}: {e}",
                    )

            if eff_at.tzinfo is None:
                eff_at = eff_at.replace(tzinfo=UTC)

            eff_loc_id = payload.override_location_id
            if eff_loc_id is None and event_data.get("location_id"):
                try:
                    eff_loc_id = uuid.UUID(str(event_data["location_id"]))
                except (ValueError, TypeError):
                    eff_loc_id = None

            raw_idem = event_data.get("idempotency_key") or str(uuid.uuid4())
            corr_idem_hash = hashlib.sha256(
                f"{incident.bundle_id}_{raw_idem}".encode()
            ).hexdigest()[:40]
            corr_idem_key = f"cf_{corr_idem_hash}"

            corr_req = AttendanceCorrectionCreateRequest(
                employee_id=incident.employee_id,
                correction_type=AttendanceCorrectionType.CORRECTION_INSERT,
                event_type=event_data["event_type"],
                effective_at=eff_at,
                correction_reason=f"Offline Conflict Approval: {payload.reason.strip()}",
                idempotency_key=corr_idem_key,
                location_id=eff_loc_id,
                metadata={
                    "conflict_incident_id": str(incident.id),
                    "bundle_id": incident.bundle_id,
                    "original_offline_idempotency_key": raw_idem,
                    "original_device_id_hash": event_data.get("device_id_hash"),
                    "source": "OFFLINE_CONFLICT_RESOLUTION",
                },
            )

            corr_res = await apply_attendance_correction(
                session=session,
                tenant_id=tenant_id,
                actor_user_id=reviewer_user_id,
                actor_role=reviewer_role,
                payload=corr_req,
            )

            resolved_event_ids.append(str(corr_res.correction_event.id))
            affected_dates.update(corr_res.affected_attendance_dates)

        # 6. Finalize Incident State
        incident.status = "APPROVED"
        incident.decision = "APPROVED"
        incident.decision_reason = payload.reason.strip()
        incident.reviewer_user_id = reviewer_user_id
        incident.decided_at = datetime.now(UTC)
        incident.resolved_correction_event_ids = resolved_event_ids
        if payload.override_location_id:
            meta = dict(incident.metadata_json or {})
            meta["override_location_id"] = str(payload.override_location_id)
            incident.metadata_json = meta
        await session.flush()

        return AttendanceConflictDecisionResponse(
            id=incident.id,
            tenant_id=incident.tenant_id,
            employee_id=incident.employee_id,
            bundle_id=incident.bundle_id,
            status="APPROVED",
            decision="APPROVED",
            decision_reason=incident.decision_reason,
            reviewer_user_id=reviewer_user_id,
            decided_at=incident.decided_at,
            resolved_correction_event_ids=resolved_event_ids,
            affected_attendance_dates=sorted(affected_dates),
            recalculated_days_count=len(affected_dates),
        )

    except HTTPException:
        await session.rollback()
        raise
    except Exception:
        await session.rollback()
        raise
