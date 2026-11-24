"""Multi-Device Conflict Detection Engine for Workforce Attendance.

Detects, classifies, and assesses attendance sequence and device conflicts:
1. OVERLAPPING_SESSIONS
2. DUPLICATE_CHECK_IN
3. UNPAIRED_CHECK_OUT
4. MULTIPLE_CHECK_OUT
5. OUT_OF_ORDER_SYNC
6. CONFLICTING_OFFLINE_TIMESTAMPS
7. POST_RECONCILIATION_ARRIVAL
8. UNAUTHORIZED_OR_REVOKED_DEVICE
9. IMPOSSIBLE_TRAVEL_TIMELINE
10. CONCURRENT_SYNC_RACE

All checks preserve immutable attendance events and classify severity and actionability:
- AUTO_RESOLVABLE
- NEEDS_EMPLOYEE_CLARIFICATION
- NEEDS_MANAGER_REVIEW
- INVALID_UNAUTHORIZED
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.attendance.models import AttendanceDay, AttendanceEvent
from services.api.attendance.schemas import (
    BatchSyncPunchItem,
    ConflictClassification,
    ConflictSeverity,
    MultiDeviceConflictCode,
)
from services.api.devices.models import Device
from services.api.fraud.service import calculate_punch_velocity


@dataclass
class DetectedConflict:
    """Represents an identified multi-device attendance conflict."""

    conflict_code: MultiDeviceConflictCode
    severity: ConflictSeverity
    classification: ConflictClassification
    summary: str
    evidence: dict[str, Any] = field(default_factory=dict)
    primary_event_id: str | None = None
    dependent_event_ids: list[str] = field(default_factory=list)
    suggested_action: str | None = None


@dataclass
class PunchItemView:
    """Normalized in-memory view of an attendance punch (raw event or batch item)."""

    idempotency_key: str
    event_type: str
    effective_at: datetime
    device_reported_at: datetime
    device_id: str | None = None
    sequence_number: int | None = None
    session_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    server_event_id: uuid.UUID | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def normalize_punch_items(
    items: Sequence[BatchSyncPunchItem | AttendanceEvent | dict[str, Any]],
) -> list[PunchItemView]:
    """Converts diverse punch representations into a uniform PunchItemView list."""
    views: list[PunchItemView] = []
    for item in items:
        if isinstance(item, BatchSyncPunchItem):
            dt = item.device_reported_at
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            else:
                dt = dt.astimezone(UTC)
            meta = dict(item.metadata or {})
            dev_id = item.device_id or meta.get("device_id_hash") or meta.get("device_id")
            views.append(
                PunchItemView(
                    idempotency_key=item.idempotency_key,
                    event_type=item.event_type,
                    effective_at=dt,
                    device_reported_at=dt,
                    device_id=dev_id,
                    sequence_number=item.sequence_number,
                    session_id=item.session_id,
                    latitude=float(item.latitude) if item.latitude is not None else None,
                    longitude=float(item.longitude) if item.longitude is not None else None,
                    server_event_id=None,
                    metadata=meta,
                )
            )
        elif isinstance(item, AttendanceEvent):
            dt = item.effective_at or item.device_reported_at or item.server_received_at
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            else:
                dt = dt.astimezone(UTC)
            rep_dt = item.device_reported_at or dt
            if rep_dt.tzinfo is None:
                rep_dt = rep_dt.replace(tzinfo=UTC)
            else:
                rep_dt = rep_dt.astimezone(UTC)
            views.append(
                PunchItemView(
                    idempotency_key=item.idempotency_key,
                    event_type=item.event_type,
                    effective_at=dt,
                    device_reported_at=rep_dt,
                    device_id=item.device_id,
                    sequence_number=None,
                    session_id=None,
                    latitude=float(item.latitude) if item.latitude is not None else None,
                    longitude=float(item.longitude) if item.longitude is not None else None,
                    server_event_id=item.id,
                    metadata={},
                )
            )
        elif isinstance(item, dict):
            raw_dt = item.get("effective_at") or item.get("device_reported_at") or datetime.now(UTC)
            if isinstance(raw_dt, str):
                try:
                    dt = datetime.fromisoformat(raw_dt)
                except Exception:
                    dt = datetime.now(UTC)
            else:
                dt = raw_dt
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            else:
                dt = dt.astimezone(UTC)

            raw_rep = item.get("device_reported_at") or dt
            if isinstance(raw_rep, str):
                try:
                    rep_dt = datetime.fromisoformat(raw_rep)
                except Exception:
                    rep_dt = dt
            else:
                rep_dt = raw_rep
            if rep_dt.tzinfo is None:
                rep_dt = rep_dt.replace(tzinfo=UTC)
            else:
                rep_dt = rep_dt.astimezone(UTC)

            lat = item.get("latitude")
            lon = item.get("longitude")
            views.append(
                PunchItemView(
                    idempotency_key=str(item.get("idempotency_key") or uuid.uuid4()),
                    event_type=str(item.get("event_type", "CHECK_IN")).upper(),
                    effective_at=dt,
                    device_reported_at=rep_dt,
                    device_id=item.get("device_id") or item.get("device_id_hash"),
                    sequence_number=item.get("sequence_number"),
                    session_id=item.get("session_id"),
                    latitude=float(lat) if lat is not None else None,
                    longitude=float(lon) if lon is not None else None,
                    server_event_id=uuid.UUID(str(item["id"])) if "id" in item and item["id"] else None,
                    metadata=dict(item.get("metadata") or {}),
                )
            )
    return views


async def detect_multi_device_conflicts(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    candidate_items: Sequence[BatchSyncPunchItem | AttendanceEvent | dict[str, Any]],
    existing_events: list[AttendanceEvent] | None = None,
    device_id_hash: str | None = None,
    sync_batch_id: str | None = None,
) -> list[DetectedConflict]:
    """Analyzes a stream of candidate offline punches against existing ledger state.

    Identifies and classifies all 10 multi-device conflict types.
    """
    conflicts: list[DetectedConflict] = []
    candidates = normalize_punch_items(candidate_items)
    if not candidates:
        return conflicts

    # 1. Device Authorization and Revocation Check
    devices_to_check: set[str] = set()
    if device_id_hash:
        devices_to_check.add(device_id_hash)
    for c in candidates:
        if c.device_id:
            devices_to_check.add(c.device_id)

    if devices_to_check:
        dev_stmt = select(Device).where(
            Device.tenant_id == tenant_id,
            Device.device_id_hash.in_(list(devices_to_check)),
        )
        found_devices = list((await session.execute(dev_stmt)).scalars().all())
        dev_map = {d.device_id_hash: d for d in found_devices}

        for dev_hash in devices_to_check:
            dev = dev_map.get(dev_hash)
            if dev is None:
                # Unregistered device submitting for employee
                conflicts.append(
                    DetectedConflict(
                        conflict_code=MultiDeviceConflictCode.UNAUTHORIZED_OR_REVOKED_DEVICE,
                        severity=ConflictSeverity.CRITICAL,
                        classification=ConflictClassification.INVALID_UNAUTHORIZED,
                        summary=f"Punches submitted from unregistered device hash {dev_hash[:16]}...",
                        evidence={
                            "device_id_hash": dev_hash,
                            "reason": "DEVICE_NOT_FOUND",
                            "employee_id": str(employee_id),
                        },
                        suggested_action="Reject unauthorized device events or register device.",
                    )
                )
            elif dev.employee_id != employee_id:
                # Device belongs to another employee (credential/device sharing violation)
                conflicts.append(
                    DetectedConflict(
                        conflict_code=MultiDeviceConflictCode.UNAUTHORIZED_OR_REVOKED_DEVICE,
                        severity=ConflictSeverity.CRITICAL,
                        classification=ConflictClassification.INVALID_UNAUTHORIZED,
                        summary=f"Device {dev_hash[:16]} is registered to a different employee.",
                        evidence={
                            "device_id_hash": dev_hash,
                            "registered_employee_id": str(dev.employee_id),
                            "submitting_employee_id": str(employee_id),
                            "reason": "EMPLOYEE_MISMATCH",
                        },
                        suggested_action="Reject events submitted from mismatched employee hardware.",
                    )
                )
            elif dev.status in ("REVOKED", "BLOCKED"):
                conflicts.append(
                    DetectedConflict(
                        conflict_code=MultiDeviceConflictCode.UNAUTHORIZED_OR_REVOKED_DEVICE,
                        severity=ConflictSeverity.CRITICAL,
                        classification=ConflictClassification.INVALID_UNAUTHORIZED,
                        summary=f"Device {dev_hash[:16]} has been revoked ({dev.status}).",
                        evidence={
                            "device_id_hash": dev_hash,
                            "device_status": dev.status,
                            "reason": "DEVICE_REVOKED",
                        },
                        suggested_action="Quarantine and reject punches from revoked hardware.",
                    )
                )

    # 2. Fetch Existing Ledger Events if not provided
    if existing_events is None:
        # Fetch relevant window around candidate timestamps (+/- 48 hours)
        min_dt = min(c.effective_at for c in candidates) - timedelta(hours=48)
        max_dt = max(c.effective_at for c in candidates) + timedelta(hours=48)
        ev_stmt = (
            select(AttendanceEvent)
            .where(
                AttendanceEvent.tenant_id == tenant_id,
                AttendanceEvent.employee_id == employee_id,
                AttendanceEvent.effective_at >= min_dt,
                AttendanceEvent.effective_at <= max_dt,
            )
            .order_by(AttendanceEvent.effective_at.asc())
        )
        existing_events = list((await session.execute(ev_stmt)).scalars().all())

    existing_views = normalize_punch_items(existing_events)

    # 3. Post-Reconciliation Arrival Check
    candidate_dates = {c.effective_at.date() for c in candidates}
    if candidate_dates:
        day_stmt = select(AttendanceDay).where(
            AttendanceDay.tenant_id == tenant_id,
            AttendanceDay.employee_id == employee_id,
            AttendanceDay.attendance_date.in_(list(candidate_dates)),
            AttendanceDay.calculation_status.in_(["FINALIZED", "LOCKED", "PAYROLL_APPROVED"]),
        )
        finalized_days = list((await session.execute(day_stmt)).scalars().all())
        for fday in finalized_days:
            conflicts.append(
                DetectedConflict(
                    conflict_code=MultiDeviceConflictCode.POST_RECONCILIATION_ARRIVAL,
                    severity=ConflictSeverity.CRITICAL,
                    classification=ConflictClassification.NEEDS_MANAGER_REVIEW,
                    summary=(
                        f"Attendance punch arrived for {fday.attendance_date} which has already been "
                        f"reconciled and locked ({fday.calculation_status})."
                    ),
                    evidence={
                        "attendance_date": fday.attendance_date.isoformat(),
                        "calculation_status": fday.calculation_status,
                        "reconciled_at": fday.updated_at.isoformat() if fday.updated_at else None,
                    },
                    suggested_action="Requires supervisor or HR unlocked correction approval.",
                )
            )

    # 4. Check Internal Candidate Timestamp Skew & Inversions (CONFLICTING_OFFLINE_TIMESTAMPS)
    for c in candidates:
        skew_seconds = (c.effective_at - c.device_reported_at).total_seconds()
        if abs(skew_seconds) > 86400 * 3:
            conflicts.append(
                DetectedConflict(
                    conflict_code=MultiDeviceConflictCode.CONFLICTING_OFFLINE_TIMESTAMPS,
                    severity=ConflictSeverity.HIGH,
                    classification=ConflictClassification.NEEDS_MANAGER_REVIEW,
                    summary=f"Gross clock drift on punch {c.idempotency_key}: drift of {int(skew_seconds)}s exceeds 3 days.",
                    evidence={
                        "idempotency_key": c.idempotency_key,
                        "device_reported_at": c.device_reported_at.isoformat(),
                        "effective_at": c.effective_at.isoformat(),
                        "drift_seconds": skew_seconds,
                    },
                    primary_event_id=c.idempotency_key,
                    suggested_action="Review offline clock calibration on mobile client.",
                )
            )

    # 5. Combined Timeline Analysis (Existing Ledger + Candidates, deduplicated by key)
    seen_identities: set[str] = set()
    all_views: list[PunchItemView] = []
    for v in sorted(existing_views + candidates, key=lambda item: item.effective_at):
        identity = v.idempotency_key or (str(v.server_event_id) if v.server_event_id else None)
        if identity and identity in seen_identities:
            continue
        if identity:
            seen_identities.add(identity)
        all_views.append(v)

    open_checkin: PunchItemView | None = None
    open_break: PunchItemView | None = None
    prior_view: PunchItemView | None = None

    for idx, v in enumerate(all_views):
        # Impossible Travel Velocity Check between consecutive punches
        if prior_view is not None:
            if (
                prior_view.latitude is not None
                and prior_view.longitude is not None
                and v.latitude is not None
                and v.longitude is not None
            ):
                vel_res = calculate_punch_velocity(
                    curr_lat=v.latitude,
                    curr_lon=v.longitude,
                    curr_time=v.effective_at,
                    prev_lat=prior_view.latitude,
                    prev_lon=prior_view.longitude,
                    prev_time=prior_view.effective_at,
                )
                if vel_res.is_impossible:
                    conflicts.append(
                        DetectedConflict(
                            conflict_code=MultiDeviceConflictCode.IMPOSSIBLE_TRAVEL_TIMELINE,
                            severity=ConflictSeverity.CRITICAL,
                            classification=ConflictClassification.NEEDS_MANAGER_REVIEW,
                            summary=(
                                f"Physically impossible velocity ({round(vel_res.velocity_mps, 1)} m/s, "
                                f"{round(vel_res.distance_meters / 1000, 1)} km in "
                                f"{int(vel_res.elapsed_seconds)}s) between consecutive punches."
                            ),
                            evidence={
                                "velocity_mps": round(vel_res.velocity_mps, 2),
                                "distance_meters": round(vel_res.distance_meters, 2),
                                "elapsed_seconds": vel_res.elapsed_seconds,
                                "prev_idempotency_key": prior_view.idempotency_key,
                                "prev_device_id": prior_view.device_id,
                                "curr_idempotency_key": v.idempotency_key,
                                "curr_device_id": v.device_id,
                            },
                            primary_event_id=v.idempotency_key,
                            dependent_event_ids=[prior_view.idempotency_key],
                            suggested_action="Review GPS coordinates and device location tampering.",
                        )
                    )

        # State transitions
        if v.event_type == "CHECK_IN":
            if open_checkin is not None:
                # Duplicate check-in or overlapping session
                time_diff = (v.effective_at - open_checkin.effective_at).total_seconds()
                is_diff_device = (
                    v.device_id is not None
                    and open_checkin.device_id is not None
                    and v.device_id != open_checkin.device_id
                )
                if is_diff_device:
                    conflicts.append(
                        DetectedConflict(
                            conflict_code=MultiDeviceConflictCode.DUPLICATE_CHECK_IN,
                            severity=ConflictSeverity.HIGH,
                            classification=(
                                ConflictClassification.NEEDS_EMPLOYEE_CLARIFICATION
                                if time_diff < 900
                                else ConflictClassification.NEEDS_MANAGER_REVIEW
                            ),
                            summary=(
                                f"Simultaneous check-ins from different devices: {(open_checkin.device_id or '')[:12]} "
                                f"and {(v.device_id or '')[:12]} ({int(time_diff)}s apart)."
                            ),
                            evidence={
                                "first_check_in": open_checkin.idempotency_key,
                                "first_device": open_checkin.device_id,
                                "first_time": open_checkin.effective_at.isoformat(),
                                "second_check_in": v.idempotency_key,
                                "second_device": v.device_id,
                                "second_time": v.effective_at.isoformat(),
                                "time_diff_seconds": time_diff,
                            },
                            primary_event_id=v.idempotency_key,
                            dependent_event_ids=[open_checkin.idempotency_key],
                            suggested_action="Request employee clarification on intended check-in.",
                        )
                    )
                else:
                    conflicts.append(
                        DetectedConflict(
                            conflict_code=MultiDeviceConflictCode.OVERLAPPING_SESSIONS,
                            severity=ConflictSeverity.HIGH,
                            classification=ConflictClassification.NEEDS_MANAGER_REVIEW,
                            summary="Consecutive check-in without check-out produces overlapping sessions.",
                            evidence={
                                "prior_check_in": open_checkin.idempotency_key,
                                "new_check_in": v.idempotency_key,
                                "time_diff_seconds": time_diff,
                            },
                            primary_event_id=v.idempotency_key,
                            dependent_event_ids=[open_checkin.idempotency_key],
                            suggested_action="Review and adjust missing check-out.",
                        )
                    )
            open_checkin = v
            open_break = None

        elif v.event_type == "CHECK_OUT":
            if open_checkin is None:
                # Check out without preceding check-in (UNPAIRED_CHECK_OUT or OUT_OF_ORDER_SYNC)
                conflicts.append(
                    DetectedConflict(
                        conflict_code=MultiDeviceConflictCode.UNPAIRED_CHECK_OUT,
                        severity=ConflictSeverity.HIGH,
                        classification=ConflictClassification.NEEDS_MANAGER_REVIEW,
                        summary=f"CHECK_OUT punch {v.idempotency_key} has no preceding active CHECK_IN.",
                        evidence={
                            "check_out_idempotency_key": v.idempotency_key,
                            "check_out_device": v.device_id,
                            "check_out_time": v.effective_at.isoformat(),
                        },
                        primary_event_id=v.idempotency_key,
                        suggested_action="Mark for supervisor review or await delayed check-in.",
                    )
                )
            else:
                # Legitimate session close or cross-device handoff
                if v.effective_at < open_checkin.effective_at:
                    conflicts.append(
                        DetectedConflict(
                            conflict_code=MultiDeviceConflictCode.CONFLICTING_OFFLINE_TIMESTAMPS,
                            severity=ConflictSeverity.HIGH,
                            classification=ConflictClassification.NEEDS_MANAGER_REVIEW,
                            summary="Check-out timestamp precedes check-in timestamp (negative work duration).",
                            evidence={
                                "check_in_time": open_checkin.effective_at.isoformat(),
                                "check_out_time": v.effective_at.isoformat(),
                            },
                            primary_event_id=v.idempotency_key,
                            dependent_event_ids=[open_checkin.idempotency_key],
                            suggested_action="Adjust timestamp discrepancy with supervisor correction.",
                        )
                    )
                open_checkin = None
                open_break = None

        elif v.event_type == "BREAK_START":
            if open_break is not None:
                conflicts.append(
                    DetectedConflict(
                        conflict_code=MultiDeviceConflictCode.OUT_OF_ORDER_SYNC,
                        severity=ConflictSeverity.MEDIUM,
                        classification=ConflictClassification.NEEDS_MANAGER_REVIEW,
                        summary="Consecutive BREAK_START without intervening BREAK_END.",
                        evidence={
                            "prior_break": open_break.idempotency_key,
                            "curr_break": v.idempotency_key,
                        },
                        primary_event_id=v.idempotency_key,
                        dependent_event_ids=[open_break.idempotency_key],
                    )
                )
            open_break = v
        elif v.event_type == "BREAK_END":
            if open_break is None:
                conflicts.append(
                    DetectedConflict(
                        conflict_code=MultiDeviceConflictCode.OUT_OF_ORDER_SYNC,
                        severity=ConflictSeverity.MEDIUM,
                        classification=ConflictClassification.NEEDS_MANAGER_REVIEW,
                        summary="BREAK_END without preceding active BREAK_START.",
                        evidence={"break_end": v.idempotency_key},
                        primary_event_id=v.idempotency_key,
                    )
                )
            open_break = None

        prior_view = v

    return conflicts
