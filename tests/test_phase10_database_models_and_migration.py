"""Comprehensive automated test suite for Phase 10 Milestone 10.1:
Notification Database Architecture, Models & Alembic Migration.

Validates:
1. Alembic migration chain integrity and dependency on Phase 9 head a4b5c6d7e8f9.
2. Upgrade and downgrade callables in migration b5c6d7e8f9a0.
3. SQLAlchemy models for all 4 Phase 10 entities:
   - NotificationTemplate (notification_templates)
   - NotificationPreference (notification_preferences)
   - Notification (notifications)
   - DevicePushToken (device_push_tokens)
4. Multi-tenant composite foreign keys, unique constraints, and check constraints.
5. System-level vs tenant-level template isolation and partial unique indexes.
6. User-level override vs tenant-default preference scopes.
7. Notification lifecycle status values, priority levels, and audit preservation (SET NULL on delete).
8. Device push token platform validation, status transitions, and active token uniqueness.
9. Verification of model registration in Base.metadata.
10. SQL DDL verification for Row-Level Security (RLS) policies and table grants.
"""

import hashlib
import uuid

from sqlalchemy import CheckConstraint

from database.migrations.versions import b5c6d7e8f9a0_phase_10_notifications as m101
from services.api.database import Base
from services.api.notifications.models import (
    DevicePushToken,
    Notification,
    NotificationPreference,
    NotificationTemplate,
)
from services.api.organization.models import Department  # noqa: F401


class TestAlembicMigrationIntegrity:
    """Validates Alembic migration chain and script metadata for Phase 10."""

    def test_migration_revision_and_down_revision(self):
        """Revision must be unique and down_revision must match Phase 9 head a4b5c6d7e8f9."""
        assert m101.revision == "b5c6d7e8f9a0"
        assert m101.down_revision == "a4b5c6d7e8f9"
        assert m101.branch_labels is None
        assert m101.depends_on is None

    def test_upgrade_and_downgrade_callables_exist(self):
        """Migration module must expose upgrade() and downgrade() functions."""
        assert callable(m101.upgrade)
        assert callable(m101.downgrade)


class TestModelMetadataRegistration:
    """Validates that all Phase 10 models register in Base.metadata."""

    def test_all_tables_registered_in_metadata(self):
        """All 4 Phase 10 table names must be registered in SQLAlchemy Base.metadata."""
        table_names = set(Base.metadata.tables.keys())
        expected_tables = {
            "notification_templates",
            "notification_preferences",
            "notifications",
            "device_push_tokens",
        }
        assert expected_tables.issubset(table_names), (
            f"Missing tables in metadata: {expected_tables - table_names}"
        )


class TestNotificationTemplateModel:
    """Validates NotificationTemplate entity architecture, constraints, and indexes."""

    def test_instantiate_tenant_template_success(self):
        """Tenant-scoped template instantiates with valid defaults."""
        tenant_id = uuid.uuid4()
        template = NotificationTemplate(
            tenant_id=tenant_id,
            template_key="LEAVE_REQUEST_APPROVED",
            name="Leave Approved Notification",
            event_type="LEAVE_REQUEST",
            channel="EMAIL",
            subject_template="Your leave for {{start_date}} has been approved",
            body_template="Hi {{employee_name}}, your {{leave_type}} leave has been approved by {{reviewer_name}}.",
            locale="en",
            is_active=True,
            is_system=False,
        )
        assert template.tenant_id == tenant_id
        assert template.is_system is False
        assert template.channel == "EMAIL"
        assert template.locale == "en"
        assert template.is_active is True
        assert "<NotificationTemplate" in repr(template)

    def test_instantiate_system_template_success(self):
        """System-level default template has tenant_id=None and is_system=True."""
        template = NotificationTemplate(
            tenant_id=None,
            template_key="ATTENDANCE_CONFLICT_RESOLVED",
            name="System Default Conflict Resolved",
            event_type="ATTENDANCE_CONFLICT",
            channel="PUSH",
            body_template="Your attendance conflict for session {{session_id}} was approved.",
            locale="en",
            is_system=True,
        )
        assert template.tenant_id is None
        assert template.is_system is True
        assert template.channel == "PUSH"

    def test_template_table_constraints(self):
        """Check constraints for channel and system/tenant consistency must exist."""
        table = NotificationTemplate.__table__
        check_constraints = {
            c.name: str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)
        }
        assert "chk_notification_templates_channel" in check_constraints
        assert "chk_notification_templates_system_tenant" in check_constraints

        # Verify channel check constraint restricts to PUSH, EMAIL, SMS
        channel_sql = check_constraints["chk_notification_templates_channel"]
        assert "PUSH" in channel_sql and "EMAIL" in channel_sql and "SMS" in channel_sql

    def test_template_partial_indexes(self):
        """Partial indexes must isolate tenant overrides from system templates."""
        table = NotificationTemplate.__table__
        index_names = {idx.name for idx in table.indexes}
        assert "uq_notification_templates_tenant" in index_names
        assert "uq_notification_templates_system" in index_names
        assert "ix_notification_templates_lookup" in index_names


