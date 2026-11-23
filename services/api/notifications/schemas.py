"""Pydantic schemas and enums for Phase 10 Notifications."""

import re
import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NotificationChannel(StrEnum):
    """Supported delivery channels."""

    PUSH = "PUSH"
    EMAIL = "EMAIL"
    SMS = "SMS"


class NotificationStatus(StrEnum):
    """Lifecycle status of a notification dispatch request."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class NotificationPriority(StrEnum):
    """Priority levels for dispatch scheduling."""

    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


class DevicePlatform(StrEnum):
    """Mobile or web push device platform."""

    ANDROID = "ANDROID"
    IOS = "IOS"
    WEB = "WEB"


class DeviceTokenStatus(StrEnum):
    """Status of registered device push tokens."""

    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class ProviderStatus(StrEnum):
    """Provider-level acknowledgment outcome."""

    ACCEPTED = "ACCEPTED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class NotificationEventType(StrEnum):
    """Approved domain event types for outbound notifications."""

    # Phase 9 — Leave
    LEAVE_REQUEST_SUBMITTED = "leave_request_submitted"
    LEAVE_REQUEST_APPROVED = "leave_request_approved"
    LEAVE_REQUEST_REJECTED = "leave_request_rejected"
    LEAVE_REQUEST_CANCELLED = "leave_request_cancelled"

    # Phase 8 — Attendance Conflicts
    OFFLINE_CONFLICT_SUBMITTED = "offline_conflict_submitted"
    ATTENDANCE_CONFLICT_APPROVED = "attendance_conflict_approved"
    ATTENDANCE_CONFLICT_REJECTED = "attendance_conflict_rejected"

    # Phase 7 — Fraud Shield
    HIGH_RISK_FRAUD_ALERT = "high_risk_fraud_alert"
    IMPOSSIBLE_TRAVEL_SIGNAL = "impossible_travel_signal"
    MOCK_GPS_DETECTED = "mock_gps_detected"

    # Phase 4 — Employee Invitations
    EMPLOYEE_INVITATION_CREATED = "employee_invitation_created"
    EMPLOYEE_INVITATION_SENT = "employee_invitation_sent"

    # Phase 2 — Password Resets
    PASSWORD_RESET_REQUESTED = "password_reset_requested"


# Regex for "HH:MM" 24-hour time validation
_TIME_24H_REGEX = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_SUSPICIOUS_EXPRESSION_REGEX = re.compile(
    r"\{\{[\s\S]*?__[\s\S]*?\}\}|\{[\s\S]*?__[\s\S]*?\}|import|eval|exec|compile|os\.|sys\."
)


class NotificationCreateRequest(BaseModel):
    """Request schema for creating an outbound notification."""

    recipient_user_id: uuid.UUID | None = None
    recipient_employee_id: uuid.UUID | None = None
    recipient_destination: str | None = None  # Direct email, phone, or FCM token if pre-resolved
    event_type: str = Field(..., min_length=1, max_length=100)
    channel: NotificationChannel
    template_key: str = Field(..., min_length=1, max_length=100)
    template_variables: dict[str, Any] = Field(default_factory=dict)
    priority: NotificationPriority = NotificationPriority.NORMAL
    idempotency_key: str | None = Field(default=None, max_length=128)
    scheduled_for: datetime | None = None
    related_entity_type: str | None = Field(default=None, max_length=50)
    related_entity_id: uuid.UUID | None = None
    locale: str = Field(default="en", max_length=10)

    model_config = ConfigDict(extra="forbid")

    @field_validator("idempotency_key")
    @classmethod
    def clean_idempotency_key(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            return None
        return v.strip() if v else None


class NotificationBatchCreateRequest(BaseModel):
    """Batch notification creation request."""

    notifications: list[NotificationCreateRequest] = Field(..., min_length=1, max_length=100)


class TemplateCreateRequest(BaseModel):
    """Request schema for creating or overriding a notification template."""

    template_key: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=150)
    description: str | None = None
    event_type: str = Field(..., min_length=1, max_length=100)
    channel: NotificationChannel
    subject_template: str | None = Field(default=None, max_length=255)
    body_template: str = Field(..., min_length=1)
    locale: str = Field(default="en", max_length=10)
    is_active: bool = True

    model_config = ConfigDict(extra="forbid")

    @field_validator("body_template", "subject_template")
    @classmethod
    def validate_safe_template(cls, v: str | None) -> str | None:
        if v is not None and _SUSPICIOUS_EXPRESSION_REGEX.search(v):
            raise ValueError("Template contains prohibited expressions, dunder attributes, or unsafe keywords.")
        return v


class PreferenceUpdateRequest(BaseModel):
    """Request schema for updating tenant-default or user-level notification preferences."""

    is_push_enabled: bool | None = None
    is_email_enabled: bool | None = None
    is_sms_enabled: bool | None = None
    quiet_hours_enabled: bool | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    timezone: str | None = None
    category_preferences: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("quiet_hours_start", "quiet_hours_end")
    @classmethod
    def validate_time_format(cls, v: str | None) -> str | None:
        if v is not None and not _TIME_24H_REGEX.match(v):
            raise ValueError("Time must be in 24-hour 'HH:MM' format (e.g. '22:00', '07:30')")
        return v

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str | None) -> str | None:
        if v is not None:
            clean = v.strip()
            if len(clean) > 50:
                raise ValueError("Timezone identifier cannot exceed 50 characters")
        return v


class DeviceTokenRegisterRequest(BaseModel):
    """Request schema for registering an FCM push token."""

    platform: DevicePlatform
    token: str = Field(..., min_length=10, max_length=512)
    device_model: str | None = Field(default=None, max_length=100)
    os_version: str | None = Field(default=None, max_length=50)
    app_version: str | None = Field(default=None, max_length=50)

    model_config = ConfigDict(extra="forbid")


class ProviderResult(BaseModel):
    """Normalized result returned by a notification provider."""

    success: bool
    status: ProviderStatus
    provider_name: str
    provider_message_id: str | None = None
    is_retryable: bool = False
    error_message: str | None = None
    raw_response: dict[str, Any] | None = None

    model_config = ConfigDict(extra="ignore")


class NotificationResponse(BaseModel):
    """Pydantic representation of a persisted notification."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    recipient_user_id: uuid.UUID | None = None
    recipient_employee_id: uuid.UUID | None = None
    event_type: str
    channel: str
    template_key: str | None = None
    recipient_destination: str
    subject: str | None = None
    body: str
    payload_json: dict[str, Any] | None = None
    status: str
    priority: str
    scheduled_for: datetime
    attempt_count: int
    max_attempts: int
    next_retry_at: datetime | None = None
    provider_name: str | None = None
    provider_message_id: str | None = None
    error_message: str | None = None
    idempotency_key: str | None = None
    related_entity_type: str | None = None
    related_entity_id: uuid.UUID | None = None
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    failed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationPreferenceResponse(BaseModel):
    """Pydantic representation of user or tenant notification preferences."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID | None = None
    is_push_enabled: bool
    is_email_enabled: bool
    is_sms_enabled: bool
    quiet_hours_enabled: bool
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    timezone: str
    category_preferences: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationTemplateResponse(BaseModel):
    """Pydantic representation of a notification template."""

    id: uuid.UUID
    tenant_id: uuid.UUID | None = None
    template_key: str
    name: str
    description: str | None = None
    event_type: str
    channel: str
    subject_template: str | None = None
    body_template: str
    locale: str
    is_active: bool
    is_system: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DevicePushTokenResponse(BaseModel):
    """Safe Pydantic representation of a registered device token (raw token masked)."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    employee_id: uuid.UUID | None = None
    platform: str
    token_preview: str
    device_model: str | None = None
    os_version: str | None = None
    app_version: str | None = None
    status: str
    last_seen_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DispatchResult(BaseModel):
    """Summary of a dispatch attempt executed by the dispatcher."""

    notification_id: uuid.UUID
    status: NotificationStatus
    provider_name: str | None = None
    provider_message_id: str | None = None
    attempt_count: int
    is_deferred: bool = False
    next_eligible_at: datetime | None = None
    error_message: str | None = None


