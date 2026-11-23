"""Downward Delta Sync Service for Phase 11.3 & Acceptance Hardening.

Orchestrates server-to-mobile synchronization of reference data:
- Composite cursor generation & HMAC-SHA256 validation (v2 format with backward-compatible v1 support)
- Key rotation support with fallback signing keys
- Tenant, user, and employee context binding
- Cursor TTL expiration enforcement
- Initial full synchronization
- Incremental delta synchronization
- Stable keyset pagination across heterogeneous collections with frozen session snapshots
- Preservation of records with identical timestamps across page boundaries
- Isolation from concurrent updates occurring during multi-page pagination sessions
- Tombstone delivery across page boundaries
- Tenant and role-based data isolation (authorized self-scope & manager direct reports)
- Soft deletion and tombstone tracking
"""

import base64
import hashlib
import hmac
import json
import uuid
from datetime import UTC, date, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from services.api.attendance.downward_sync_schemas import (
    SyncAttendancePolicyPayload,
    SyncDeltaResponse,
    SyncDirectReportPayload,
    SyncEmployeePayload,
    SyncHolidayPayload,
    SyncLeaveBalancePayload,
    SyncLeaveRequestPayload,
    SyncLeaveTypePayload,
    SyncReportingHierarchyPayload,
    SyncShiftPayload,
    SyncTombstonePayload,
    SyncType,
    SyncWorkplacePayload,
)
from services.api.attendance.models import (
    ShiftAssignment,
    ShiftTemplate,
    TenantAttendancePolicy,
)
from services.api.config import settings
from services.api.employees.models import Employee
from services.api.leave.models import (
    Holiday,
    HolidayCalendar,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
)
from services.api.locations.models import EmployeeLocation, Location
from services.api.organization.models import Department

COLLECTION_ORDER = [
    "shifts",
    "workplaces",
    "holidays",
    "leave_types",
    "leave_balances",
    "leave_requests",
    "direct_reports",
]


class ParsedSyncCursor(datetime):
    """Parsed sync cursor token representation extending datetime for 100% backward compatibility."""

    tenant_id: uuid.UUID
    user_id: uuid.UUID
    employee_id: uuid.UUID | None
    base_ts: datetime | None
    session_ts: datetime
    entity_type: str
    last_id: str | None
    expires_at: int | None
    is_done: bool

    def __new__(
        cls,
        dt: datetime,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        employee_id: uuid.UUID | None = None,
        base_ts: datetime | None = None,
        session_ts: datetime | None = None,
        entity_type: str = "DONE",
        last_id: str | None = None,
        expires_at: int | None = None,
    ) -> "ParsedSyncCursor":
        tz = dt.tzinfo or UTC
        obj = datetime.__new__(
            cls,
            dt.year,
            dt.month,
            dt.day,
            dt.hour,
            dt.minute,
            dt.second,
            dt.microsecond,
            tz,
        )
        obj.tenant_id = tenant_id
        obj.user_id = user_id
        obj.employee_id = employee_id
        obj.base_ts = base_ts
        obj.session_ts = session_ts or dt
        obj.entity_type = entity_type
        obj.last_id = last_id
        obj.expires_at = expires_at
        obj.is_done = entity_type == "DONE"
        return obj


def generate_sync_cursor(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    timestamp: datetime | None = None,
    employee_id: uuid.UUID | None = None,
    base_ts: datetime | None = None,
    session_ts: datetime | None = None,
    entity_type: str = "DONE",
    last_id: str | None = None,
    expires_in_seconds: int = 30 * 86400,
    secret_key: str | None = None,
) -> str:
    """Generates a tamper-proof HMAC-signed base64 composite cursor token."""
    secret = secret_key or settings.SECRET_KEY
    s_ts = session_ts or timestamp or datetime.now(UTC)
    b_ts = base_ts or timestamp
    s_ts_str = s_ts.isoformat()
    b_ts_str = b_ts.isoformat() if b_ts else ""
    eid_str = str(employee_id) if employee_id else ""
    last_id_str = str(last_id) if last_id else ""
    exp = int(datetime.now(UTC).timestamp()) + expires_in_seconds

    raw_payload = f"2:{tenant_id}:{user_id}:{eid_str}:{b_ts_str}:{s_ts_str}:{entity_type}:{last_id_str}:{exp}"
    sig = hmac.new(secret.encode(), raw_payload.encode(), hashlib.sha256).hexdigest()

    data = {
        "v": 2,
        "tid": str(tenant_id),
        "uid": str(user_id),
        "eid": eid_str,
        "bts": b_ts_str,
        "sts": s_ts_str,
        "ent": entity_type,
        "lid": last_id_str,
        "exp": exp,
        "sig": sig,
    }
    encoded = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
    return encoded


