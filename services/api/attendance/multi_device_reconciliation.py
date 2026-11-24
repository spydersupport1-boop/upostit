"""Multi-Device Session Reconciliation Service.

Pure projection recalculation from immutable attendance events.
Handles:
- Clean cross-device handoffs (e.g. Device A check-in -> Device B check-out).
- Out-of-order event synchronization and retroactive pairing.
- Ambiguous or conflicting timelines marked with AttendanceConflictIncident.
- Projection recalculation without modifying immutable event ledger.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.attendance.conflict_detector import (
    DetectedConflict,
    detect_multi_device_conflicts,
)
from services.api.attendance.models import (
    AttendanceConflictIncident,
    AttendanceDay,
    AttendanceEvent,
)
from services.api.attendance.schemas import (
    ConflictClassification,
    ConflictIncidentStatus,
)
from services.api.attendance.service import recalculate_attendance_day
from services.api.employees.models import Employee

logger = logging.getLogger("attendance.multi_device_reconciliation")


@dataclass
class MultiDeviceReconciliationResult:
    """Outcome of multi-device session reconciliation for an employee."""

    tenant_id: uuid.UUID
    employee_id: uuid.UUID
    attendance_date: date
    status: str  # "AUTO_RESOLVED", "CLEAN", "NEEDS_REVIEW", "ERROR"
    conflicts_detected: list[DetectedConflict] = field(default_factory=list)
    created_incident_ids: list[uuid.UUID] = field(default_factory=list)
    recalculated_day: AttendanceDay | None = None
    summary: str = ""


async def reconcile_employee_multi_device_sessions(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    attendance_date: date,
    events: list[AttendanceEvent] | None = None,
    sync_batch_id: str | None = None,
    auto_create_incidents: bool = True,
) -> MultiDeviceReconciliationResult:
    """Reconciles attendance sessions across multiple devices for a specific date.

    Invariants:
    - Never mutates or deletes original AttendanceEvent records.
    - Deterministic and idempotent.
    - Clean cross-device handoffs resolve automatically without generating false incidents.
    - True anomalies create an AttendanceConflictIncident for supervisor adjudication.
    """
    # 1. Fetch relevant events for the date if not supplied
    if events is None:
        day_start = datetime.combine(attendance_date - timedelta(days=1), datetime.min.time(), tzinfo=UTC)
        day_end = datetime.combine(attendance_date + timedelta(days=1), datetime.max.time(), tzinfo=UTC)
        ev_stmt = (
            select(AttendanceEvent)
            .where(
                AttendanceEvent.tenant_id == tenant_id,
                AttendanceEvent.employee_id == employee_id,
                AttendanceEvent.effective_at >= day_start,
                AttendanceEvent.effective_at <= day_end,
            )
            .order_by(AttendanceEvent.effective_at.asc(), AttendanceEvent.server_received_at.asc())
        )
        events = list((await session.execute(ev_stmt)).scalars().all())

    if not events:
        day = await recalculate_attendance_day(session, tenant_id, employee_id, attendance_date)
        return MultiDeviceReconciliationResult(
            tenant_id=tenant_id,
            employee_id=employee_id,
            attendance_date=attendance_date,
            status="CLEAN",
            recalculated_day=day,
            summary="No events found for date window; day projection recalculated cleanly.",
        )

    # 2. Run Multi-Device Conflict Detection
    conflicts = await detect_multi_device_conflicts(
        session=session,
        tenant_id=tenant_id,
        employee_id=employee_id,
        candidate_items=events,
        existing_events=events,
        sync_batch_id=sync_batch_id,
    )

    # Filter out pure auto-resolvable items (e.g. valid clean cross-device handoffs)
    actionable_conflicts = [
        c for c in conflicts if c.classification != ConflictClassification.AUTO_RESOLVABLE
    ]

    created_incident_ids: list[uuid.UUID] = []

    # 3. Create Conflict Incidents for Actionable Conflicts if requested
    if auto_create_incidents and actionable_conflicts:
        # Resolve submitting user_id for employee
        emp_stmt = select(Employee).where(
            Employee.tenant_id == tenant_id,
            Employee.id == employee_id,
        )
        emp = (await session.execute(emp_stmt)).scalar_one_or_none()
        user_id = emp.user_id if emp and emp.user_id else employee_id

        for c in actionable_conflicts:
            bundle_key = f"rec_{attendance_date.isoformat()}_{c.conflict_code}_{c.primary_event_id or uuid.uuid4()}"[:64]

            # Check if incident already exists for this bundle
            inc_stmt = select(AttendanceConflictIncident).where(
                AttendanceConflictIncident.tenant_id == tenant_id,
                AttendanceConflictIncident.bundle_id == bundle_key,
            )
            existing_inc = (await session.execute(inc_stmt)).scalar_one_or_none()

            if existing_inc is None:
                # Primary event data
                prim_data: dict[str, Any] = {
                    "event_type": "CHECK_IN",
                    "idempotency_key": c.primary_event_id or str(uuid.uuid4()),
                    "device_reported_at": datetime.now(UTC).isoformat(),
                    "conflict_code": str(c.conflict_code),
                }
                for ev in events:
                    if str(ev.idempotency_key) == c.primary_event_id or str(ev.id) == c.primary_event_id:
                        prim_data = {
                            "event_type": ev.event_type,
                            "idempotency_key": ev.idempotency_key,
                            "device_reported_at": (ev.device_reported_at or ev.effective_at).isoformat(),
                            "device_id_hash": ev.device_id,
                            "location_id": str(ev.location_id) if ev.location_id else None,
                        }
                        break

                dep_data: list[dict[str, Any]] = []
                for dep_id in c.dependent_event_ids:
                    for ev in events:
                        if str(ev.idempotency_key) == dep_id or str(ev.id) == dep_id:
                            dep_data.append(
                                {
                                    "event_type": ev.event_type,
                                    "idempotency_key": ev.idempotency_key,
                                    "device_reported_at": (ev.device_reported_at or ev.effective_at).isoformat(),
                                    "device_id_hash": ev.device_id,
                                    "location_id": str(ev.location_id) if ev.location_id else None,
                                }
                            )
                            break

                incident_status = (
                    ConflictIncidentStatus.NEEDS_CLARIFICATION
                    if c.classification == ConflictClassification.NEEDS_EMPLOYEE_CLARIFICATION
                    else ConflictIncidentStatus.PENDING_REVIEW
                )

                incident = AttendanceConflictIncident(
                    tenant_id=tenant_id,
                    employee_id=employee_id,
                    user_id=user_id,
                    bundle_id=bundle_key,
                    session_id=None,
                    status=incident_status,
                    conflict_code=str(c.conflict_code),
                    severity=str(c.severity),
                    classification=str(c.classification),
                    primary_rejected_event=prim_data,
                    dependent_events=dep_data,
                    total_events_count=1 + len(dep_data),
                    rejection_summary=c.summary[:255],
                    employee_notes=c.suggested_action,
                    submitted_at=datetime.now(UTC),
                    metadata_json={
                        "evidence": c.evidence,
                        "source": "MULTI_DEVICE_RECONCILIATION_ENGINE",
                        "attendance_date": attendance_date.isoformat(),
                    },
                )
                session.add(incident)
                await session.flush()
                created_incident_ids.append(incident.id)

    # 4. Pure Projection Recalculation
    day = await recalculate_attendance_day(session, tenant_id, employee_id, attendance_date)

    status_str = "NEEDS_REVIEW" if actionable_conflicts else "AUTO_RESOLVED"
    summary_str = (
        f"Reconciled date {attendance_date}: {len(actionable_conflicts)} actionable conflicts identified, "
        f"{len(created_incident_ids)} incidents created."
        if actionable_conflicts
        else f"Clean cross-device reconciliation for {attendance_date} completed successfully."
    )

    return MultiDeviceReconciliationResult(
        tenant_id=tenant_id,
        employee_id=employee_id,
        attendance_date=attendance_date,
        status=status_str,
        conflicts_detected=actionable_conflicts,
        created_incident_ids=created_incident_ids,
        recalculated_day=day,
        summary=summary_str,
    )
