"""Default system notification templates for Phase 10 Domain Events.

Provides canonical system templates for all approved domain events:
- Phase 9 Leave: submitted, approved, rejected, cancelled
- Phase 8 Conflicts: submitted, approved, rejected
- Phase 7 Fraud Shield: high-risk fraud alert, impossible travel signal, mock GPS detected
- Phase 4 Invitations: created, sent
- Phase 2 Password Resets: requested

Supports:
- Safe parameter substitution adhering to SafeTemplateRenderer regex
- Context-aware escaping and zero code execution
- Safe fallback when database records have not been seeded
"""

import uuid
from typing import Any

from services.api.notifications.models import NotificationTemplate
from services.api.notifications.schemas import NotificationChannel, NotificationEventType

# Built-in system template definitions
SYSTEM_DEFAULT_TEMPLATES: list[dict[str, Any]] = [
    # =========================================================================
    # Phase 9 — Leave Templates
    # =========================================================================
    {
        "template_key": NotificationEventType.LEAVE_REQUEST_SUBMITTED.value,
        "name": "Leave Request Submitted (Email)",
        "description": "Sent to supervisor when an employee applies for time off.",
        "event_type": NotificationEventType.LEAVE_REQUEST_SUBMITTED.value,
        "channel": NotificationChannel.EMAIL.value,
        "subject_template": "Leave Request Submitted: {employee_name} ({leave_type})",
        "body_template": (
            "Hello,\n\n"
            "{employee_name} has submitted a leave request for {duration_days} day(s) "
            "from {start_date} to {end_date}.\n"
            "Reason: {reason}\n\n"
            "Please review and adjudicate in the supervisor portal."
        ),
        "locale": "en",
    },
    {
        "template_key": NotificationEventType.LEAVE_REQUEST_SUBMITTED.value,
        "name": "Leave Request Submitted (Push)",
        "description": "Push notification to supervisor when an employee applies for time off.",
        "event_type": NotificationEventType.LEAVE_REQUEST_SUBMITTED.value,
        "channel": NotificationChannel.PUSH.value,
        "subject_template": "New Leave Request",
        "body_template": "{employee_name} requested {duration_days} day(s) of {leave_type}.",
        "locale": "en",
    },
    {
        "template_key": NotificationEventType.LEAVE_REQUEST_APPROVED.value,
        "name": "Leave Request Approved (Email)",
        "description": "Sent to employee when their time-off application is approved.",
        "event_type": NotificationEventType.LEAVE_REQUEST_APPROVED.value,
        "channel": NotificationChannel.EMAIL.value,
        "subject_template": "Leave Request Approved: {leave_type}",
        "body_template": (
            "Hello {employee_name},\n\n"
            "Your leave request for {leave_type} from {start_date} to {end_date} has been approved.\n"
            "Supervisor Comment: {supervisor_comment}\n\n"
            "Thank you."
        ),
        "locale": "en",
    },
    {
        "template_key": NotificationEventType.LEAVE_REQUEST_APPROVED.value,
        "name": "Leave Request Approved (Push)",
        "description": "Push notification to employee when leave is approved.",
        "event_type": NotificationEventType.LEAVE_REQUEST_APPROVED.value,
        "channel": NotificationChannel.PUSH.value,
        "subject_template": "Leave Request Approved",
        "body_template": "Your {leave_type} request ({start_date} to {end_date}) was approved.",
        "locale": "en",
    },
    {
        "template_key": NotificationEventType.LEAVE_REQUEST_REJECTED.value,
        "name": "Leave Request Rejected (Email)",
        "description": "Sent to employee when their time-off application is rejected.",
        "event_type": NotificationEventType.LEAVE_REQUEST_REJECTED.value,
        "channel": NotificationChannel.EMAIL.value,
        "subject_template": "Leave Request Rejected: {leave_type}",
        "body_template": (
            "Hello {employee_name},\n\n"
            "Your leave request for {leave_type} from {start_date} to {end_date} has been rejected.\n"
            "Reason: {rejection_reason}\n\n"
            "If you have questions, please reach out to your supervisor."
        ),
        "locale": "en",
    },
    {
        "template_key": NotificationEventType.LEAVE_REQUEST_REJECTED.value,
        "name": "Leave Request Rejected (Push)",
        "description": "Push notification to employee when leave is rejected.",
        "event_type": NotificationEventType.LEAVE_REQUEST_REJECTED.value,
        "channel": NotificationChannel.PUSH.value,
        "subject_template": "Leave Request Rejected",
        "body_template": "Your {leave_type} request was rejected: {rejection_reason}",
        "locale": "en",
    },
    {
        "template_key": NotificationEventType.LEAVE_REQUEST_CANCELLED.value,
        "name": "Leave Request Cancelled (Email)",
        "description": "Sent to supervisor when an employee cancels a pending leave request.",
        "event_type": NotificationEventType.LEAVE_REQUEST_CANCELLED.value,
        "channel": NotificationChannel.EMAIL.value,
        "subject_template": "Leave Request Cancelled: {employee_name}",
        "body_template": (
            "Hello,\n\n"
            "{employee_name} has cancelled their leave request for {leave_type} "
            "({start_date} to {end_date}).\n"
            "Reason: {cancellation_reason}\n\n"
            "Reserved balances have been returned to available leave."
        ),
        "locale": "en",
    },
    {
        "template_key": NotificationEventType.LEAVE_REQUEST_CANCELLED.value,
        "name": "Leave Request Cancelled (Push)",
        "description": "Push notification to supervisor when an employee cancels leave.",
        "event_type": NotificationEventType.LEAVE_REQUEST_CANCELLED.value,
        "channel": NotificationChannel.PUSH.value,
        "subject_template": "Leave Request Cancelled",
        "body_template": "{employee_name} cancelled their {leave_type} request.",
        "locale": "en",
    },

    # =========================================================================
    # Phase 8 — Attendance Conflict Templates
    # =========================================================================
    {
        "template_key": NotificationEventType.OFFLINE_CONFLICT_SUBMITTED.value,
        "name": "Offline Conflict Incident Submitted (Email)",
        "description": "Sent to supervisor when an offline attendance conflict bundle arrives.",
        "event_type": NotificationEventType.OFFLINE_CONFLICT_SUBMITTED.value,
        "channel": NotificationChannel.EMAIL.value,
        "subject_template": "Attendance Conflict Submitted: {employee_name}",
        "body_template": (
            "Hello,\n\n"
            "An offline attendance conflict bundle containing {conflict_count} incident(s) "
            "has been submitted for {employee_name}.\n"
            "Incident ID: {incident_id}\n"
            "Summary: {reason}\n\n"
            "Please review and adjudicate in the supervisor queue."
        ),
        "locale": "en",
    },
    {
        "template_key": NotificationEventType.OFFLINE_CONFLICT_SUBMITTED.value,
        "name": "Offline Conflict Incident Submitted (Push)",
        "description": "Push notification to supervisor for new offline conflict bundle.",
        "event_type": NotificationEventType.OFFLINE_CONFLICT_SUBMITTED.value,
        "channel": NotificationChannel.PUSH.value,
        "subject_template": "Attendance Conflict Awaiting Review",
        "body_template": "{employee_name} submitted a conflict bundle ({conflict_count} events).",
        "locale": "en",
    },
    {
        "template_key": NotificationEventType.ATTENDANCE_CONFLICT_APPROVED.value,
        "name": "Attendance Conflict Approved (Email)",
        "description": "Sent to employee when their attendance conflict incident is approved.",
        "event_type": NotificationEventType.ATTENDANCE_CONFLICT_APPROVED.value,
        "channel": NotificationChannel.EMAIL.value,
        "subject_template": "Attendance Conflict Approved",
        "body_template": (
            "Hello {employee_name},\n\n"
            "Your attendance conflict incident ({incident_id}) has been approved.\n"
            "Reviewer Notes: {adjudication_comment}\n\n"
            "The attendance ledger has been reconciled."
        ),
        "locale": "en",
    },
    {
        "template_key": NotificationEventType.ATTENDANCE_CONFLICT_APPROVED.value,
        "name": "Attendance Conflict Approved (Push)",
        "description": "Push notification to employee when conflict is approved.",
        "event_type": NotificationEventType.ATTENDANCE_CONFLICT_APPROVED.value,
        "channel": NotificationChannel.PUSH.value,
        "subject_template": "Attendance Conflict Approved",
        "body_template": "Your attendance conflict incident {incident_id} was approved.",
        "locale": "en",
    },
    {
        "template_key": NotificationEventType.ATTENDANCE_CONFLICT_REJECTED.value,
        "name": "Attendance Conflict Rejected (Email)",
        "description": "Sent to employee when their attendance conflict incident is rejected.",
        "event_type": NotificationEventType.ATTENDANCE_CONFLICT_REJECTED.value,
        "channel": NotificationChannel.EMAIL.value,
        "subject_template": "Attendance Conflict Rejected",
        "body_template": (
            "Hello {employee_name},\n\n"
            "Your attendance conflict incident ({incident_id}) has been rejected.\n"
            "Reason: {rejection_reason}\n\n"
            "If you believe this is in error, contact your supervisor."
        ),
        "locale": "en",
    },
    {
        "template_key": NotificationEventType.ATTENDANCE_CONFLICT_REJECTED.value,
        "name": "Attendance Conflict Rejected (Push)",
        "description": "Push notification to employee when conflict is rejected.",
        "event_type": NotificationEventType.ATTENDANCE_CONFLICT_REJECTED.value,
        "channel": NotificationChannel.PUSH.value,
        "subject_template": "Attendance Conflict Rejected",
        "body_template": "Your attendance conflict incident {incident_id} was rejected.",
        "locale": "en",
    },

    # =========================================================================
    # Phase 7 — Fraud Shield Templates
    # =========================================================================
    {
        "template_key": NotificationEventType.HIGH_RISK_FRAUD_ALERT.value,
        "name": "High-Risk Fraud Alert (Email)",
        "description": "Critical security alert to tenant admins on high/critical attendance fraud.",
        "event_type": NotificationEventType.HIGH_RISK_FRAUD_ALERT.value,
        "channel": NotificationChannel.EMAIL.value,
        "subject_template": "URGENT: High-Risk Attendance Alert for {employee_name}",
        "body_template": (
            "Security Alert: High-risk attendance anomaly detected.\n\n"
            "Employee: {employee_name}\n"
            "Risk Category: {risk_category}\n"
            "Risk Score: {risk_score}\n"
            "Event Type: {event_type}\n"
            "Flags: {flag_summary}\n\n"
            "Please inspect the Fraud Shield review console immediately."
        ),
        "locale": "en",
    },
    {
        "template_key": NotificationEventType.HIGH_RISK_FRAUD_ALERT.value,
        "name": "High-Risk Fraud Alert (Push)",
        "description": "Push alert to tenant admins on high/critical fraud score.",
        "event_type": NotificationEventType.HIGH_RISK_FRAUD_ALERT.value,
        "channel": NotificationChannel.PUSH.value,
        "subject_template": "Security Alert: High-Risk Attendance",
        "body_template": "{risk_category} risk detected for {employee_name} (Score: {risk_score}).",
        "locale": "en",
    },
    {
        "template_key": NotificationEventType.IMPOSSIBLE_TRAVEL_SIGNAL.value,
        "name": "Impossible Travel Detected (Email)",
        "description": "Alert to tenant admins when impossible travel velocity is calculated.",
        "event_type": NotificationEventType.IMPOSSIBLE_TRAVEL_SIGNAL.value,
        "channel": NotificationChannel.EMAIL.value,
        "subject_template": "Fraud Alert: Impossible Travel Detected ({employee_name})",
        "body_template": (
            "Security Alert: Impossible travel velocity calculated between punches.\n\n"
            "Employee: {employee_name}\n"
            "Calculated Velocity: {velocity_mps} m/s\n"
            "Distance: {distance_km} km\n"
            "Elapsed Time: {elapsed_seconds} s\n\n"
            "Review attendance records in the administration portal."
        ),
        "locale": "en",
    },
    {
        "template_key": NotificationEventType.IMPOSSIBLE_TRAVEL_SIGNAL.value,
        "name": "Impossible Travel Detected (Push)",
        "description": "Push notification to tenant admins on impossible travel velocity.",
        "event_type": NotificationEventType.IMPOSSIBLE_TRAVEL_SIGNAL.value,
        "channel": NotificationChannel.PUSH.value,
        "subject_template": "Fraud Alert: Impossible Travel",
        "body_template": "Impossible travel detected for {employee_name} ({velocity_mps} m/s).",
        "locale": "en",
    },
    {
        "template_key": NotificationEventType.MOCK_GPS_DETECTED.value,
        "name": "Mock GPS Detected (Email)",
        "description": "Alert to tenant admins when mock location spoofing is detected.",
        "event_type": NotificationEventType.MOCK_GPS_DETECTED.value,
        "channel": NotificationChannel.EMAIL.value,
        "subject_template": "Fraud Alert: Mock GPS Detected ({employee_name})",
        "body_template": (
            "Security Alert: Mock location provider was detected during punch.\n\n"
            "Employee: {employee_name}\n"
            "Device ID: {device_id}\n"
            "Location Summary: {location_summary}\n\n"
            "Inspect device authorization and fraud flag review queue."
        ),
        "locale": "en",
    },
    {
        "template_key": NotificationEventType.MOCK_GPS_DETECTED.value,
        "name": "Mock GPS Detected (Push)",
        "description": "Push notification to tenant admins on mock GPS detection.",
        "event_type": NotificationEventType.MOCK_GPS_DETECTED.value,
        "channel": NotificationChannel.PUSH.value,
        "subject_template": "Fraud Alert: Mock GPS Detected",
        "body_template": "Mock GPS provider detected for {employee_name}.",
        "locale": "en",
    },

    # =========================================================================
    # Phase 4 — Employee Invitation Templates
    # =========================================================================
    {
        "template_key": NotificationEventType.EMPLOYEE_INVITATION_CREATED.value,
        "name": "Employee Invitation Created (Email)",
        "description": "Sent to new employee to activate account and set password.",
        "event_type": NotificationEventType.EMPLOYEE_INVITATION_CREATED.value,
        "channel": NotificationChannel.EMAIL.value,
        "subject_template": "Invitation to join {company_name} on Attendance SaaS",
        "body_template": (
            "Hello {recipient_name},\n\n"
            "You have been invited to join {company_name} on Attendance SaaS.\n\n"
            "To activate your account and establish your secure credentials, visit:\n"
            "{activation_url}\n\n"
            "This activation link will expire in {expires_hours} hours and can only be used once."
        ),
        "locale": "en",
    },
    {
        "template_key": NotificationEventType.EMPLOYEE_INVITATION_SENT.value,
        "name": "Employee Invitation Sent / Resent (Email)",
        "description": "Sent to employee upon invitation resend or delivery initiation.",
        "event_type": NotificationEventType.EMPLOYEE_INVITATION_SENT.value,
        "channel": NotificationChannel.EMAIL.value,
        "subject_template": "Invitation to join {company_name} on Attendance SaaS",
        "body_template": (
            "Hello {recipient_name},\n\n"
            "Your invitation to join {company_name} on Attendance SaaS has been re-sent.\n\n"
            "To activate your account, please visit:\n"
            "{activation_url}\n\n"
            "This link will expire in {expires_hours} hours."
        ),
        "locale": "en",
    },

    # =========================================================================
    # Phase 2 — Password Reset Template
    # =========================================================================
    {
        "template_key": NotificationEventType.PASSWORD_RESET_REQUESTED.value,
        "name": "Password Reset Request (Email)",
        "description": "Sent to account owner when password reset is requested.",
        "event_type": NotificationEventType.PASSWORD_RESET_REQUESTED.value,
        "channel": NotificationChannel.EMAIL.value,
        "subject_template": "Password Reset Request - {company_name}",
        "body_template": (
            "Hello {user_name},\n\n"
            "A password reset was requested for your account at {company_name}.\n\n"
            "To reset your password, visit:\n"
            "{reset_url}\n\n"
            "This link will expire in {expires_minutes} minutes. "
            "If you did not request this, you can safely ignore this email."
        ),
        "locale": "en",
    },
]


def get_default_system_template(
    template_key: str,
    channel: str,
    locale: str = "en",
) -> NotificationTemplate | None:
    """Retrieves a canonical built-in system template if defined."""
    ch = channel.upper()
    loc = locale.lower()
    for d in SYSTEM_DEFAULT_TEMPLATES:
        if (
            d["template_key"] == template_key
            and d["channel"] == ch
            and d.get("locale", "en") == loc
        ):
            # Deterministic UUID for the system template
            tpl_id = uuid.uuid5(
                uuid.NAMESPACE_DNS,
                f"upostit.system.template.{template_key}.{ch}.{loc}",
            )
            return NotificationTemplate(
                id=tpl_id,
                tenant_id=None,
                template_key=d["template_key"],
                name=d["name"],
                description=d.get("description"),
                event_type=d["event_type"],
                channel=d["channel"],
                subject_template=d.get("subject_template"),
                body_template=d["body_template"],
                locale=loc,
                is_active=True,
                is_system=True,
            )
    return None