def decode_and_verify_sync_cursor(
    cursor_str: str,
    expected_tenant_id: uuid.UUID,
    expected_user_id: uuid.UUID,
    expected_employee_id: uuid.UUID | None = None,
    secret_key: str | None = None,
    fallback_keys: list[str] | None = None,
) -> ParsedSyncCursor:
    """Decodes and cryptographically verifies an opaque sync cursor token.

    Validates:
    - HMAC signature using active secret key and optional fallback keys (key rotation).
    - Tenant, user, and employee context binding.
    - Cursor expiration (TTL).
    - Format and claims completeness.
    - Full backward compatibility for v1 cursor format.

    Raises HTTPException 400 if tampered, malformed, expired, or context mismatch.
    """
    secret = secret_key or settings.SECRET_KEY
    keys = [secret]
    if fallback_keys:
        keys.extend(fallback_keys)

    try:
        raw_json = base64.urlsafe_b64decode(cursor_str.encode()).decode()
        data = json.loads(raw_json)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Malformed sync cursor: {e}",
        ) from e

    if not isinstance(data, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed sync cursor data structure",
        )

    v = data.get("v")
    tid = data.get("tid")
    uid = data.get("uid")
    sig = data.get("sig")

    if not tid or not uid or not sig:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incomplete sync cursor claims",
        )

    if v == 1:
        # Legacy v1 format: raw_payload = f"1:{tid}:{uid}:{ts_str}"
        ts_str = data.get("ts")
        if not ts_str:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Incomplete v1 sync cursor claims",
            )
        raw_payload = f"1:{tid}:{uid}:{ts_str}"
        sig_valid = any(
            hmac.compare_digest(
                sig,
                hmac.new(k.encode(), raw_payload.encode(), hashlib.sha256).hexdigest(),
            )
            for k in keys
        )
        if not sig_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or tampered sync cursor signature",
            )
        if tid != str(expected_tenant_id) or uid != str(expected_user_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sync cursor tenant or user mismatch",
            )
        try:
            ts = datetime.fromisoformat(ts_str)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid sync cursor timestamp: {e}",
            ) from e
        return ParsedSyncCursor(
            ts,
            tenant_id=expected_tenant_id,
            user_id=expected_user_id,
            employee_id=expected_employee_id,
            base_ts=ts,
            session_ts=ts,
            entity_type="DONE",
            last_id=None,
        )

    elif v == 2:
        eid = data.get("eid", "")
        bts_str = data.get("bts", "")
        sts_str = data.get("sts", "")
        ent = data.get("ent", "DONE")
        lid = data.get("lid") or None
        exp = data.get("exp", 0)

        raw_payload = f"2:{tid}:{uid}:{eid}:{bts_str}:{sts_str}:{ent}:{lid or ''}:{exp}"
        sig_valid = any(
            hmac.compare_digest(
                sig,
                hmac.new(k.encode(), raw_payload.encode(), hashlib.sha256).hexdigest(),
            )
            for k in keys
        )
        if not sig_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or tampered sync cursor signature",
            )

        if tid != str(expected_tenant_id) or uid != str(expected_user_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sync cursor tenant or user mismatch",
            )

        if expected_employee_id and eid and eid != str(expected_employee_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sync cursor employee mismatch",
            )

        now_epoch = int(datetime.now(UTC).timestamp())
        if exp and exp < now_epoch:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sync cursor has expired, full sync required",
            )

        try:
            sts = datetime.fromisoformat(sts_str)
            bts = datetime.fromisoformat(bts_str) if bts_str else None
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid sync cursor timestamp: {e}",
            ) from e

        emp_uuid = uuid.UUID(eid) if eid else expected_employee_id
        return ParsedSyncCursor(
            sts,
            tenant_id=expected_tenant_id,
            user_id=expected_user_id,
            employee_id=emp_uuid,
            base_ts=bts,
            session_ts=sts,
            entity_type=ent,
            last_id=lid,
            expires_at=exp,
        )

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported sync cursor version",
        )