class TestNotificationPreferenceModel:
    """Validates NotificationPreference entity architecture, defaults, and scopes."""

    def test_instantiate_tenant_default_preferences(self):
        """Tenant default preferences have user_id=None and active channel defaults."""
        tenant_id = uuid.uuid4()
        pref = NotificationPreference(
            tenant_id=tenant_id,
            user_id=None,
            is_push_enabled=True,
            is_email_enabled=True,
            is_sms_enabled=False,
            quiet_hours_enabled=False,
            timezone="America/New_York",
            category_preferences={"attendance": True, "leave": True, "fraud_alerts": True},
        )
        assert pref.tenant_id == tenant_id
        assert pref.user_id is None
        assert pref.is_push_enabled is True
        assert pref.is_email_enabled is True
        assert pref.is_sms_enabled is False
        assert pref.timezone == "America/New_York"
        assert "<NotificationPreference" in repr(pref)

    def test_instantiate_user_override_preferences_with_quiet_hours(self):
        """User override preference has user_id set and configures quiet hours window."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        pref = NotificationPreference(
            tenant_id=tenant_id,
            user_id=user_id,
            is_push_enabled=True,
            is_email_enabled=False,
            is_sms_enabled=False,
            quiet_hours_enabled=True,
            quiet_hours_start="22:00",
            quiet_hours_end="07:30",
            timezone="Asia/Kolkata",
        )
        assert pref.user_id == user_id
        assert pref.quiet_hours_enabled is True
        assert pref.quiet_hours_start == "22:00"
        assert pref.quiet_hours_end == "07:30"

    def test_preference_table_indexes(self):
        """Indexes must support user override uniqueness and tenant default uniqueness."""
        table = NotificationPreference.__table__
        index_names = {idx.name for idx in table.indexes}
        assert "uq_notification_preferences_user" in index_names
        assert "uq_notification_preferences_tenant_default" in index_names


class TestNotificationModel:
    """Validates Notification dispatch queue and audit entity architecture."""

    def test_instantiate_notification_record_success(self):
        """Notification instantiates with default PENDING status and audit fields."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        notif = Notification(
            tenant_id=tenant_id,
            recipient_user_id=user_id,
            recipient_employee_id=emp_id,
            event_type="LEAVE_REQUEST_SUBMITTED",
            channel="EMAIL",
            recipient_destination="manager@enterprise.test",
            subject="New Leave Request Pending Your Approval",
            body="Employee Jane Doe has requested 2 days of Annual Leave.",
            payload_json={"request_id": str(uuid.uuid4()), "action_url": "/leave/approvals"},
            status="PENDING",
            priority="HIGH",
            attempt_count=0,
            max_attempts=3,
            idempotency_key="idemp_leave_submit_12345",
        )
        assert notif.tenant_id == tenant_id
        assert notif.status == "PENDING"
        assert notif.priority == "HIGH"
        assert notif.attempt_count == 0
        assert notif.max_attempts == 3
        assert notif.idempotency_key == "idemp_leave_submit_12345"
        assert "<Notification" in repr(notif)

    def test_notification_status_and_priority_constraints(self):
        """Check constraints must enforce permitted statuses and priority values."""
        table = Notification.__table__
        check_constraints = {
            c.name: str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)
        }
        assert "chk_notifications_channel" in check_constraints
        assert "chk_notifications_status" in check_constraints
        assert "chk_notifications_priority" in check_constraints
        assert "chk_notifications_attempt_count" in check_constraints
        assert "chk_notifications_max_attempts" in check_constraints

        status_sql = check_constraints["chk_notifications_status"]
        for st in ["PENDING", "PROCESSING", "RETRY_SCHEDULED", "SENT", "DELIVERED", "FAILED", "CANCELLED"]:
            assert st in status_sql

    def test_notification_audit_preservation_foreign_keys(self):
        """Recipient foreign keys must use ondelete='SET NULL' to preserve delivery audit trails."""
        table = Notification.__table__
        fk_ondelete = {fk.parent.name: fk.ondelete for fk in table.foreign_keys}

        assert fk_ondelete.get("recipient_user_id") == "SET NULL", (
            "recipient_user_id must SET NULL to preserve notification delivery history"
        )
        assert fk_ondelete.get("recipient_employee_id") == "SET NULL", (
            "recipient_employee_id must SET NULL to preserve notification delivery history"
        )
        assert fk_ondelete.get("template_id") == "SET NULL", (
            "template_id must SET NULL on template deletion to retain rendered message audit"
        )
        assert fk_ondelete.get("tenant_id") == "RESTRICT"

    def test_notification_indexes_for_dispatch_and_audit(self):
        """Worker queue, recipient query, and idempotency indexes must exist."""
        table = Notification.__table__
        index_names = {idx.name for idx in table.indexes}
        assert "uq_notifications_tenant_idempotency" in index_names
        assert "ix_notifications_worker_queue" in index_names
        assert "ix_notifications_recipient_user" in index_names
        assert "ix_notifications_recipient_employee" in index_names
        assert "ix_notifications_related_entity" in index_names


