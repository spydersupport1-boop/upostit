"""Attendance reconciliation service identifying unclosed or stranded sessions and recomputing projections."""

import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.attendance.models import AttendanceDay, AttendanceEvent, ShiftAssignment
from services.api.attendance.schemas import ReconciliationRequest, ReconciliationResponse
from services.api.attendance.service import recalculate_attendance_day
from services.api.employees.models import Employee

logger = logging.getLogger("attendance.reconciliation")


async def run_attendance_reconciliation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    payload: ReconciliationRequest,
) -> ReconciliationResponse:
    """Executes a bounded, safe-to-retry reconciliation job across target attendance dates.

    Invariants:
    - Never modifies or deletes immutable attendance events.
    - Pure projection recalculation from raw events.
    - Serialized employee row locking to prevent conflicting concurrent recalculations.
    - Logs errors without exposing employee PII.
    - Chunked batch processing.
    """
    # 1. Resolve Target Dates
    target_dates: list[date] = []
    if payload.target_date is not None:
        target_dates = [payload.target_date]
    elif payload.start_date is not None and payload.end_date is not None:
        curr = payload.start_date
        while curr <= payload.end_date:
            target_dates.append(curr)
            curr += timedelta(days=1)
    else:
        # Default to yesterday's attendance date
        yesterday = (datetime.now(UTC) - timedelta(days=1)).date()
        target_dates = [yesterday]

    recalculated_count = 0
    failed_count = 0
    errors: list[str] = []
    total_candidates = 0

    for t_date in target_dates:
        # 2. Identify Candidate Employee IDs for this date
        candidate_ids: set[uuid.UUID] = set()

        if payload.employee_id is not None:
            # Single employee targeted
            emp_chk = (
                await session.execute(
                    select(Employee.id).where(
                        Employee.tenant_id == tenant_id,
                        Employee.id == payload.employee_id,
                    )
                )
            ).scalar_one_or_none()
            if emp_chk:
                candidate_ids.add(emp_chk)
        else:
            # A. Employees with active shift assignments on this date
            asgn_stmt = select(ShiftAssignment.employee_id).where(
                ShiftAssignment.tenant_id == tenant_id,
                ShiftAssignment.effective_from <= t_date,
                (ShiftAssignment.effective_to.is_(None) | (ShiftAssignment.effective_to >= t_date)),
            )
            asgn_emps = (await session.execute(asgn_stmt)).scalars().all()
            candidate_ids.update(asgn_emps)

            # B. Employees who have existing attendance day projections on this date
            day_stmt = select(AttendanceDay.employee_id).where(
                AttendanceDay.tenant_id == tenant_id,
                AttendanceDay.attendance_date == t_date,
            )
            day_emps = (await session.execute(day_stmt)).scalars().all()
            candidate_ids.update(day_emps)

            # C. Employees who have punches falling on or near this date
            dt_start = datetime.combine(t_date - timedelta(days=1), datetime.min.time(), tzinfo=UTC)
            dt_end = datetime.combine(t_date + timedelta(days=1), datetime.max.time(), tzinfo=UTC)
            ev_stmt = select(AttendanceEvent.employee_id).where(
                AttendanceEvent.tenant_id == tenant_id,
                AttendanceEvent.effective_at >= dt_start,
                AttendanceEvent.effective_at <= dt_end,
            )
            ev_emps = (await session.execute(ev_stmt)).scalars().all()
            candidate_ids.update(ev_emps)

        sorted_candidates = sorted(candidate_ids)
        total_candidates += len(sorted_candidates)

        # 3. Process candidates in bounded batches
        batch_size = payload.batch_size
        for i in range(0, len(sorted_candidates), batch_size):
            batch = sorted_candidates[i : i + batch_size]
            for emp_id in batch:
                try:
                    # Execute recalculation with savepoint isolation per employee
                    async with session.begin_nested():
                        await recalculate_attendance_day(
                            session=session,
                            tenant_id=tenant_id,
                            employee_id=emp_id,
                            attendance_date=t_date,
                        )
                    recalculated_count += 1
                except Exception as exc:
                    failed_count += 1
                    # Sanitized logging: only UUID and error type, zero employee PII (names/emails)
                    logger.error(
                        "Reconciliation failed for employee %s on date %s: %s",
                        emp_id,
                        t_date,
                        type(exc).__name__,
                    )
                    errors.append(f"Employee {emp_id} on {t_date}: {type(exc).__name__}")

    status_str = (
        "COMPLETED" if failed_count == 0 else ("PARTIAL" if recalculated_count > 0 else "FAILED")
    )

    return ReconciliationResponse(
        status=status_str,
        tenant_id=tenant_id,
        target_dates=target_dates,
        total_candidates=total_candidates,
        recalculated_count=recalculated_count,
        failed_count=failed_count,
        errors=errors[:50],  # Cap sanitized errors
    )