async def process_downward_delta_sync(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    cursor: str | None = None,
    limit: int = 50,
) -> SyncDeltaResponse:
    """Retrieves reference data and shift schedules authorized for the authenticated employee."""
    # 1. Resolve employee profile
    emp_stmt = select(Employee).where(
        Employee.tenant_id == tenant_id,
        Employee.user_id == user_id,
    )
    emp_res = await session.execute(emp_stmt)
    employee = emp_res.scalar_one_or_none()

    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee profile not found for authenticated user in this tenant.",
        )

    # 2. Parse cursor and determine sync mode
    server_time = datetime.now(UTC)
    today = date.today()
    parsed_cursor: ParsedSyncCursor | None = None

    if cursor and cursor.strip():
        parsed_cursor = decode_and_verify_sync_cursor(
            cursor_str=cursor,
            expected_tenant_id=tenant_id,
            expected_user_id=user_id,
            expected_employee_id=employee.id,
        )

    # If employee is deactivated/terminated, return deactivated profile and empty deltas
    if employee.status != "active":
        deactivated_emp_payload = SyncEmployeePayload.model_validate(employee)
        next_cursor = generate_sync_cursor(
            tenant_id=tenant_id,
            user_id=user_id,
            employee_id=employee.id,
            timestamp=server_time,
            base_ts=server_time,
            session_ts=server_time,
            entity_type="DONE",
        )
        return SyncDeltaResponse(
            sync_type=SyncType.FULL if parsed_cursor is None else SyncType.DELTA,
            server_time=server_time,
            next_cursor=next_cursor,
            has_more=False,
            employee=deactivated_emp_payload,
            shifts=[],
            workplaces=[],
            holidays=[],
            leave_types=[],
            leave_balances=[],
            leave_requests=[],
            attendance_policy=None,
            reporting_hierarchy=None,
            tombstones=[],
        )

    if parsed_cursor is None:
        sync_type = SyncType.FULL
        base_ts: datetime | None = None
        session_ts: datetime | None = None
        start_entity: str | None = None
        start_last_id: str | None = None
    elif parsed_cursor.is_done:
        sync_type = SyncType.DELTA
        base_ts = parsed_cursor.base_ts
        session_ts = None
        start_entity = None
        start_last_id = None
    else:
        sync_type = SyncType.DELTA if parsed_cursor.base_ts is not None else SyncType.FULL
        base_ts = parsed_cursor.base_ts
        session_ts = parsed_cursor.session_ts  # Preserve frozen session snapshot across pages!
        start_entity = parsed_cursor.entity_type
        start_last_id = parsed_cursor.last_id

    # 3. Employee Profile Header Payload (Only on initial page of session)
    emp_payload: SyncEmployeePayload | None = None
    if start_entity is None:
        if base_ts is None or (employee.updated_at > base_ts and (session_ts is None or employee.updated_at <= session_ts)):
            emp_payload = SyncEmployeePayload.model_validate(employee)

    candidate_timestamps = [server_time, employee.updated_at]

    # 4. Shifts and Schedule Assignments
    shifts_raw: list[dict[str, Any]] = []
    shift_stmt = (
        select(ShiftAssignment, ShiftTemplate)
        .join(
            ShiftTemplate,
            (ShiftTemplate.id == ShiftAssignment.shift_template_id)
            & (ShiftTemplate.tenant_id == tenant_id),
        )
        .options(selectinload(ShiftTemplate.versions))
        .where(
            ShiftAssignment.tenant_id == tenant_id,
            ShiftAssignment.employee_id == employee.id,
        )
        .order_by(ShiftAssignment.updated_at.asc(), ShiftAssignment.id.asc())
    )
    if base_ts is not None:
        shift_stmt = shift_stmt.where(
            (ShiftAssignment.updated_at > base_ts) | (ShiftTemplate.updated_at > base_ts)
        )
    if session_ts is not None:
        shift_stmt = shift_stmt.where(ShiftAssignment.updated_at <= session_ts)

    shift_res = await session.execute(shift_stmt)
    for assignment, template in shift_res.all():
        if session_ts is not None and (assignment.updated_at > session_ts or template.updated_at > session_ts):
            continue
        candidate_timestamps.extend([assignment.updated_at, template.updated_at])
        applicable_versions = [
            v for v in template.versions if v.version_effective_from <= today
        ]
        if applicable_versions:
            applicable_versions.sort(
                key=lambda v: (v.version_effective_from, v.version_number), reverse=True
            )
            version = applicable_versions[0]
        elif template.versions:
            template.versions.sort(key=lambda v: v.version_number, reverse=True)
            version = template.versions[0]
        else:
            continue

        payload = SyncShiftPayload(
            id=assignment.id,
            shift_template_id=template.id,
            name=template.name,
            code=template.code,
            start_time=version.start_time.isoformat(),
            end_time=version.end_time.isoformat(),
            grace_period_minutes=version.grace_period_minutes if version.grace_period_minutes is not None else 15,
            early_exit_grace_minutes=version.early_exit_grace_minutes if version.early_exit_grace_minutes is not None else 15,
            half_day_threshold_minutes=version.half_day_threshold_minutes if version.half_day_threshold_minutes is not None else 240,
            full_day_threshold_minutes=version.full_day_threshold_minutes if version.full_day_threshold_minutes is not None else 480,
            break_duration_minutes=version.break_duration_minutes if version.break_duration_minutes is not None else 60,
            is_overnight=version.is_overnight if version.is_overnight is not None else False,
            is_flexible=version.is_flexible if version.is_flexible is not None else False,
            weekly_off_days=version.weekly_off_days if version.weekly_off_days is not None else [6, 0],
            effective_from=assignment.effective_from,
            effective_to=assignment.effective_to,
            updated_at=assignment.updated_at,
        )
        shifts_raw.append({"id": str(assignment.id), "payload": payload})

    # 5. Workplaces & Geofences (including de-assignments / tombstones)
    workplaces_raw: list[dict[str, Any]] = []
    wp_stmt = (
        select(EmployeeLocation, Location)
        .join(
            Location,
            (Location.id == EmployeeLocation.location_id)
            & (Location.tenant_id == tenant_id),
        )
        .where(
            EmployeeLocation.tenant_id == tenant_id,
            EmployeeLocation.employee_id == employee.id,
        )
        .order_by(Location.updated_at.asc(), Location.id.asc())
    )
    if base_ts is not None:
        wp_stmt = wp_stmt.where(
            (EmployeeLocation.created_at > base_ts) | (Location.updated_at > base_ts)
        )
    if session_ts is not None:
        wp_stmt = wp_stmt.where(Location.updated_at <= session_ts)

    wp_res = await session.execute(wp_stmt)
    for emp_loc, loc in wp_res.all():
        if session_ts is not None and loc.updated_at > session_ts:
            continue
        candidate_timestamps.append(loc.updated_at)
        is_assigned = emp_loc.effective_to is None or emp_loc.effective_to >= today
        if is_assigned and loc.is_active:
            wp_payload = SyncWorkplacePayload(
                id=loc.id,
                name=loc.name,
                code=loc.code,
                address_line1=loc.address_line1,
                city=loc.city,
                latitude=float(loc.latitude),
                longitude=float(loc.longitude),
                radius_meters=loc.radius_meters,
                timezone=loc.timezone,
                wifi_bssids=loc.wifi_bssids or [],
                is_active=loc.is_active,
                is_assigned=True,
                is_primary=emp_loc.is_primary,
                updated_at=loc.updated_at,
            )
            workplaces_raw.append({"id": str(loc.id), "payload": wp_payload, "type": "workplace"})
        else:
            tomb_payload = SyncTombstonePayload(
                entity_type="workplace",
                entity_id=loc.id,
                deleted_at=loc.updated_at,
            )
            workplaces_raw.append({"id": str(loc.id), "payload": tomb_payload, "type": "tombstone"})

    # 6. Holidays & Weekly Offs
    holidays_raw: list[dict[str, Any]] = []
    cal_stmt = select(HolidayCalendar).where(
        HolidayCalendar.tenant_id == tenant_id,
        HolidayCalendar.year.in_([today.year, today.year + 1]),
    )
    cal_res = await session.execute(cal_stmt)
    calendars = cal_res.scalars().all()
    calendar_ids = [c.id for c in calendars]

    if calendar_ids:
        hol_stmt = (
            select(Holiday)
            .where(
                Holiday.tenant_id == tenant_id,
                Holiday.calendar_id.in_(calendar_ids),
            )
            .order_by(Holiday.holiday_date.asc(), Holiday.id.asc())
        )
        if base_ts is not None:
            hol_stmt = hol_stmt.where(Holiday.updated_at > base_ts)
        if session_ts is not None:
            hol_stmt = hol_stmt.where(Holiday.updated_at <= session_ts)

        hol_res = await session.execute(hol_stmt)
        for h in hol_res.scalars().all():
            if session_ts is not None and h.updated_at > session_ts:
                continue
            candidate_timestamps.append(h.updated_at)
            hol_payload = SyncHolidayPayload(
                id=h.id,
                calendar_id=h.calendar_id,
                holiday_date=h.holiday_date,
                name=h.name,
                holiday_type=h.holiday_type,
                is_optional=h.is_optional,
                updated_at=h.updated_at,
            )
            holidays_raw.append({"id": str(h.id), "payload": hol_payload})

    # 7. Leave Types
    leave_types_raw: list[dict[str, Any]] = []
    lt_stmt = select(LeaveType).where(
        LeaveType.tenant_id == tenant_id,
        LeaveType.is_active.is_(True),
    ).order_by(LeaveType.name.asc(), LeaveType.id.asc())
    if base_ts is not None:
        lt_stmt = lt_stmt.where(LeaveType.updated_at > base_ts)
    if session_ts is not None:
        lt_stmt = lt_stmt.where(LeaveType.updated_at <= session_ts)

    lt_res = await session.execute(lt_stmt)
    for lt in lt_res.scalars().all():
        if session_ts is not None and lt.updated_at > session_ts:
            continue
        candidate_timestamps.append(lt.updated_at)
        lt_payload = SyncLeaveTypePayload(
            id=lt.id,
            code=lt.code,
            name=lt.name,
            is_paid=lt.is_paid,
            allow_half_day=lt.allow_half_day,
            updated_at=lt.updated_at,
        )
        leave_types_raw.append({"id": str(lt.id), "payload": lt_payload})

    # 8. Leave Balances (Current Year, Strictly Scoped to Employee)
    leave_balances_raw: list[dict[str, Any]] = []
    lb_stmt = select(LeaveBalance).where(
        LeaveBalance.tenant_id == tenant_id,
        LeaveBalance.employee_id == employee.id,
        LeaveBalance.year == today.year,
    ).order_by(LeaveBalance.id.asc())
    if base_ts is not None:
        lb_stmt = lb_stmt.where(LeaveBalance.updated_at > base_ts)
    if session_ts is not None:
        lb_stmt = lb_stmt.where(LeaveBalance.updated_at <= session_ts)

    lb_res = await session.execute(lb_stmt)
    for lb in lb_res.scalars().all():
        if session_ts is not None and lb.updated_at > session_ts:
            continue
        candidate_timestamps.append(lb.updated_at)
        lb_payload = SyncLeaveBalancePayload(
            id=lb.id,
            leave_type_id=lb.leave_type_id,
            year=lb.year,
            annual_allocation=float(lb.annual_allocation),
            used=float(lb.used),
            available_balance=float(lb.available_balance),
            updated_at=lb.updated_at,
        )
        leave_balances_raw.append({"id": str(lb.id), "payload": lb_payload})

    # 9. Leave Requests (Strictly Scoped to Employee)
    leave_requests_raw: list[dict[str, Any]] = []
    lr_stmt = select(LeaveRequest).where(
        LeaveRequest.tenant_id == tenant_id,
        LeaveRequest.employee_id == employee.id,
    ).order_by(LeaveRequest.updated_at.asc(), LeaveRequest.id.asc())
    if base_ts is not None:
        lr_stmt = lr_stmt.where(LeaveRequest.updated_at > base_ts)
    if session_ts is not None:
        lr_stmt = lr_stmt.where(LeaveRequest.updated_at <= session_ts)

    lr_res = await session.execute(lr_stmt)
    for lr in lr_res.scalars().all():
        if session_ts is not None and lr.updated_at > session_ts:
            continue
        candidate_timestamps.append(lr.updated_at)
        lr_payload = SyncLeaveRequestPayload(
            id=lr.id,
            leave_type_id=lr.leave_type_id,
            start_date=lr.start_date,
            end_date=lr.end_date,
            is_half_day=lr.is_half_day,
            total_days=float(lr.total_days),
            reason=lr.reason,
            status=lr.status,
            decided_at=lr.decided_at,
            updated_at=lr.updated_at,
        )
        leave_requests_raw.append({"id": str(lr.id), "payload": lr_payload})

    # 10. Organization Attendance Policy (Only on initial page of session)
    policy_payload: SyncAttendancePolicyPayload | None = None
    pol_stmt = (
        select(TenantAttendancePolicy)
        .where(
            TenantAttendancePolicy.tenant_id == tenant_id,
            TenantAttendancePolicy.is_active.is_(True),
        )
        .order_by(TenantAttendancePolicy.version.desc())
    )
    pol_res = await session.execute(pol_stmt)
    active_policy = pol_res.scalars().first()

    if active_policy:
        candidate_timestamps.append(active_policy.updated_at)
        if start_entity is None:
            if base_ts is None or (active_policy.updated_at > base_ts and (session_ts is None or active_policy.updated_at <= session_ts)):
                policy_payload = SyncAttendancePolicyPayload(
                    id=active_policy.id,
                    version=active_policy.version,
                    is_active=active_policy.is_active,
                    default_mode=active_policy.default_mode,
                    allowed_methods=active_policy.allowed_methods,
                    required_methods=active_policy.required_methods,
                    combination_rule=active_policy.combination_rule,
                    gps_config=active_policy.gps_config or {},
                    wifi_config=active_policy.wifi_config or {},
                    updated_at=active_policy.updated_at,
                )

    # 11. Manager / Reporting Hierarchy
    manager_name: str | None = None
    manager_email: str | None = None

    if employee.reporting_manager_id and start_entity is None:
        mgr_stmt = select(Employee).where(
            Employee.tenant_id == tenant_id,
            Employee.id == employee.reporting_manager_id,
        )
        mgr_res = await session.execute(mgr_stmt)
        manager = mgr_res.scalar_one_or_none()
        if manager:
            manager_name = f"{manager.first_name} {manager.last_name}"
            manager_email = manager.work_email

    # Direct reports if employee is a supervisor/manager
    direct_reports_raw: list[dict[str, Any]] = []
    dr_stmt = (
        select(Employee, Department.name.label("dept_name"))
        .outerjoin(Department, Department.id == Employee.department_id)
        .where(
            Employee.tenant_id == tenant_id,
            Employee.reporting_manager_id == employee.id,
            Employee.status == "active",
        )
        .order_by(Employee.last_name.asc(), Employee.first_name.asc(), Employee.id.asc())
    )
    if base_ts is not None:
        dr_stmt = dr_stmt.where(Employee.updated_at > base_ts)
    if session_ts is not None:
        dr_stmt = dr_stmt.where(Employee.updated_at <= session_ts)

    dr_res = await session.execute(dr_stmt)
    for dr_emp, dept_name in dr_res.all():
        if session_ts is not None and dr_emp.updated_at > session_ts:
            continue
        candidate_timestamps.append(dr_emp.updated_at)
        dr_payload = SyncDirectReportPayload(
            id=dr_emp.id,
            employee_id=dr_emp.employee_id,
            first_name=dr_emp.first_name,
            last_name=dr_emp.last_name,
            work_email=dr_emp.work_email,
            department_name=dept_name,
            status=dr_emp.status,
            updated_at=dr_emp.updated_at,
        )
        direct_reports_raw.append({"id": str(dr_emp.id), "payload": dr_payload})

    if session_ts is None:
        session_ts = max(candidate_timestamps)

    # 12. Keyset Pagination Across Ordered Collections
    raw_collections = {
        "shifts": shifts_raw,
        "workplaces": workplaces_raw,
        "holidays": holidays_raw,
        "leave_types": leave_types_raw,
        "leave_balances": leave_balances_raw,
        "leave_requests": leave_requests_raw,
        "direct_reports": direct_reports_raw,
    }

    shifts: list[SyncShiftPayload] = []
    workplaces: list[SyncWorkplacePayload] = []
    holidays: list[SyncHolidayPayload] = []
    leave_types: list[SyncLeaveTypePayload] = []
    leave_balances: list[SyncLeaveBalancePayload] = []
    leave_requests: list[SyncLeaveRequestPayload] = []
    direct_reports: list[SyncDirectReportPayload] = []
    tombstones: list[SyncTombstonePayload] = []

    accumulated = 0
    has_more = False
    last_entity: str | None = None
    last_id: str | None = None
    stop = False

    for ent in COLLECTION_ORDER:
        if stop:
            break
        if start_entity is not None and COLLECTION_ORDER.index(ent) < COLLECTION_ORDER.index(start_entity):
            continue

        items = raw_collections.get(ent, [])
        if start_entity == ent and start_last_id:
            idx = -1
            for i, it in enumerate(items):
                if str(it["id"]) == str(start_last_id):
                    idx = i
                    break
            if idx != -1:
                items = items[idx + 1:]

        for it in items:
            if accumulated >= limit:
                has_more = True
                stop = True
                break

            if ent == "shifts":
                shifts.append(it["payload"])
            elif ent == "workplaces":
                if it.get("type") == "workplace":
                    workplaces.append(it["payload"])
                else:
                    tombstones.append(it["payload"])
            elif ent == "holidays":
                holidays.append(it["payload"])
            elif ent == "leave_types":
                leave_types.append(it["payload"])
            elif ent == "leave_balances":
                leave_balances.append(it["payload"])
            elif ent == "leave_requests":
                leave_requests.append(it["payload"])
            elif ent == "direct_reports":
                direct_reports.append(it["payload"])

            accumulated += 1
            last_entity = ent
            last_id = str(it["id"])

    # 13. Reporting Hierarchy Construction
    reporting_hierarchy: SyncReportingHierarchyPayload | None = None
    if start_entity is None or direct_reports or manager_name:
        reporting_hierarchy = SyncReportingHierarchyPayload(
            manager_id=employee.reporting_manager_id,
            manager_name=manager_name,
            manager_email=manager_email,
            direct_reports=direct_reports,
        )

    # 14. Cursor Advancement
    if has_more:
        next_cursor = generate_sync_cursor(
            tenant_id=tenant_id,
            user_id=user_id,
            employee_id=employee.id,
            base_ts=base_ts,
            session_ts=session_ts,
            entity_type=last_entity or "DONE",
            last_id=last_id,
            expires_in_seconds=86400,  # 24h for in-flight pagination cursor
        )
    else:
        next_cursor = generate_sync_cursor(
            tenant_id=tenant_id,
            user_id=user_id,
            employee_id=employee.id,
            base_ts=session_ts,  # Advanced to session snapshot timestamp!
            session_ts=session_ts,
            entity_type="DONE",
            last_id=None,
            expires_in_seconds=30 * 86400,  # 30 days for completed cursor
        )

    return SyncDeltaResponse(
        sync_type=sync_type,
        server_time=server_time,
        next_cursor=next_cursor,
        has_more=has_more,
        employee=emp_payload,
        shifts=shifts,
        workplaces=workplaces,
        holidays=holidays,
        leave_types=leave_types,
        leave_balances=leave_balances,
        leave_requests=leave_requests,
        attendance_policy=policy_payload,
        reporting_hierarchy=reporting_hierarchy,
        tombstones=tombstones,
    )
