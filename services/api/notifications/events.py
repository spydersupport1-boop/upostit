"""Typed domain event schemas for Phase 10 Notification Triggers.

Defines all 13 approved business domain events across UPOSTIT business domains:
- Phase 9 Leave: submitted, approved, rejected, cancelled
- Phase 8 Conflicts: submitted, approved, rejected
- Phase 7 Fraud Shield: high-risk fraud alert, impossible travel signal, mock GPS detected
- Phase 4 Invitations: created, sent
- Phase 2 Password Resets: requested

Invariants:
- Tenant isolation: every event strictly carries tenant_id.
- Correlation tracking: includes event_id, occurred_at, and optional correlation_id.
- Security & privacy: zero sensitive credentials, private tokens, or unredacted sensor telemetry.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from services.api.notifications.schemas import NotificationEventType


class DomainEvent(BaseModel):
    """Base model for all tenant-scoped business domain events."""

    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    event_type: NotificationEventType
    tenant_id: uuid.UUID
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    correlation_id: str | None = None
    actor_user_id: uuid.UUID | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


# =============================================================================
# Phase 9 — Leave Domain Events
# =============================================================================


class LeaveRequestSubmittedEvent(DomainEvent):
    """Fired when an employee submits a leave request requiring supervisor review."""

    event_type: NotificationEventType = NotificationEventType.LEAVE_REQUEST_SUBMITTED
    leave_request_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    leave_type: str
    start_date: date
    end_date: date
    total_days: Decimal | float
    reason: str
    supervisor_id: uuid.UUID | None = None


class LeaveRequestApprovedEvent(DomainEvent):
    """Fired when a supervisor approves an employee's leave request."""

    event_type: NotificationEventType = NotificationEventType.LEAVE_REQUEST_APPROVED
    leave_request_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    leave_type: str
    start_date: date
    end_date: date
    supervisor_comment: str | None = None


class LeaveRequestRejectedEvent(DomainEvent):
    """Fired when a supervisor rejects an employee's leave request."""

    event_type: NotificationEventType = NotificationEventType.LEAVE_REQUEST_REJECTED
    leave_request_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    leave_type: str
    start_date: date
    end_date: date
    rejection_reason: str | None = None


class LeaveRequestCancelledEvent(DomainEvent):
    """Fired when an employee cancels a pending leave request."""

    event_type: NotificationEventType = NotificationEventType.LEAVE_REQUEST_CANCELLED
    leave_request_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    leave_type: str
    start_date: date
    end_date: date
    cancellation_reason: str | None = None
    supervisor_id: uuid.UUID | None = None


# =============================================================================
# Phase 8 — Attendance Conflict Domain Events
# =============================================================================


class OfflineConflictSubmittedEvent(DomainEvent):
    """Fired when an offline attendance conflict bundle is submitted for supervisor review."""

    event_type: NotificationEventType = NotificationEventType.OFFLINE_CONFLICT_SUBMITTED
    incident_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    bundle_id: str
    conflict_count: int
    reason: str | None = None
    assigned_reviewer_id: uuid.UUID | None = None


class AttendanceConflictApprovedEvent(DomainEvent):
    """Fired when a reviewer approves an attendance conflict incident."""

    event_type: NotificationEventType = NotificationEventType.ATTENDANCE_CONFLICT_APPROVED
    incident_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    reviewer_user_id: uuid.UUID
    adjudication_comment: str | None = None


class AttendanceConflictRejectedEvent(DomainEvent):
    """Fired when a reviewer rejects an attendance conflict incident."""

    event_type: NotificationEventType = NotificationEventType.ATTENDANCE_CONFLICT_REJECTED
    incident_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    reviewer_user_id: uuid.UUID
    rejection_reason: str | None = None


# =============================================================================
# Phase 7 — Fraud Shield Domain Events
# =============================================================================


class HighRiskFraudAlertEvent(DomainEvent):
    """Fired when an attendance punch receives high or critical fraud risk scoring."""

    event_type: NotificationEventType = NotificationEventType.HIGH_RISK_FRAUD_ALERT
    attendance_event_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    risk_score: int
    risk_category: str
    attendance_event_type: str
    flag_summary: str


class ImpossibleTravelSignalEvent(DomainEvent):
    """Fired when impossible travel velocity between consecutive punches is detected."""

    event_type: NotificationEventType = NotificationEventType.IMPOSSIBLE_TRAVEL_SIGNAL
    attendance_event_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    velocity_mps: float
    distance_km: float
    elapsed_seconds: float


class MockGpsDetectedEvent(DomainEvent):
    """Fired when mock location spoofing or fake GPS provider is detected on device."""

    event_type: NotificationEventType = NotificationEventType.MOCK_GPS_DETECTED
    attendance_event_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    device_id: str | None = None
    location_summary: str


# =============================================================================
# Phase 4 — Employee Invitation Domain Events
# =============================================================================


class EmployeeInvitationCreatedEvent(DomainEvent):
    """Fired when an employee invitation record is created."""

    event_type: NotificationEventType = NotificationEventType.EMPLOYEE_INVITATION_CREATED
    invitation_id: uuid.UUID
    employee_id: uuid.UUID
    recipient_email: str
    recipient_name: str
    company_name: str
    activation_url: str
    expires_hours: int


class EmployeeInvitationSentEvent(DomainEvent):
    """Fired when an employee invitation is dispatched or re-sent."""

    event_type: NotificationEventType = NotificationEventType.EMPLOYEE_INVITATION_SENT
    invitation_id: uuid.UUID
    employee_id: uuid.UUID
    recipient_email: str
    recipient_name: str
    company_name: str
    activation_url: str
    expires_hours: int


# =============================================================================
# Phase 2 — Password Reset Domain Events
# =============================================================================


class PasswordResetRequestedEvent(DomainEvent):
    """Fired when a password reset is requested for an active account owner."""

    event_type: NotificationEventType = NotificationEventType.PASSWORD_RESET_REQUESTED
    user_id: uuid.UUID
    user_email: str
    user_name: str
    company_name: str
    reset_url: str
    expires_minutes: int = 30
