"""Phase 10 Notifications: Core Outbound Dispatch Engine, Repository & Provider Abstraction."""

from services.api.notifications.crypto import (
    EncryptionConfigError,
    TokenEncryptionError,
    decrypt_push_token,
    encrypt_push_token,
    get_fernet_suite,
    hash_push_token,
    mask_token_for_display,
)
from services.api.notifications.crypto import (
    decrypt_push_token as decrypt_token_at_rest,
)
from services.api.notifications.crypto import (
    encrypt_push_token as encrypt_token_at_rest,
)
from services.api.notifications.default_templates import (
    SYSTEM_DEFAULT_TEMPLATES,
    get_default_system_template,
)
from services.api.notifications.dispatcher import (
    NotificationDispatcher,
    calculate_exponential_backoff,
)
from services.api.notifications.event_handler import (
    DomainNotificationHandler,
    dispatch_domain_event,
    enqueue_celery_dispatch,
)
from services.api.notifications.events import (
    AttendanceConflictApprovedEvent,
    AttendanceConflictRejectedEvent,
    DomainEvent,
    EmployeeInvitationCreatedEvent,
    EmployeeInvitationSentEvent,
    HighRiskFraudAlertEvent,
    ImpossibleTravelSignalEvent,
    LeaveRequestApprovedEvent,
    LeaveRequestCancelledEvent,
    LeaveRequestRejectedEvent,
    LeaveRequestSubmittedEvent,
    MockGpsDetectedEvent,
    OfflineConflictSubmittedEvent,
    PasswordResetRequestedEvent,
)
from services.api.notifications.exceptions import (
    ChannelDisabledError,
    DuplicateNotificationError,
    InvalidStateTransitionError,
    NotificationException,
    ProviderError,
    ProviderPermanentError,
    ProviderRetryableError,
    ProviderTimeoutError,
    QuietHoursDeferredError,
    RecipientNotFoundError,
    TemplateNotFoundError,
    TemplateRenderError,
)
from services.api.notifications.fcm_provider import FirebasePushProvider
from services.api.notifications.models import (
    DevicePushToken,
    Notification,
    NotificationPreference,
    NotificationTemplate,
)
from services.api.notifications.preference_resolver import (
    EffectivePreferences,
    PreferenceResolver,
)
from services.api.notifications.provider import (
    BaseNotificationProvider,
    MockEmailProvider,
    MockPushProvider,
    MockSmsProvider,
    ProviderRegistry,
)
from services.api.notifications.quiet_hours import (
    QuietHoursEvaluationResult,
    QuietHoursEvaluator,
)
from services.api.notifications.repository import NotificationRepository
from services.api.notifications.routes import router as notifications_router
from services.api.notifications.schemas import (
    DevicePlatform,
    DevicePushTokenResponse,
    DeviceTokenRegisterRequest,
    DeviceTokenStatus,
    DispatchResult,
    NotificationBatchCreateRequest,
    NotificationChannel,
    NotificationCreateRequest,
    NotificationEventType,
    NotificationPreferenceResponse,
    NotificationPriority,
    NotificationResponse,
    NotificationStatus,
    NotificationTemplateResponse,
    PreferenceUpdateRequest,
    ProviderResult,
    ProviderStatus,
    TemplateCreateRequest,
)
from services.api.notifications.service import NotificationService
from services.api.notifications.template_renderer import SafeTemplateRenderer

__all__ = [
    # Models
    "DevicePushToken",
    "Notification",
    "NotificationPreference",
    "NotificationTemplate",
    # Exceptions
    "NotificationException",
    "EncryptionConfigError",
    "TokenEncryptionError",
    "TemplateNotFoundError",
    "TemplateRenderError",
    "RecipientNotFoundError",
    "ChannelDisabledError",
    "QuietHoursDeferredError",
    "DuplicateNotificationError",
    "InvalidStateTransitionError",
    "ProviderError",
    "ProviderTimeoutError",
    "ProviderPermanentError",
    "ProviderRetryableError",
    # Enums & Schemas
    "NotificationChannel",
    "NotificationEventType",
    "NotificationStatus",
    "NotificationPriority",
    "DevicePlatform",
    "DeviceTokenStatus",
    "ProviderStatus",
    "NotificationCreateRequest",
    "NotificationBatchCreateRequest",
    "TemplateCreateRequest",
    "PreferenceUpdateRequest",
    "DeviceTokenRegisterRequest",
    "ProviderResult",
    "NotificationResponse",
    "NotificationPreferenceResponse",
    "NotificationTemplateResponse",
    "DevicePushTokenResponse",
    "DispatchResult",
    # Domain Events
    "DomainEvent",
    "LeaveRequestSubmittedEvent",
    "LeaveRequestApprovedEvent",
    "LeaveRequestRejectedEvent",
    "LeaveRequestCancelledEvent",
    "OfflineConflictSubmittedEvent",
    "AttendanceConflictApprovedEvent",
    "AttendanceConflictRejectedEvent",
    "HighRiskFraudAlertEvent",
    "ImpossibleTravelSignalEvent",
    "MockGpsDetectedEvent",
    "EmployeeInvitationCreatedEvent",
    "EmployeeInvitationSentEvent",
    "PasswordResetRequestedEvent",
    # Event Handlers & Templates
    "DomainNotificationHandler",
    "dispatch_domain_event",
    "enqueue_celery_dispatch",
    "SYSTEM_DEFAULT_TEMPLATES",
    "get_default_system_template",
    # Components
    "SafeTemplateRenderer",
    "EffectivePreferences",
    "PreferenceResolver",
    "QuietHoursEvaluationResult",
    "QuietHoursEvaluator",
    "BaseNotificationProvider",
    "FirebasePushProvider",
    "MockPushProvider",
    "MockEmailProvider",
    "MockSmsProvider",
    "ProviderRegistry",
    "hash_push_token",
    "mask_token_for_display",
    "encrypt_token_at_rest",
    "decrypt_token_at_rest",
    "encrypt_push_token",
    "decrypt_push_token",
    "get_fernet_suite",
    "NotificationRepository",
    "NotificationService",
    "NotificationDispatcher",
    "notifications_router",
    "calculate_exponential_backoff",
]
