"""Domain Notification Event Handler: maps business domain events to transactional notifications.

Implements the Transactional Outbox Pattern:
- Persists Notification records with status PENDING within the calling business transaction.
- Generates deterministic idempotency keys: {event_type}:{entity_id}:{recipient}:{channel}.
- Resolves recipients strictly within tenant boundaries (Supervisors, Employees, HR Admins).
- Enforces user channel preferences and tenant defaults via PreferenceResolver.
- Evaluates quiet hours via QuietHoursEvaluator, scheduling deferred dispatch when active.
- Provides post-commit Celery task enqueue helper with zero-loss fallback to batch poller.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.auth.models import User
from services.api.employees.models import Employee
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
from services.api.notifications.preference_resolver import PreferenceResolver
from services.api.notifications.repository import NotificationRepository
from services.api.notifications.schemas import (
    NotificationChannel,
    NotificationCreateRequest,
    NotificationEventType,
    NotificationPriority,
    NotificationResponse,
)
from services.api.notifications.service import NotificationService

logger = logging.getLogger(__name__)


class DomainNotificationHandler:
    """Orchestrates recipient resolution, preference filtering, and notification creation for domain events."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = NotificationRepository(session)
        self.notification_service = NotificationService(session)

    # =========================================================================
    # 1. Recipient Resolution Helpers (Tenant Scoped)
    # =========================================================================

    async def _resolve_supervisor(
        self,
        tenant_id: uuid.UUID,
        employee_id: uuid.UUID,
        explicit_supervisor_id: uuid.UUID | None = None,
    ) -> tuple[uuid.UUID | None, str | None]:
        """Resolves supervisor user ID and email from employee reporting hierarchy or explicit supervisor."""
        target_manager_id = explicit_supervisor_id

        if not target_manager_id:
            emp_stmt = select(Employee.reporting_manager_id).where(
                Employee.id == employee_id,
                Employee.tenant_id == tenant_id,
            )
            target_manager_id = (await self.session.execute(emp_stmt)).scalar_one_or_none()

        if target_manager_id:
            mgr_stmt = select(Employee.user_id, Employee.work_email).where(
                Employee.id == target_manager_id,
                Employee.tenant_id == tenant_id,
            )
            row = (await self.session.execute(mgr_stmt)).first()
            if row and row[0]:
                return row[0], row[1]

        # Fallback to tenant owner / admin
        admin_stmt = (
            select(User.id, User.email)
            .where(
                User.tenant_id == tenant_id,
                User.role.in_(["owner", "admin"]),
                User.status == "active",
            )
            .limit(1)
        )
        admin_row = (await self.session.execute(admin_stmt)).first()
        if admin_row:
            return admin_row[0], admin_row[1]
        return None, None

    async def _resolve_employee_user_id(
        self,
        tenant_id: uuid.UUID,
        employee_id: uuid.UUID,
    ) -> tuple[uuid.UUID | None, str | None]:
        """Resolves user_id and work_email for an employee."""
        emp_stmt = select(Employee.user_id, Employee.work_email).where(
            Employee.id == employee_id,
            Employee.tenant_id == tenant_id,
        )
        row = (await self.session.execute(emp_stmt)).first()
        if row:
            return row[0], row[1]
        return None, None

    async def _resolve_tenant_admins(
        self,
        tenant_id: uuid.UUID,
    ) -> list[tuple[uuid.UUID, str]]:
        """Queries active security / tenant admins for urgent fraud alerts."""
        admin_stmt = select(User.id, User.email).where(
            User.tenant_id == tenant_id,
            User.role.in_(["owner", "admin"]),
            User.status == "active",
        )
        rows = (await self.session.execute(admin_stmt)).all()
        return [(r[0], r[1]) for r in rows]

    # =========================================================================
    # 2. Main Event Dispatch Handler
    # =========================================================================

    async def handle_event(self, event: DomainEvent) -> list[NotificationResponse]:
        """Processes a domain event and creates transactional outbox notifications.

        Args:
            event: Typed DomainEvent subclass.

        Returns:
            List of created NotificationResponse objects.
        """
        tenant_id = event.tenant_id
        notifications: list[NotificationResponse] = []

        # Load tenant defaults for preference checking
        tenant_pref = await self.repository.get_tenant_default_preference(tenant_id)

        # ---------------------------------------------------------------------
        # A. Phase 9 Leave Events
        # ---------------------------------------------------------------------
        if isinstance(event, LeaveRequestSubmittedEvent):
            sup_user_id, sup_email = await self._resolve_supervisor(
                tenant_id, event.employee_id, event.supervisor_id
            )
            if sup_user_id:
                sup_pref = await self.repository.get_user_preference(tenant_id, sup_user_id)
                variables = {
                    "employee_name": event.employee_name,
                    "leave_type": event.leave_type,
                    "start_date": event.start_date.isoformat(),
                    "end_date": event.end_date.isoformat(),
                    "duration_days": str(event.total_days),
                    "reason": event.reason or "No reason provided",
                }
                for ch in [NotificationChannel.EMAIL, NotificationChannel.PUSH]:
                    allowed, skip_reason = PreferenceResolver.is_channel_allowed(ch, sup_pref, tenant_pref)
                    if not allowed:
                        logger.info("Skipping %s for supervisor %s: %s", ch, sup_user_id, skip_reason)
                        continue
                    idem_key = f"{event.event_type.value}:{event.leave_request_id}:{sup_user_id}:{ch.value}"
                    req = NotificationCreateRequest(
                        recipient_user_id=sup_user_id,
                        recipient_employee_id=None,
                        recipient_destination=sup_email if ch == NotificationChannel.EMAIL else None,
                        event_type=event.event_type.value,
                        channel=ch,
                        template_key=NotificationEventType.LEAVE_REQUEST_SUBMITTED.value,
                        template_variables=variables,
                        priority=NotificationPriority.NORMAL,
                        idempotency_key=idem_key,
                        scheduled_for=event.occurred_at,
                        related_entity_type="leave_request",
                        related_entity_id=event.leave_request_id,
                    )
                    res = await self.notification_service.create_notification(tenant_id, req, enforce_preferences=False)
                    notifications.append(res)

        elif isinstance(event, LeaveRequestApprovedEvent):
            emp_user_id, work_email = await self._resolve_employee_user_id(tenant_id, event.employee_id)
            emp_pref = await self.repository.get_user_preference(tenant_id, emp_user_id) if emp_user_id else None
            variables = {
                "employee_name": event.employee_name,
                "leave_type": event.leave_type,
                "start_date": event.start_date.isoformat(),
                "end_date": event.end_date.isoformat(),
                "supervisor_comment": event.supervisor_comment or "Approved",
            }
            for ch in [NotificationChannel.EMAIL, NotificationChannel.PUSH]:
                allowed, skip_reason = PreferenceResolver.is_channel_allowed(ch, emp_pref, tenant_pref)
                if not allowed:
                    continue
                idem_key = f"{event.event_type.value}:{event.leave_request_id}:{event.employee_id}:{ch.value}"
                req = NotificationCreateRequest(
                    recipient_user_id=emp_user_id,
                    recipient_employee_id=event.employee_id,
                    recipient_destination=work_email if ch == NotificationChannel.EMAIL else None,
                    event_type=event.event_type.value,
                    channel=ch,
                    template_key=NotificationEventType.LEAVE_REQUEST_APPROVED.value,
                    template_variables=variables,
                    priority=NotificationPriority.NORMAL,
                    idempotency_key=idem_key,
                    scheduled_for=event.occurred_at,
                    related_entity_type="leave_request",
                    related_entity_id=event.leave_request_id,
                )
                res = await self.notification_service.create_notification(tenant_id, req, enforce_preferences=False)
                notifications.append(res)

        elif isinstance(event, LeaveRequestRejectedEvent):
            emp_user_id, work_email = await self._resolve_employee_user_id(tenant_id, event.employee_id)
            emp_pref = await self.repository.get_user_preference(tenant_id, emp_user_id) if emp_user_id else None
            variables = {
                "employee_name": event.employee_name,
                "leave_type": event.leave_type,
                "start_date": event.start_date.isoformat(),
                "end_date": event.end_date.isoformat(),
                "rejection_reason": event.rejection_reason or "Requirements not met",
            }
            for ch in [NotificationChannel.EMAIL, NotificationChannel.PUSH]:
                allowed, skip_reason = PreferenceResolver.is_channel_allowed(ch, emp_pref, tenant_pref)
                if not allowed:
                    continue
                idem_key = f"{event.event_type.value}:{event.leave_request_id}:{event.employee_id}:{ch.value}"
                req = NotificationCreateRequest(
                    recipient_user_id=emp_user_id,
                    recipient_employee_id=event.employee_id,
                    recipient_destination=work_email if ch == NotificationChannel.EMAIL else None,
                    event_type=event.event_type.value,
                    channel=ch,
                    template_key=NotificationEventType.LEAVE_REQUEST_REJECTED.value,
                    template_variables=variables,
                    priority=NotificationPriority.NORMAL,
                    idempotency_key=idem_key,
                    scheduled_for=event.occurred_at,
                    related_entity_type="leave_request",
                    related_entity_id=event.leave_request_id,
                )
                res = await self.notification_service.create_notification(tenant_id, req, enforce_preferences=False)
                notifications.append(res)

        elif isinstance(event, LeaveRequestCancelledEvent):
            sup_user_id, sup_email = await self._resolve_supervisor(
                tenant_id, event.employee_id, event.supervisor_id
            )
            if sup_user_id:
                sup_pref = await self.repository.get_user_preference(tenant_id, sup_user_id)
                variables = {
                    "employee_name": event.employee_name,
                    "leave_type": event.leave_type,
                    "start_date": event.start_date.isoformat(),
                    "end_date": event.end_date.isoformat(),
                    "cancellation_reason": event.cancellation_reason or "Cancelled by employee",
                }
                for ch in [NotificationChannel.EMAIL, NotificationChannel.PUSH]:
                    allowed, skip_reason = PreferenceResolver.is_channel_allowed(ch, sup_pref, tenant_pref)
                    if not allowed:
                        continue
                    idem_key = f"{event.event_type.value}:{event.leave_request_id}:{sup_user_id}:{ch.value}"
                    req = NotificationCreateRequest(
                        recipient_user_id=sup_user_id,
                        recipient_employee_id=None,
                        recipient_destination=sup_email if ch == NotificationChannel.EMAIL else None,
                        event_type=event.event_type.value,
                        channel=ch,
                        template_key=NotificationEventType.LEAVE_REQUEST_CANCELLED.value,
                        template_variables=variables,
                        priority=NotificationPriority.NORMAL,
                        idempotency_key=idem_key,
                        scheduled_for=event.occurred_at,
                        related_entity_type="leave_request",
                        related_entity_id=event.leave_request_id,
                    )
                    res = await self.notification_service.create_notification(tenant_id, req, enforce_preferences=False)
                    notifications.append(res)

        # ---------------------------------------------------------------------
        # B. Phase 8 Attendance Conflict Events
        # ---------------------------------------------------------------------
        elif isinstance(event, OfflineConflictSubmittedEvent):
            reviewer_user_id = event.assigned_reviewer_id
            reviewer_email = None
            if not reviewer_user_id:
                reviewer_user_id, reviewer_email = await self._resolve_supervisor(tenant_id, event.employee_id)
            else:
                user_stmt = select(User.email).where(User.id == reviewer_user_id, User.tenant_id == tenant_id)
                reviewer_email = (await self.session.execute(user_stmt)).scalar_one_or_none()

            if reviewer_user_id:
                rev_pref = await self.repository.get_user_preference(tenant_id, reviewer_user_id)
                variables = {
                    "employee_name": event.employee_name,
                    "conflict_count": str(event.conflict_count),
                    "incident_id": str(event.incident_id),
                    "reason": event.reason or f"Bundle {event.bundle_id[:8]}",
                }
                for ch in [NotificationChannel.EMAIL, NotificationChannel.PUSH]:
                    allowed, skip_reason = PreferenceResolver.is_channel_allowed(ch, rev_pref, tenant_pref)
                    if not allowed:
                        continue
                    idem_key = f"{event.event_type.value}:{event.incident_id}:{reviewer_user_id}:{ch.value}"
                    req = NotificationCreateRequest(
                        recipient_user_id=reviewer_user_id,
                        recipient_employee_id=None,
                        recipient_destination=reviewer_email if ch == NotificationChannel.EMAIL else None,
                        event_type=event.event_type.value,
                        channel=ch,
                        template_key=NotificationEventType.OFFLINE_CONFLICT_SUBMITTED.value,
                        template_variables=variables,
                        priority=NotificationPriority.NORMAL,
                        idempotency_key=idem_key,
                        scheduled_for=event.occurred_at,
                        related_entity_type="attendance_conflict_incident",
                        related_entity_id=event.incident_id,
                    )
                    res = await self.notification_service.create_notification(tenant_id, req, enforce_preferences=False)
                    notifications.append(res)

        elif isinstance(event, AttendanceConflictApprovedEvent):
            emp_user_id, work_email = await self._resolve_employee_user_id(tenant_id, event.employee_id)
            emp_pref = await self.repository.get_user_preference(tenant_id, emp_user_id) if emp_user_id else None
            variables = {
                "employee_name": event.employee_name,
                "incident_id": str(event.incident_id),
                "adjudication_comment": event.adjudication_comment or "Approved",
            }
            for ch in [NotificationChannel.EMAIL, NotificationChannel.PUSH]:
                allowed, skip_reason = PreferenceResolver.is_channel_allowed(ch, emp_pref, tenant_pref)
                if not allowed:
                    continue
                idem_key = f"{event.event_type.value}:{event.incident_id}:{event.employee_id}:{ch.value}"
                req = NotificationCreateRequest(
                    recipient_user_id=emp_user_id,
                    recipient_employee_id=event.employee_id,
                    recipient_destination=work_email if ch == NotificationChannel.EMAIL else None,
                    event_type=event.event_type.value,
                    channel=ch,
                    template_key=NotificationEventType.ATTENDANCE_CONFLICT_APPROVED.value,
                    template_variables=variables,
                    priority=NotificationPriority.NORMAL,
                    idempotency_key=idem_key,
                    scheduled_for=event.occurred_at,
                    related_entity_type="attendance_conflict_incident",
                    related_entity_id=event.incident_id,
                )
                res = await self.notification_service.create_notification(tenant_id, req, enforce_preferences=False)
                notifications.append(res)

        elif isinstance(event, AttendanceConflictRejectedEvent):
            emp_user_id, work_email = await self._resolve_employee_user_id(tenant_id, event.employee_id)
            emp_pref = await self.repository.get_user_preference(tenant_id, emp_user_id) if emp_user_id else None
            variables = {
                "employee_name": event.employee_name,
                "incident_id": str(event.incident_id),
                "rejection_reason": event.rejection_reason or "Rejected by reviewer",
            }
            for ch in [NotificationChannel.EMAIL, NotificationChannel.PUSH]:
                allowed, skip_reason = PreferenceResolver.is_channel_allowed(ch, emp_pref, tenant_pref)
                if not allowed:
                    continue
                idem_key = f"{event.event_type.value}:{event.incident_id}:{event.employee_id}:{ch.value}"
                req = NotificationCreateRequest(
                    recipient_user_id=emp_user_id,
                    recipient_employee_id=event.employee_id,
                    recipient_destination=work_email if ch == NotificationChannel.EMAIL else None,
                    event_type=event.event_type.value,
                    channel=ch,
                    template_key=NotificationEventType.ATTENDANCE_CONFLICT_REJECTED.value,
                    template_variables=variables,
                    priority=NotificationPriority.NORMAL,
                    idempotency_key=idem_key,
                    scheduled_for=event.occurred_at,
                    related_entity_type="attendance_conflict_incident",
                    related_entity_id=event.incident_id,
                )
                res = await self.notification_service.create_notification(tenant_id, req, enforce_preferences=False)
                notifications.append(res)

        # ---------------------------------------------------------------------
        # C. Phase 7 Fraud Shield Events (Urgent Priority)
        # ---------------------------------------------------------------------
        elif isinstance(event, HighRiskFraudAlertEvent):
            admins = await self._resolve_tenant_admins(tenant_id)
            variables = {
                "employee_name": event.employee_name,
                "risk_score": str(event.risk_score),
                "risk_category": event.risk_category,
                "event_type": event.attendance_event_type,
                "flag_summary": event.flag_summary,
            }
            for admin_id, admin_email in admins:
                adm_pref = await self.repository.get_user_preference(tenant_id, admin_id)
                for ch in [NotificationChannel.EMAIL, NotificationChannel.PUSH]:
                    allowed, _ = PreferenceResolver.is_channel_allowed(ch, adm_pref, tenant_pref)
                    if not allowed:
                        continue
                    idem_key = f"{event.event_type.value}:{event.attendance_event_id}:{admin_id}:{ch.value}"
                    req = NotificationCreateRequest(
                        recipient_user_id=admin_id,
                        recipient_employee_id=None,
                        recipient_destination=admin_email if ch == NotificationChannel.EMAIL else None,
                        event_type=event.event_type.value,
                        channel=ch,
                        template_key=NotificationEventType.HIGH_RISK_FRAUD_ALERT.value,
                        template_variables=variables,
                        priority=NotificationPriority.URGENT,
                        idempotency_key=idem_key,
                        scheduled_for=event.occurred_at,
                        related_entity_type="attendance_event",
                        related_entity_id=event.attendance_event_id,
                    )
                    res = await self.notification_service.create_notification(tenant_id, req, enforce_preferences=False)
                    notifications.append(res)

        elif isinstance(event, ImpossibleTravelSignalEvent):
            admins = await self._resolve_tenant_admins(tenant_id)
            variables = {
                "employee_name": event.employee_name,
                "velocity_mps": f"{event.velocity_mps:.1f}",
                "distance_km": f"{event.distance_km:.2f}",
                "elapsed_seconds": f"{event.elapsed_seconds:.0f}",
            }
            for admin_id, admin_email in admins:
                adm_pref = await self.repository.get_user_preference(tenant_id, admin_id)
                for ch in [NotificationChannel.EMAIL, NotificationChannel.PUSH]:
                    allowed, _ = PreferenceResolver.is_channel_allowed(ch, adm_pref, tenant_pref)
                    if not allowed:
                        continue
                    idem_key = f"{event.event_type.value}:{event.attendance_event_id}:{admin_id}:{ch.value}"
                    req = NotificationCreateRequest(
                        recipient_user_id=admin_id,
                        recipient_employee_id=None,
                        recipient_destination=admin_email if ch == NotificationChannel.EMAIL else None,
                        event_type=event.event_type.value,
                        channel=ch,
                        template_key=NotificationEventType.IMPOSSIBLE_TRAVEL_SIGNAL.value,
                        template_variables=variables,
                        priority=NotificationPriority.URGENT,
                        idempotency_key=idem_key,
                        scheduled_for=event.occurred_at,
                        related_entity_type="attendance_event",
                        related_entity_id=event.attendance_event_id,
                    )
                    res = await self.notification_service.create_notification(tenant_id, req, enforce_preferences=False)
                    notifications.append(res)

        elif isinstance(event, MockGpsDetectedEvent):
            admins = await self._resolve_tenant_admins(tenant_id)
            variables = {
                "employee_name": event.employee_name,
                "device_id": event.device_id or "Unknown Device",
                "location_summary": event.location_summary,
            }
            for admin_id, admin_email in admins:
                adm_pref = await self.repository.get_user_preference(tenant_id, admin_id)
                for ch in [NotificationChannel.EMAIL, NotificationChannel.PUSH]:
                    allowed, _ = PreferenceResolver.is_channel_allowed(ch, adm_pref, tenant_pref)
                    if not allowed:
                        continue
                    idem_key = f"{event.event_type.value}:{event.attendance_event_id}:{admin_id}:{ch.value}"
                    req = NotificationCreateRequest(
                        recipient_user_id=admin_id,
                        recipient_employee_id=None,
                        recipient_destination=admin_email if ch == NotificationChannel.EMAIL else None,
                        event_type=event.event_type.value,
                        channel=ch,
                        template_key=NotificationEventType.MOCK_GPS_DETECTED.value,
                        template_variables=variables,
                        priority=NotificationPriority.URGENT,
                        idempotency_key=idem_key,
                        scheduled_for=event.occurred_at,
                        related_entity_type="attendance_event",
                        related_entity_id=event.attendance_event_id,
                    )
                    res = await self.notification_service.create_notification(tenant_id, req, enforce_preferences=False)
                    notifications.append(res)

        # ---------------------------------------------------------------------
        # D. Phase 4 Employee Invitation Events
        # ---------------------------------------------------------------------
        elif isinstance(event, (EmployeeInvitationCreatedEvent, EmployeeInvitationSentEvent)):
            variables = {
                "recipient_name": event.recipient_name,
                "company_name": event.company_name,
                "activation_url": event.activation_url,
                "expires_hours": str(event.expires_hours),
            }
            idem_key = f"{event.event_type.value}:{event.invitation_id}:{event.recipient_email}:EMAIL"
            req = NotificationCreateRequest(
                recipient_user_id=None,
                recipient_employee_id=event.employee_id,
                recipient_destination=event.recipient_email,
                event_type=event.event_type.value,
                channel=NotificationChannel.EMAIL,
                template_key=event.event_type.value,
                template_variables=variables,
                priority=NotificationPriority.HIGH,
                idempotency_key=idem_key,
                scheduled_for=event.occurred_at,
                related_entity_type="employee_invitation",
                related_entity_id=event.invitation_id,
            )
            res = await self.notification_service.create_notification(tenant_id, req, enforce_preferences=False)
            notifications.append(res)

        # ---------------------------------------------------------------------
        # E. Phase 2 Password Reset Events
        # ---------------------------------------------------------------------
        elif isinstance(event, PasswordResetRequestedEvent):
            variables = {
                "user_name": event.user_name,
                "company_name": event.company_name,
                "reset_url": event.reset_url,
                "expires_minutes": str(event.expires_minutes),
            }
            # Idempotency key covers user within 15-minute window or correlation ID
            time_bucket = event.occurred_at.strftime("%Y%m%d%H%M")[:11]  # ~10 min bucket
            idem_key = f"{event.event_type.value}:{event.user_id}:{time_bucket}:EMAIL"
            req = NotificationCreateRequest(
                recipient_user_id=event.user_id,
                recipient_employee_id=None,
                recipient_destination=event.user_email,
                event_type=event.event_type.value,
                channel=NotificationChannel.EMAIL,
                template_key=NotificationEventType.PASSWORD_RESET_REQUESTED.value,
                template_variables=variables,
                priority=NotificationPriority.URGENT,
                idempotency_key=idem_key,
                scheduled_for=event.occurred_at,
                related_entity_type="user",
                related_entity_id=event.user_id,
            )
            res = await self.notification_service.create_notification(tenant_id, req, enforce_preferences=False)
            notifications.append(res)

        return notifications


# =============================================================================
# 3. Convenience Dispatch Function & Post-Commit Celery Enqueuer
# =============================================================================


async def dispatch_domain_event(
    session: AsyncSession,
    event: DomainEvent,
) -> list[NotificationResponse]:
    """Top-level helper to process a domain event inside the active transaction."""
    handler = DomainNotificationHandler(session)
    return await handler.handle_event(event)


def enqueue_celery_dispatch(notifications: list[NotificationResponse]) -> int:
    """Enqueues Celery background dispatch tasks for the given notifications.

    Should be called *after* transaction commit. If Celery/Redis is unreachable,
    the notifications remain in PENDING status in the database (Transactional Outbox)
    and will be picked up by the Celery batch worker.
    """
    enqueued = 0
    from services.workers.notification_tasks import dispatch_single_notification_task

    for n in notifications:
        try:
            dispatch_single_notification_task.delay(str(n.id), str(n.tenant_id))
            enqueued += 1
        except Exception as exc:
            logger.warning(
                "Failed to enqueue Celery task for notification %s (Outbox recovery will dispatch): %s",
                n.id,
                exc,
            )
    return enqueued
