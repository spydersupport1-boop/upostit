"""Domain exceptions for Phase 10 Notifications."""


class NotificationException(Exception):
    """Base exception for all notification engine operations."""

    def __init__(self, message: str, code: str = "NOTIFICATION_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class TemplateNotFoundError(NotificationException):
    """Raised when an active template matching key, channel, and locale cannot be found."""

    def __init__(self, template_key: str, channel: str, locale: str = "en") -> None:
        super().__init__(
            f"Notification template '{template_key}' for channel '{channel}' and locale '{locale}' not found",
            code="TEMPLATE_NOT_FOUND",
        )
        self.template_key = template_key
        self.channel = channel
        self.locale = locale


class TemplateRenderError(NotificationException):
    """Raised when template variable interpolation fails or required variables are missing."""

    def __init__(self, message: str, missing_variable: str | None = None) -> None:
        super().__init__(message, code="TEMPLATE_RENDER_ERROR")
        self.missing_variable = missing_variable


class RecipientNotFoundError(NotificationException):
    """Raised when recipient user/employee or destination address cannot be resolved."""

    def __init__(self, message: str = "Recipient or destination address not found") -> None:
        super().__init__(message, code="RECIPIENT_NOT_FOUND")


class ChannelDisabledError(NotificationException):
    """Raised when the requested notification channel is disabled by preference."""

    def __init__(self, channel: str, reason: str = "Channel disabled by user or tenant preference") -> None:
        super().__init__(f"Notification channel '{channel}' is disabled: {reason}", code="CHANNEL_DISABLED")
        self.channel = channel
        self.reason = reason


class QuietHoursDeferredError(NotificationException):
    """Raised when notification delivery is deferred to a future time due to active quiet hours."""

    def __init__(self, next_eligible_at: str) -> None:
        super().__init__(
            f"Notification deferred due to active quiet hours; next eligible dispatch: {next_eligible_at}",
            code="QUIET_HOURS_DEFERRED",
        )
        self.next_eligible_at = next_eligible_at


class DuplicateNotificationError(NotificationException):
    """Raised when a notification with the same idempotency key already exists for the tenant."""

    def __init__(self, idempotency_key: str) -> None:
        super().__init__(
            f"Notification with idempotency key '{idempotency_key}' already exists",
            code="DUPLICATE_NOTIFICATION",
        )
        self.idempotency_key = idempotency_key


class InvalidStateTransitionError(NotificationException):
    """Raised when attempting an invalid or illegal state transition in the notification lifecycle."""

    def __init__(self, from_status: str, to_status: str) -> None:
        super().__init__(
            f"Cannot transition notification status from '{from_status}' to '{to_status}'",
            code="INVALID_STATE_TRANSITION",
        )
        self.from_status = from_status
        self.to_status = to_status


class ProviderError(NotificationException):
    """Base exception for provider communication failures."""

    def __init__(
        self,
        message: str,
        provider_name: str,
        is_retryable: bool = False,
        raw_error: str | None = None,
    ) -> None:
        super().__init__(message, code="PROVIDER_ERROR")
        self.provider_name = provider_name
        self.is_retryable = is_retryable
        self.raw_error = raw_error


class ProviderTimeoutError(ProviderError):
    """Raised when a downstream notification provider times out."""

    def __init__(self, provider_name: str, message: str = "Provider dispatch request timed out") -> None:
        super().__init__(message, provider_name=provider_name, is_retryable=True)


class ProviderPermanentError(ProviderError):
    """Raised when a downstream provider rejects the dispatch with an unretryable error."""

    def __init__(self, provider_name: str, message: str) -> None:
        super().__init__(message, provider_name=provider_name, is_retryable=False)


class ProviderRetryableError(ProviderError):
    """Raised when a downstream provider fails with a transient, retryable error."""

    def __init__(self, provider_name: str, message: str) -> None:
        super().__init__(message, provider_name=provider_name, is_retryable=True)

