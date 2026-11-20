"""Business logic and workflow service for HR Fraud Review Queue and Adjudication."""

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.attendance.models import AttendanceEvent, ShiftAssignment, ShiftTemplate
from services.api.attendance.service import (
    determine_shift_date_for_punch,
    recalculate_attendance_day,
)
from services.api.auth.models import User
from services.api.auth.permissions import Permission, UserRole, has_permission
from services.api.devices.models import Device
from services.api.employees.models import Employee
from services.api.fraud.models import FraudFlag, FraudReview
from services.api.fraud.schemas import (
    FraudEventReviewDetailResponse,
    FraudFlagResponse,
    FraudReviewDecisionRequest,
    FraudReviewDecisionResponse,
    FraudReviewHistoryItem,
)
from services.api.locations.models import Location
from services.api.organization.models import Department
from services.api.tenants.models import Tenant


async def get_fraud_event_review_detail(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    event_id: uuid.UUID,
    reviewer_user: User,
    reviewer_role: UserRole | str,
) -> FraudEventReviewDetailResponse:
    """Retrieves full forensic details, telemetry, rule signals, and review history
    for a suspicious attendance event. Enforces manager reporting-line visibility.
    """
    # 1. Fetch attendance event with tenant isolation
    stmt = select(AttendanceEvent).where(
        AttendanceEvent.tenant_id == tenant_id,
        AttendanceEvent.id == event_id,
    )
    event = (await session.execute(stmt)).scalar_one_or_none()
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Attendance event '{event_id}' not found.",
        )

    # 2. Fetch employee profile
    emp_stmt = select(Employee).where(
        Employee.tenant_id == tenant_id,
        Employee.id == event.employee_id,
    )
    employee = (await session.execute(emp_stmt)).scalar_one_or_none()

    # 3. Enforce Manager departmental & direct-report visibility restriction
    role_enum = UserRole(reviewer_role) if isinstance(reviewer_role, str) else reviewer_role
    if role_enum == UserRole.MANAGER:
        manager_emp_stmt = select(Employee).where(
            Employee.tenant_id == tenant_id,
            Employee.user_id == reviewer_user.id,
        )
        manager_emp = (await session.execute(manager_emp_stmt)).scalar_one_or_none()
        if manager_emp is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Manager has no linked employee profile to determine organizational visibility.",
            )

        is_direct_report = employee is not None and employee.reporting_manager_id == manager_emp.id
        is_same_department = (
            employee is not None
            and manager_emp.department_id is not None
            and employee.department_id == manager_emp.department_id
        )

        if not (is_direct_report or is_same_department):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You do not have permission to view fraud review details for this employee.",
            )

    # 4. Resolve Department Name
    dept_name: str | None = None
    if employee and employee.department_id:
        dept_stmt = select(Department.name).where(
            Department.tenant_id == tenant_id,
            Department.id == employee.department_id,
        )
        dept_res = (await session.execute(dept_stmt)).scalar_one_or_none()
        dept_name = str(dept_res) if dept_res is not None else None

    # 5. Resolve Location telemetry & metadata
    location_payload: dict[str, object] | None = None
    spatial_ev = (event.metadata_json or {}).get("spatial_evidence", {})
    loc_name: str | None = None
    if event.location_id is not None:
        loc_stmt = select(Location.name).where(
            Location.tenant_id == tenant_id,
            Location.id == event.location_id,
        )
        loc_res = (await session.execute(loc_stmt)).scalar_one_or_none()
        loc_name = str(loc_res) if loc_res is not None else None

    if event.location_id is not None or event.latitude is not None or event.longitude is not None:
        location_payload = {
            "location_id": str(event.location_id) if event.location_id else None,
            "location_name": loc_name,
            "latitude": float(event.latitude) if event.latitude is not None else None,
            "longitude": float(event.longitude) if event.longitude is not None else None,
            "accuracy_meters": float(event.accuracy_meters) if event.accuracy_meters is not None else None,
            "distance_meters": spatial_ev.get("distance_to_location_meters") or spatial_ev.get("distance_meters"),
            "geofence_matched": spatial_ev.get("geofence_matched", False),
            "is_mock_reported": bool(event.is_mock_location),
        }

    # 6. Resolve Device telemetry
    device_payload: dict[str, object] | None = None
    if event.device_id is not None:
        dev = None
        try:
            device_uuid = uuid.UUID(str(event.device_id))
            dev_stmt = select(Device).where(
                Device.tenant_id == tenant_id,
                Device.id == device_uuid,
            )
            dev = (await session.execute(dev_stmt)).scalar_one_or_none()
        except (ValueError, TypeError):
            dev = None

        if dev is not None:
            device_payload = {
                "device_id": str(dev.id),
                "platform": dev.platform,
                "device_model": dev.device_model,
                "os_version": dev.os_version,
                "app_version": dev.app_version,
                "status": dev.status,
                "registered_at": dev.registered_at.isoformat() if dev.registered_at else None,
            }
        else:
            device_payload = {
                "device_id": str(event.device_id),
                "status": "UNREGISTERED",
            }

    # 7. Resolve Shift details
    shift_payload: dict[str, object] | None = None
    asgn_stmt = (
        select(ShiftAssignment, ShiftTemplate.name)
        .join(
            ShiftTemplate,
            (ShiftTemplate.tenant_id == ShiftAssignment.tenant_id)
            & (ShiftTemplate.id == ShiftAssignment.shift_template_id),
        )
        .where(
            ShiftAssignment.tenant_id == tenant_id,
            ShiftAssignment.employee_id == event.employee_id,
            ShiftAssignment.effective_from <= event.effective_at.date(),
        )
        .order_by(ShiftAssignment.effective_from.desc())
        .limit(1)
    )
    asgn_row = (await session.execute(asgn_stmt)).first()
    if asgn_row is not None:
        try:
            asgn, tmpl_name = asgn_row[0], asgn_row[1]
            shift_payload = {
                "shift_template_id": str(asgn.shift_template_id),
                "shift_template_name": tmpl_name,
                "effective_from": asgn.effective_from.isoformat(),
                "effective_to": asgn.effective_to.isoformat() if asgn.effective_to else None,
            }
        except (IndexError, TypeError, ValueError):
            shift_payload = None

    # 8. Fetch Forensic Fraud Flags
    flags_stmt = (
        select(FraudFlag)
        .where(
            FraudFlag.tenant_id == tenant_id,
            FraudFlag.attendance_event_id == event_id,
        )
        .order_by(FraudFlag.detected_at.asc())
    )
    flag_records = list((await session.execute(flags_stmt)).scalars().all())
    signals = [FraudFlagResponse.model_validate(f) for f in flag_records]

    # 9. Fetch Review Decision History
    rev_stmt = (
        select(FraudReview, User.full_name, User.email)
        .join(
            User,
            (User.tenant_id == FraudReview.tenant_id)
            & (User.id == FraudReview.reviewer_user_id),
        )
        .where(
            FraudReview.tenant_id == tenant_id,
            FraudReview.attendance_event_id == event_id,
        )
        .order_by(FraudReview.decided_at.desc())
    )
    rev_rows = (await session.execute(rev_stmt)).all()
    review_history = [
        FraudReviewHistoryItem(
            id=r.FraudReview.id,
            tenant_id=r.FraudReview.tenant_id,
            attendance_event_id=r.FraudReview.attendance_event_id,
            reviewer_user_id=r.FraudReview.reviewer_user_id,
            reviewer_name=r.full_name,
            reviewer_email=r.email,
            reviewer_role=r.FraudReview.reviewer_role,
            decision=r.FraudReview.decision,
            reason=r.FraudReview.reason,
            notes=r.FraudReview.notes,
            metadata_json=r.FraudReview.metadata_json,
            decided_at=r.FraudReview.decided_at,
            created_at=r.FraudReview.created_at,
        )
        for r in rev_rows
    ]

    return FraudEventReviewDetailResponse(
        attendance_event_id=event.id,
        tenant_id=event.tenant_id,
        employee_id=event.employee_id,
        employee_name=f"{employee.first_name} {employee.last_name}" if employee else None,
        employee_code=employee.employee_id if employee else None,
        employee_department=dept_name,
        event_type=event.event_type,
        effective_at=event.effective_at,
        server_received_at=event.server_received_at,
        source=event.source,
        review_status=event.review_status,
        risk_score=event.risk_score or 0,
        risk_category=event.risk_category or "NORMAL",
        timestamp_verification_status=event.timestamp_verification_status,
        clock_drift_seconds=float(event.clock_drift_seconds) if event.clock_drift_seconds is not None else None,
        location=location_payload,
        device=device_payload,
        shift=shift_payload,
        signals=signals,
        review_history=review_history,
    )