class TemplateUpdateRequest(BaseModel):
    """Request schema for updating an existing template."""

    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None
    subject_template: str | None = Field(default=None, max_length=255)
    body_template: str | None = Field(default=None, min_length=1)
    is_active: bool | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("body_template", "subject_template")
    @classmethod
    def validate_safe_template(cls, v: str | None) -> str | None:
        if v is not None and _SUSPICIOUS_EXPRESSION_REGEX.search(v):
            raise ValueError("Template contains prohibited expressions, dunder attributes, or unsafe keywords.")
        return v


class NotificationOverviewResponse(BaseModel):
    """Aggregate metrics and recent activity for the notification administration console."""

    total_count: int
    status_counts: dict[str, int]
    channel_counts: dict[str, int]
    recent_notifications: list[NotificationResponse]
    delivery_distinction_note: str = (
        "SENT indicates that the notification was accepted by the downstream provider (e.g. FCM, SMTP). "
        "DELIVERED indicates verified receipt confirmation by the destination device or service."
    )

    model_config = ConfigDict(from_attributes=True)


class ChannelConfigItem(BaseModel):
    """Runtime configuration status of an outbound delivery channel."""

    channel: NotificationChannel
    is_enabled: bool
    provider_name: str
    status: str  # "CONFIGURED" | "MOCK" | "UNCONFIGURED"
    description: str
    details: dict[str, Any] = Field(default_factory=dict)


class ChannelListResponse(BaseModel):
    """List of all delivery channels and their configuration states."""

    channels: list[ChannelConfigItem]


class NotificationListResponse(BaseModel):
    """Paginated list of notifications."""

    items: list[NotificationResponse]
    total: int
    offset: int
    limit: int


class TemplateListResponse(BaseModel):
    """List of notification templates."""

    items: list[NotificationTemplateResponse]
    total: int