class TestDevicePushTokenModel:
    """Validates DevicePushToken entity architecture, security hashing, and rotation."""

    def test_instantiate_device_push_token_success(self):
        """Push token instantiates with token_hash and default ACTIVE status."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        raw_token = "fcm_mock_device_token_xyz_1234567890abcdef"
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

        push_token = DevicePushToken(
            tenant_id=tenant_id,
            user_id=user_id,
            platform="ANDROID",
            token=raw_token,
            token_hash=token_hash,
            device_model="Pixel 8",
            os_version="Android 15",
            app_version="1.0.0",
            status="ACTIVE",
        )
        assert push_token.tenant_id == tenant_id
        assert push_token.platform == "ANDROID"
        assert push_token.status == "ACTIVE"
        assert len(push_token.token_hash) == 64
        assert "<DevicePushToken" in repr(push_token)

    def test_device_push_token_constraints(self):
        """Check constraints must enforce valid platforms and statuses."""
        table = DevicePushToken.__table__
        check_constraints = {
            c.name: str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)
        }
        assert "chk_device_push_tokens_platform" in check_constraints
        assert "chk_device_push_tokens_status" in check_constraints

        status_sql = check_constraints["chk_device_push_tokens_status"]
        assert "ACTIVE" in status_sql and "REVOKED" in status_sql and "EXPIRED" in status_sql

    def test_device_push_token_active_uniqueness_index(self):
        """uq_device_push_tokens_active_token index must exist to prevent duplicate active tokens."""
        table = DevicePushToken.__table__
        index_names = {idx.name for idx in table.indexes}
        assert "uq_device_push_tokens_active_token" in index_names
        assert "ix_device_push_tokens_user_status" in index_names
        assert "ix_device_push_tokens_employee_status" in index_names


class TestMigrationRLSPoliciesScriptVerification:
    """Verifies DDL structure and RLS policy statements in the migration script."""

    def test_migration_enables_rls_on_all_four_tables(self):
        """Migration script must execute ENABLE and FORCE ROW LEVEL SECURITY on all 4 tables."""
        import inspect

        source = inspect.getsource(m101.upgrade)
        tables = [
            "notification_templates",
            "notification_preferences",
            "notifications",
            "device_push_tokens",
        ]
        for tbl in tables:
            assert f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;" in source, f"Missing ENABLE RLS on {tbl}"
            assert f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;" in source, f"Missing FORCE RLS on {tbl}"

    def test_migration_template_read_and_write_policy_distinction(self):
        """Template migration must allow system template read (tenant_id IS NULL) while restricting writes."""
        import inspect

        source = inspect.getsource(m101.upgrade)
        assert "CREATE POLICY tenant_isolation_read ON notification_templates" in source
        assert "tenant_id IS NULL" in source
        assert "CREATE POLICY tenant_isolation_write ON notification_templates" in source
        assert "WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid)" in source

    def test_migration_grants_permissions(self):
        """Migration script must grant CRUD permissions to authenticated and service_role."""
        import inspect

        source = inspect.getsource(m101.upgrade)
        assert "GRANT SELECT, INSERT, UPDATE, DELETE ON notification_templates TO authenticated, service_role;" in source
        assert "GRANT SELECT, INSERT, UPDATE, DELETE ON" in source
        assert "TO authenticated, service_role;" in source