async def adjudicate_fraud_event(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    event_id: uuid.UUID,
    payload: FraudReviewDecisionRequest,
    reviewer_user: User,
    reviewer_role: UserRole | str,
) -> FraudReviewDecisionResponse:
    """Performs atomic adjudication of a flagged attendance event.
    Enforces concurrency row-locking, self-review prohibition, reason validation,
    immutable audit recording, and automatic attendance recalculation.
    """
    # 1. Row-lock target attendance event
    stmt = (
        select(AttendanceEvent)
        .where(
            AttendanceEvent.tenant_id == tenant_id,
            AttendanceEvent.id == event_id,
        )
        .with_for_update()
    )
    event = (await session.execute(stmt)).scalar_one_or_none()
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Attendance event '{event_id}' not found.",
        )

    # 2. Check Adjudication Permission
    role_enum = UserRole(reviewer_role) if isinstance(reviewer_role, str) else reviewer_role
    if not has_permission(role_enum, Permission.REVIEW_FRAUD_EVENTS):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to adjudicate attendance fraud reviews.",
        )

    # 3. Enforce Self-Review Prohibition
    # Check if the reviewer is linked to the employee whose attendance was flagged
    reviewer_emp_stmt = select(Employee.id).where(
        Employee.tenant_id == tenant_id,
        Employee.user_id == reviewer_user.id,
    )
    reviewer_emp_id = (await session.execute(reviewer_emp_stmt)).scalar_one_or_none()
    if reviewer_emp_id is not None and reviewer_emp_id == event.employee_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Self-review prohibited: Users cannot adjudicate their own attendance fraud reviews.",
        )

    # 4. Validate Decision & Reason
    decision = payload.decision.upper()
    if decision not in ("APPROVED", "REJECTED"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Decision must be either 'APPROVED' or 'REJECTED'.",
        )

    reason_clean = payload.reason.strip()
    if len(reason_clean) < 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Mandatory review reason must be at least 3 characters long.",
        )

    # 5. Create immutable audit review record
    now = datetime.now(UTC)
    review_record = FraudReview(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        attendance_event_id=event.id,
        reviewer_user_id=reviewer_user.id,
        reviewer_role=role_enum.value,
        decision=decision,
        reason=reason_clean,
        notes=payload.notes.strip() if payload.notes else None,
        metadata_json=payload.metadata,
        decided_at=now,
        created_at=now,
    )
    session.add(review_record)

    # 6. Update attendance event review status atomically
    event.review_status = decision

    # 7. Trigger Daily Attendance Projection Recalculation
    tenant_stmt = select(Tenant.timezone).where(Tenant.id == tenant_id)
    tenant_tz = (await session.execute(tenant_stmt)).scalar_one_or_none() or "UTC"

    shift_date = await determine_shift_date_for_punch(
        session=session,
        tenant_id=tenant_id,
        employee_id=event.employee_id,
        effective_at=event.effective_at,
        event_type=event.event_type,
        tenant_timezone=tenant_tz,
    )

    day_record = await recalculate_attendance_day(
        session=session,
        tenant_id=tenant_id,
        employee_id=event.employee_id,
        attendance_date=shift_date,
    )

    await session.flush()

    history_item = FraudReviewHistoryItem(
        id=review_record.id,
        tenant_id=review_record.tenant_id,
        attendance_event_id=review_record.attendance_event_id,
        reviewer_user_id=review_record.reviewer_user_id,
        reviewer_name=reviewer_user.full_name,
        reviewer_email=reviewer_user.email,
        reviewer_role=review_record.reviewer_role,
        decision=review_record.decision,
        reason=review_record.reason,
        notes=review_record.notes,
        metadata_json=review_record.metadata_json,
        decided_at=review_record.decided_at,
        created_at=review_record.created_at,
    )

    return FraudReviewDecisionResponse(
        success=True,
        message=f"Fraud review adjudicated successfully as {decision}.",
        review=history_item,
        updated_review_status=event.review_status,
        recalculated_day_id=day_record.id if day_record else None,
    )
