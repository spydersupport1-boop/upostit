"""Pure functional timeline resolution and attendance calculation engine.

Zero database dependencies. Fully deterministic and unit-testable.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from services.api.attendance.models import AttendanceEvent, ShiftTemplateVersion


@dataclass(frozen=True)
class BreakInterval:
    """Represents a discrete break interval within a work session."""

    start: datetime
    end: datetime | None
    duration_minutes: int = 0
    is_open: bool = False


@dataclass
class WorkSession:
    """Represents a work session opened by CHECK_IN and closed by CHECK_OUT."""

    check_in: datetime
    check_out: datetime | None = None
    breaks: list[BreakInterval] = field(default_factory=list)
    gross_minutes: int = 0
    break_minutes: int = 0
    net_minutes: int = 0
    is_open: bool = False


@dataclass
class ResolvedTimeline:
    """Output of the timeline resolution algorithm."""

    active_events: list[AttendanceEvent]
    sessions: list[WorkSession]
    first_check_in: datetime | None
    last_check_out: datetime | None
    unclosed_session: bool
    unclosed_break: bool
    has_suspicious_events: bool
    anomalies: list[str]
    source_event_ids: list[str]


@dataclass(frozen=True)
class OvertimeCalculationDetails:
    """Detailed overtime calculation breakdown for a single attendance day."""

    raw_overtime_minutes: int
    eligible_overtime_minutes: int
    multiplier: Decimal
    payable_overtime_minutes: int
    overtime_type: str  # 'WORKDAY', 'WEEK_OFF', 'HOLIDAY'
    requires_approval: bool
    status: str  # 'AUTO_APPROVED', 'PENDING_APPROVAL'
    rule_id: uuid.UUID | None


@dataclass
class AttendanceDayCalculationResult:
    """Output of the pure attendance day calculation engine."""

    attendance_date: date
    shift_template_id: uuid.UUID | None
    shift_version_id: uuid.UUID | None
    first_check_in: datetime | None
    last_check_out: datetime | None
    total_working_minutes: int
    total_break_minutes: int
    net_working_minutes: int
    actual_late_minutes: int
    late_arrival_minutes: int
    actual_early_minutes: int
    early_departure_minutes: int
    overtime_minutes: int
    status: str
    calculation_status: str
    is_incomplete: bool
    missing_punch: bool
    source_event_ids: list[str]
    metadata: dict[str, Any]
    overtime_details: OvertimeCalculationDetails | None = None


def resolve_active_timeline(events: list[AttendanceEvent]) -> ResolvedTimeline:
    """Resolves an append-only event ledger stream into an active effective timeline.

    1. Maps superseding and voiding chains in chronological order of server receipt.
    2. Drops voided, superseded, and voiding-action tombstones.
    3. Orders active events by effective timestamp.
    4. Evaluates event pairs, open breaks, and clock drift flags.
    """
    if not events:
        return ResolvedTimeline(
            active_events=[],
            sessions=[],
            first_check_in=None,
            last_check_out=None,
            unclosed_session=False,
            unclosed_break=False,
            has_suspicious_events=False,
            anomalies=[],
            source_event_ids=[],
        )

    # 1. Sort chronologically by server_received_at so later corrections take precedence
    chronological = sorted(
        events,
        key=lambda e: (
            e.server_received_at or datetime.min.replace(tzinfo=UTC),
            e.created_at or datetime.min.replace(tzinfo=UTC),
        ),
    )

    voided_ids: set[uuid.UUID] = set()
    superseded_ids: set[uuid.UUID] = set()

    for event in chronological:
        if event.event_category == "CORRECTION_VOID" and event.supersedes_event_id:
            voided_ids.add(event.supersedes_event_id)
        elif event.event_category == "CORRECTION_SUPERSEDE" and event.supersedes_event_id:
            superseded_ids.add(event.supersedes_event_id)

    # 2. Filter out voided, superseded, and voiding tombstones
    active_events: list[AttendanceEvent] = []
    source_ids: list[str] = []
    anomalies: list[str] = []
    has_suspicious = False

    for event in chronological:
        if event.id in voided_ids or event.id in superseded_ids:
            continue
        if event.event_category == "CORRECTION_VOID":
            continue
        if event.review_status == "REJECTED":
            continue

        active_events.append(event)
        source_ids.append(str(event.id))

        if event.timestamp_verification_status in (
            "SUSPICIOUS_CLOCK_DRIFT",
            "FLAGGED_SUSPICIOUS",
        ) or event.review_status in ("PENDING_REVIEW", "FLAGGED", "REQUIRED"):
            has_suspicious = True
            anomalies.append(f"Suspicious event timestamp detected on event {event.id}.")

    # 3. Sort active timeline strictly by effective_at ascending
    active_events.sort(key=lambda e: e.effective_at or datetime.min.replace(tzinfo=UTC))

    # 4. Construct sessions & pair intervals
    sessions: list[WorkSession] = []
    current_session: WorkSession | None = None
    current_break_start: datetime | None = None
    first_check_in: datetime | None = None
    last_check_out: datetime | None = None
    unclosed_session = False
    unclosed_break = False

    for ev in active_events:
        t = ev.effective_at
        if t.tzinfo is None:
            t = t.replace(tzinfo=UTC)

        if ev.event_type == "CHECK_IN":
            if first_check_in is None:
                first_check_in = t
            if current_session is not None and current_session.is_open:
                anomalies.append(
                    f"Multiple consecutive CHECK_IN at {t.isoformat()} without CHECK_OUT."
                )
            else:
                current_session = WorkSession(check_in=t, is_open=True)
                sessions.append(current_session)

        elif ev.event_type == "BREAK_START":
            if current_session is None or not current_session.is_open:
                anomalies.append(f"BREAK_START at {t.isoformat()} without active CHECK_IN.")
            elif current_break_start is not None:
                anomalies.append(f"Consecutive BREAK_START at {t.isoformat()} without BREAK_END.")
            else:
                current_break_start = t

        elif ev.event_type == "BREAK_END":
            if current_break_start is None:
                anomalies.append(f"BREAK_END at {t.isoformat()} without prior BREAK_START.")
            else:
                dur = max(0, int((t - current_break_start).total_seconds() // 60))
                break_interval = BreakInterval(
                    start=current_break_start, end=t, duration_minutes=dur, is_open=False
                )
                if current_session is not None:
                    current_session.breaks.append(break_interval)
                current_break_start = None

        elif ev.event_type == "CHECK_OUT":
            last_check_out = t
            if current_break_start is not None:
                # Open break closed implicitly or anomalous
                dur = max(0, int((t - current_break_start).total_seconds() // 60))
                break_interval = BreakInterval(
                    start=current_break_start, end=t, duration_minutes=dur, is_open=False
                )
                if current_session is not None:
                    current_session.breaks.append(break_interval)
                current_break_start = None

            if current_session is None or not current_session.is_open:
                anomalies.append(f"CHECK_OUT at {t.isoformat()} without active CHECK_IN.")
            else:
                current_session.check_out = t
                current_session.is_open = False
                gross = max(0, int((t - current_session.check_in).total_seconds() // 60))
                b_total = sum(b.duration_minutes for b in current_session.breaks)
                current_session.gross_minutes = gross
                current_session.break_minutes = b_total
                current_session.net_minutes = max(0, gross - b_total)
                current_session = None

    if current_break_start is not None:
        unclosed_break = True
        anomalies.append("Unclosed break detected at end of timeline.")

    if current_session is not None and current_session.is_open:
        unclosed_session = True
        anomalies.append("Unclosed work session (missing CHECK_OUT) detected.")

    return ResolvedTimeline(
        active_events=active_events,
        sessions=sessions,
        first_check_in=first_check_in,
        last_check_out=last_check_out,
        unclosed_session=unclosed_session,
        unclosed_break=unclosed_break,
        has_suspicious_events=has_suspicious,
        anomalies=anomalies,
        source_event_ids=source_ids,
    )


def calculate_attendance_day(
    target_date: date,
    shift_version: ShiftTemplateVersion | None,
    resolved_timeline: ResolvedTimeline,
    tenant_timezone: str = "UTC",
    now_dt: datetime | None = None,
    is_holiday: bool = False,
    is_on_leave: bool = False,
    leave_type_code: str | None = None,
    is_half_day_leave: bool = False,
    half_day_period: str | None = None,
    overtime_rule: Any = None,
) -> AttendanceDayCalculationResult:
    """Pure calculation engine evaluating work durations, tardiness, overtime, and daily presence status.

    Zero DB calls. Supports:
    - Normal single and split shifts.
    - Configurable grace periods and strict enterprise post-grace lateness/early penalty.
    - Overnight shift windows and attribution.
    - Incomplete / missing punch handling.
    - Day boundary, weekly off, and statutory holiday detection with deterministic precedence.
    - Approved full-day and half-day leave integration without counting leave as worked overtime.
    - Overtime rules engine evaluating thresholds, daily caps, categories, and multipliers.
    """
    if now_dt is None:
        now_dt = datetime.now(UTC)
    elif now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=UTC)

    try:
        tz = ZoneInfo(tenant_timezone)
    except Exception:
        tz = ZoneInfo("UTC")

    # 1. Total working and break durations across all completed sessions
    # Rule: Incomplete / open sessions do NOT count towards completed work minutes
    total_working_minutes = sum(
        s.gross_minutes for s in resolved_timeline.sessions if not s.is_open
    )
    total_break_minutes = sum(s.break_minutes for s in resolved_timeline.sessions if not s.is_open)
    net_working_minutes = max(0, total_working_minutes - total_break_minutes)

    first_in = resolved_timeline.first_check_in
    last_out = resolved_timeline.last_check_out
    is_incomplete = resolved_timeline.unclosed_session or resolved_timeline.unclosed_break
    missing_punch = is_incomplete

    # Weekly off detection (0=Sunday, 6=Saturday convention)
    # Python date.weekday(): Mon=0 ... Sun=6 -> (weekday + 1) % 7 gives Sun=0 ... Sat=6
    day_of_week = (target_date.weekday() + 1) % 7

    # 2. Case: No Shift Assigned
    if shift_version is None:
        is_weekly_off_no_shift = day_of_week in (6, 0)
        status: str
        calc_status = "CALCULATED"
        if resolved_timeline.has_suspicious_events:
            status = "PENDING_REVIEW"
            calc_status = "FLAGGED"
        elif is_incomplete:
            status = "INCOMPLETE"
            calc_status = "INCOMPLETE"
        elif is_on_leave and not is_half_day_leave:
            status = "ON_LEAVE"
        elif net_working_minutes > 0:
            status = "PRESENT"
        elif is_holiday:
            status = "HOLIDAY"
        elif is_weekly_off_no_shift:
            status = "WEEK_OFF"
        else:
            status = "ABSENT"

        ot_minutes = 0
        ot_details_no_shift: OvertimeCalculationDetails | None = None
        if (
            overtime_rule is not None
            and not is_incomplete
            and not (is_on_leave and not is_half_day_leave)
        ):
            if is_holiday:
                ot_type = "HOLIDAY"
                mult = Decimal(str(overtime_rule.holiday_multiplier))
                raw_ot = net_working_minutes
            elif is_weekly_off_no_shift:
                ot_type = "WEEK_OFF"
                mult = Decimal(str(overtime_rule.weekend_multiplier))
                raw_ot = net_working_minutes
            else:
                ot_type = "WORKDAY"
                mult = Decimal(str(overtime_rule.workday_multiplier))
                raw_ot = net_working_minutes

            if raw_ot < overtime_rule.min_overtime_threshold_minutes:
                eligible_ot = 0
            else:
                eligible_ot = raw_ot
                if (
                    overtime_rule.max_daily_overtime_minutes is not None
                    and eligible_ot > overtime_rule.max_daily_overtime_minutes
                ):
                    eligible_ot = overtime_rule.max_daily_overtime_minutes

            payable_ot = int(round(Decimal(eligible_ot) * mult))
            requires_appr = bool(
                overtime_rule.requires_manager_approval or overtime_rule.requires_pre_approval
            )
            ot_status = "PENDING_APPROVAL" if requires_appr else "AUTO_APPROVED"
            ot_minutes = eligible_ot

            ot_details_no_shift = OvertimeCalculationDetails(
                raw_overtime_minutes=raw_ot,
                eligible_overtime_minutes=eligible_ot,
                multiplier=mult,
                payable_overtime_minutes=payable_ot,
                overtime_type=ot_type,
                requires_approval=requires_appr,
                status=ot_status,
                rule_id=getattr(overtime_rule, "id", None),
            )

        return AttendanceDayCalculationResult(
            attendance_date=target_date,
            shift_template_id=None,
            shift_version_id=None,
            first_check_in=first_in,
            last_check_out=last_out,
            total_working_minutes=total_working_minutes,
            total_break_minutes=total_break_minutes,
            net_working_minutes=net_working_minutes,
            actual_late_minutes=0,
            late_arrival_minutes=0,
            actual_early_minutes=0,
            early_departure_minutes=0,
            overtime_minutes=ot_minutes,
            status=status,
            calculation_status=calc_status,
            is_incomplete=is_incomplete,
            missing_punch=missing_punch,
            source_event_ids=resolved_timeline.source_event_ids,
            metadata={
                "no_shift_assigned": True,
                "is_holiday": is_holiday,
                "is_on_leave": is_on_leave,
                "leave_type_code": leave_type_code,
                "is_half_day_leave": is_half_day_leave,
                "anomalies": resolved_timeline.anomalies,
            },
            overtime_details=ot_details_no_shift,
        )

    # 3. Case: Shift Assigned — Compute Scheduled Boundaries in Timezone
    shift_start_local = datetime.combine(target_date, shift_version.start_time, tzinfo=tz)
    sched_start_utc = shift_start_local.astimezone(UTC)

    if shift_version.is_overnight:
        shift_end_local = datetime.combine(
            target_date + timedelta(days=1), shift_version.end_time, tzinfo=tz
        )
    else:
        shift_end_local = datetime.combine(target_date, shift_version.end_time, tzinfo=tz)
    sched_end_utc = shift_end_local.astimezone(UTC)

    # Window boundaries with allowances
    window_start_utc = sched_start_utc - timedelta(
        minutes=shift_version.early_arrival_allowance_minutes
    )
    window_end_utc = sched_end_utc + timedelta(
        minutes=shift_version.late_departure_allowance_minutes
    )

    is_weekly_off = day_of_week in (shift_version.weekly_off_days or [])

    # Scheduled duration excluding configured break
    sched_gross = max(0, int((sched_end_utc - sched_start_utc).total_seconds() // 60))
    sched_net = max(0, sched_gross - shift_version.break_duration_minutes)
    if is_half_day_leave:
        sched_net = max(0, sched_net // 2)

    actual_late_minutes = 0
    late_arrival_minutes = 0
    actual_early_minutes = 0
    early_departure_minutes = 0
    overtime_minutes = 0

    has_punches = bool(resolved_timeline.active_events or resolved_timeline.sessions)

    # A. Late Arrival & Early Departure Calculation (only on normal workdays)
    if has_punches and not (is_holiday or is_weekly_off):
        if first_in is not None:
            if first_in > sched_start_utc:
                actual_late_minutes = max(
                    0, int((first_in - sched_start_utc).total_seconds() // 60)
                )
                if actual_late_minutes <= shift_version.grace_period_minutes:
                    late_arrival_minutes = 0
                else:
                    # Enterprise rule: Grace breached -> store actual minutes from scheduled start
                    late_arrival_minutes = actual_late_minutes

        if last_out is not None and not is_incomplete:
            if last_out < sched_end_utc:
                actual_early_minutes = max(0, int((sched_end_utc - last_out).total_seconds() // 60))
                if actual_early_minutes <= shift_version.early_exit_grace_minutes:
                    early_departure_minutes = 0
                else:
                    early_departure_minutes = actual_early_minutes

    # B. Overtime Calculation with Category Precedence & Rules
    ot_details: OvertimeCalculationDetails | None = None
    if has_punches and not is_incomplete and not (is_on_leave and not is_half_day_leave):
        # Deterministic Category Precedence:
        # Statutory Holiday takes precedence over Weekly Off (no double counting)
        if is_holiday:
            ot_category = "HOLIDAY"
            raw_ot = net_working_minutes
        elif is_weekly_off:
            ot_category = "WEEK_OFF"
            raw_ot = net_working_minutes
        else:
            ot_category = "WORKDAY"
            raw_ot = max(0, net_working_minutes - sched_net)

        if overtime_rule is not None:
            if ot_category == "HOLIDAY":
                mult = Decimal(str(overtime_rule.holiday_multiplier))
            elif ot_category == "WEEK_OFF":
                mult = Decimal(str(overtime_rule.weekend_multiplier))
            else:
                mult = Decimal(str(overtime_rule.workday_multiplier))

            if raw_ot < overtime_rule.min_overtime_threshold_minutes:
                eligible_ot = 0
            else:
                eligible_ot = raw_ot
                if (
                    overtime_rule.max_daily_overtime_minutes is not None
                    and eligible_ot > overtime_rule.max_daily_overtime_minutes
                ):
                    eligible_ot = overtime_rule.max_daily_overtime_minutes

            payable_ot = int(round(Decimal(eligible_ot) * mult))
            requires_appr = bool(
                overtime_rule.requires_manager_approval or overtime_rule.requires_pre_approval
            )
            ot_status = "PENDING_APPROVAL" if requires_appr else "AUTO_APPROVED"
            overtime_minutes = eligible_ot

            ot_details = OvertimeCalculationDetails(
                raw_overtime_minutes=raw_ot,
                eligible_overtime_minutes=eligible_ot,
                multiplier=mult,
                payable_overtime_minutes=payable_ot,
                overtime_type=ot_category,
                requires_approval=requires_appr,
                status=ot_status,
                rule_id=getattr(overtime_rule, "id", None),
            )
        else:
            # Legacy fallback if no overtime_rule provided
            if ot_category == "WORKDAY":
                overtime_minutes = raw_ot
            else:
                overtime_minutes = raw_ot

    # C. Status Determination
    if has_punches:
        calc_status = "CALCULATED"
        if resolved_timeline.has_suspicious_events:
            status = "PENDING_REVIEW"
            calc_status = "FLAGGED"
        elif is_incomplete:
            status = "INCOMPLETE"
            calc_status = "INCOMPLETE"
        elif is_on_leave and not is_half_day_leave:
            status = "ON_LEAVE"
        elif is_holiday or is_weekly_off:
            # Working on rest day or holiday confers presence
            status = "PRESENT"
        elif net_working_minutes >= shift_version.full_day_threshold_minutes:
            if late_arrival_minutes > 0:
                status = "LATE"
            else:
                status = "PRESENT"
        elif net_working_minutes >= shift_version.half_day_threshold_minutes:
            status = "HALF_DAY"
        else:
            status = "ABSENT"
    else:
        # No punches recorded
        calc_status = "CALCULATED"
        if is_on_leave:
            status = "ON_LEAVE"
        elif is_holiday:
            status = "HOLIDAY"
        elif is_weekly_off:
            status = "WEEK_OFF"
        elif now_dt <= window_end_utc:
            # Shift completion window has not yet elapsed: do not mark absent prematurely
            status = "INCOMPLETE"
            calc_status = "INCOMPLETE"
        else:
            status = "ABSENT"

    metadata: dict[str, Any] = {
        "is_overnight": shift_version.is_overnight,
        "is_weekly_off": is_weekly_off,
        "is_holiday": is_holiday,
        "is_on_leave": is_on_leave,
        "leave_type_code": leave_type_code,
        "is_half_day_leave": is_half_day_leave,
        "half_day_period": half_day_period,
        "scheduled_start_utc": sched_start_utc.isoformat(),
        "scheduled_end_utc": sched_end_utc.isoformat(),
        "window_start_utc": window_start_utc.isoformat(),
        "window_end_utc": window_end_utc.isoformat(),
        "anomalies": resolved_timeline.anomalies,
        "has_suspicious_events": resolved_timeline.has_suspicious_events,
    }
    if ot_details:
        metadata["overtime"] = {
            "raw_overtime_minutes": ot_details.raw_overtime_minutes,
            "eligible_overtime_minutes": ot_details.eligible_overtime_minutes,
            "multiplier": float(ot_details.multiplier),
            "payable_overtime_minutes": ot_details.payable_overtime_minutes,
            "overtime_type": ot_details.overtime_type,
            "status": ot_details.status,
            "requires_approval": ot_details.requires_approval,
        }

    return AttendanceDayCalculationResult(
        attendance_date=target_date,
        shift_template_id=shift_version.shift_template_id,
        shift_version_id=shift_version.id,
        first_check_in=first_in,
        last_check_out=last_out,
        total_working_minutes=total_working_minutes,
        total_break_minutes=total_break_minutes,
        net_working_minutes=net_working_minutes,
        actual_late_minutes=actual_late_minutes,
        late_arrival_minutes=late_arrival_minutes,
        actual_early_minutes=actual_early_minutes,
        early_departure_minutes=early_departure_minutes,
        overtime_minutes=overtime_minutes,
        status=status,
        calculation_status=calc_status,
        is_incomplete=is_incomplete,
        missing_punch=missing_punch,
        source_event_ids=resolved_timeline.source_event_ids,
        metadata=metadata,
        overtime_details=ot_details,
    )
