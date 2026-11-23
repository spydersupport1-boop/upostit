"""Preference resolution engine for user and tenant notification channels."""

from dataclasses import dataclass
from typing import Any

from services.api.notifications.models import NotificationPreference
from services.api.notifications.schemas import NotificationChannel


@dataclass(frozen=True)
class EffectivePreferences:
    """Consolidated preferences resulting from resolving User -> Tenant -> System fallback."""

    is_push_enabled: bool
    is_email_enabled: bool
    is_sms_enabled: bool
    quiet_hours_enabled: bool
    quiet_hours_start: str | None
    quiet_hours_end: str | None
    timezone: str
    category_preferences: dict[str, Any]
    source: str  # "USER_OVERRIDE", "TENANT_DEFAULT", "SYSTEM_DEFAULT"


class PreferenceResolver:
    """Resolves hierarchical notification preferences respecting strict opt-outs."""

    # Approved system defaults when neither user nor tenant preferences exist
    SYSTEM_DEFAULT_PUSH = True
    SYSTEM_DEFAULT_EMAIL = True
    SYSTEM_DEFAULT_SMS = False
    SYSTEM_DEFAULT_QUIET_HOURS = False
    SYSTEM_DEFAULT_TIMEZONE = "UTC"

    @classmethod
    def resolve(
        cls,
        user_preference: NotificationPreference | None,
        tenant_default_preference: NotificationPreference | None,
    ) -> EffectivePreferences:
        """Resolves effective preferences in order: User override -> Tenant default -> System fallback."""
        if user_preference is not None:
            # User has an explicit preference record
            return EffectivePreferences(
                is_push_enabled=user_preference.is_push_enabled,
                is_email_enabled=user_preference.is_email_enabled,
                is_sms_enabled=user_preference.is_sms_enabled,
                quiet_hours_enabled=user_preference.quiet_hours_enabled,
                quiet_hours_start=user_preference.quiet_hours_start,
                quiet_hours_end=user_preference.quiet_hours_end,
                timezone=user_preference.timezone or cls.SYSTEM_DEFAULT_TIMEZONE,
                category_preferences=user_preference.category_preferences or {},
                source="USER_OVERRIDE",
            )

        if tenant_default_preference is not None:
            # Fall back to tenant-level defaults
            return EffectivePreferences(
                is_push_enabled=tenant_default_preference.is_push_enabled,
                is_email_enabled=tenant_default_preference.is_email_enabled,
                is_sms_enabled=tenant_default_preference.is_sms_enabled,
                quiet_hours_enabled=tenant_default_preference.quiet_hours_enabled,
                quiet_hours_start=tenant_default_preference.quiet_hours_start,
                quiet_hours_end=tenant_default_preference.quiet_hours_end,
                timezone=tenant_default_preference.timezone or cls.SYSTEM_DEFAULT_TIMEZONE,
                category_preferences=tenant_default_preference.category_preferences or {},
                source="TENANT_DEFAULT",
            )

        # Fall back to system defaults
        return EffectivePreferences(
            is_push_enabled=cls.SYSTEM_DEFAULT_PUSH,
            is_email_enabled=cls.SYSTEM_DEFAULT_EMAIL,
            is_sms_enabled=cls.SYSTEM_DEFAULT_SMS,
            quiet_hours_enabled=cls.SYSTEM_DEFAULT_QUIET_HOURS,
            quiet_hours_start=None,
            quiet_hours_end=None,
            timezone=cls.SYSTEM_DEFAULT_TIMEZONE,
            category_preferences={},
            source="SYSTEM_DEFAULT",
        )

    @classmethod
    def is_channel_allowed(
        cls,
        channel: NotificationChannel | str,
        user_preference: NotificationPreference | None,
        tenant_default_preference: NotificationPreference | None,
    ) -> tuple[bool, str | None]:
        """Determines whether a channel is permitted, returning (is_allowed, skip_reason).

        Args:
            channel: The requested channel (PUSH, EMAIL, SMS).
            user_preference: User preference record if present.
            tenant_default_preference: Tenant default preference record if present.

        Returns:
            Tuple of (bool, str | None). If False, skip_reason provides audit explanation.
        """
        ch_str = channel.value if isinstance(channel, NotificationChannel) else str(channel).upper()
        effective = cls.resolve(user_preference, tenant_default_preference)

        if ch_str == "PUSH":
            if not effective.is_push_enabled:
                reason = "OPT_OUT_USER" if effective.source == "USER_OVERRIDE" else "DISABLED_TENANT_POLICY"
                return False, f"Push channel disabled ({reason})"
            return True, None

        elif ch_str == "EMAIL":
            if not effective.is_email_enabled:
                reason = "OPT_OUT_USER" if effective.source == "USER_OVERRIDE" else "DISABLED_TENANT_POLICY"
                return False, f"Email channel disabled ({reason})"
            return True, None

        elif ch_str == "SMS":
            if not effective.is_sms_enabled:
                reason = "OPT_OUT_USER" if effective.source == "USER_OVERRIDE" else "DISABLED_TENANT_POLICY"
                return False, f"SMS channel disabled ({reason})"
            return True, None

        return False, f"Unsupported channel '{ch_str}'"

