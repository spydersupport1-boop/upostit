"""Quiet-hours evaluation engine supporting timezones, daylight-saving, and overnight intervals."""

import zoneinfo
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

from services.api.notifications.preference_resolver import EffectivePreferences
from services.api.notifications.schemas import NotificationPriority


@dataclass(frozen=True)
class QuietHoursEvaluationResult:
    """Outcome of quiet-hours evaluation for a notification."""

    is_in_quiet_hours: bool
    should_defer: bool
    next_eligible_dispatch_time: datetime | None
    current_local_time: datetime
    timezone: str
    reason: str | None = None


class QuietHoursEvaluator:
    """Evaluates whether notification dispatch should be deferred due to quiet hours."""

    @classmethod
    def get_timezone(cls, tz_name: str | None) -> zoneinfo.ZoneInfo:
        """Safely parses a timezone name, falling back to UTC if invalid or missing."""
        if not tz_name:
            return zoneinfo.ZoneInfo("UTC")
        try:
            return zoneinfo.ZoneInfo(tz_name.strip())
        except (zoneinfo.ZoneInfoNotFoundError, ValueError):
            return zoneinfo.ZoneInfo("UTC")

    @classmethod
    def evaluate(
        cls,
        preferences: EffectivePreferences,
        priority: NotificationPriority | str = NotificationPriority.NORMAL,
        *,
        evaluation_time_utc: datetime | None = None,
    ) -> QuietHoursEvaluationResult:
        """Evaluates quiet hours against effective preferences.

        All notifications strictly respect recipient quiet-hours preferences without
        unconditional bypass, per Phase 10 roadmap rules.

        Args:
            preferences: Effective resolved preferences containing quiet hours and timezone.
            priority: Priority level of the notification (retained for signature compatibility).
            evaluation_time_utc: Optional evaluation timestamp (defaults to current UTC time).

        Returns:
            QuietHoursEvaluationResult indicating whether to defer and the next eligible dispatch time.
        """
        now_utc = evaluation_time_utc or datetime.now(UTC)
        if now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=UTC)

        tz = cls.get_timezone(preferences.timezone)
        now_local = now_utc.astimezone(tz)

        # If quiet hours are disabled or unconfigured, dispatch immediately
        if (
            not preferences.quiet_hours_enabled
            or not preferences.quiet_hours_start
            or not preferences.quiet_hours_end
        ):
            return QuietHoursEvaluationResult(
                is_in_quiet_hours=False,
                should_defer=False,
                next_eligible_dispatch_time=None,
                current_local_time=now_local,
                timezone=str(tz),
                reason=None,
            )

        try:
            start_h, start_m = map(int, preferences.quiet_hours_start.split(":"))
            end_h, end_m = map(int, preferences.quiet_hours_end.split(":"))
            start_time = time(start_h, start_m)
            end_time = time(end_h, end_m)
        except (ValueError, AttributeError):
            # Invalid time format, default to immediate dispatch to avoid dropping alerts
            return QuietHoursEvaluationResult(
                is_in_quiet_hours=False,
                should_defer=False,
                next_eligible_dispatch_time=None,
                current_local_time=now_local,
                timezone=str(tz),
                reason="Invalid quiet-hours time format, skipped deferral",
            )

        current_time = now_local.time()
        is_quiet = False
        next_end_local: datetime | None = None

        if start_time < end_time:
            # Daytime/intraday interval (e.g. 13:00 to 15:00)
            if start_time <= current_time < end_time:
                is_quiet = True
                next_end_local = now_local.replace(
                    hour=end_h, minute=end_m, second=0, microsecond=0
                )
        elif start_time > end_time:
            # Overnight interval crossing midnight (e.g. 22:00 to 07:00)
            if current_time >= start_time:
                # Started today before midnight, ends tomorrow morning
                is_quiet = True
                tomorrow = now_local + timedelta(days=1)
                next_end_local = tomorrow.replace(
                    hour=end_h, minute=end_m, second=0, microsecond=0
                )
            elif current_time < end_time:
                # Continued past midnight, ends today morning
                is_quiet = True
                next_end_local = now_local.replace(
                    hour=end_h, minute=end_m, second=0, microsecond=0
                )
        else:
            # start_time == end_time (0 duration)
            is_quiet = False

        if not is_quiet or next_end_local is None:
            return QuietHoursEvaluationResult(
                is_in_quiet_hours=False,
                should_defer=False,
                next_eligible_dispatch_time=None,
                current_local_time=now_local,
                timezone=str(tz),
                reason=None,
            )

        # Convert calculated local end time to UTC
        next_eligible_utc = next_end_local.astimezone(UTC)

        return QuietHoursEvaluationResult(
            is_in_quiet_hours=True,
            should_defer=True,
            next_eligible_dispatch_time=next_eligible_utc,
            current_local_time=now_local,
            timezone=str(tz),
            reason=f"Quiet hours active until {preferences.quiet_hours_end} {tz}",
        )

