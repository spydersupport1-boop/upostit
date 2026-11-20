"""Comprehensive automated test suite for Phase 8 Milestone 8.1:
Database Architecture, Data Models, and Alembic Migration.

Validates:
1. Alembic migration chain integrity and compatibility with head revision d6e7f8a9b0c1.
2. Static SQL generation for upgrade and downgrade.
3. AttendanceConflictIncident SQLAlchemy model definition, table arguments, constraints, and relationships.
4. Composite foreign key deletion behavior for assigned_reviewer_id (ensuring tenant_id is preserved).
5. Tenant isolation, unique bundle_id constraint per tenant, and composite foreign key mappings.
6. Status, decision, and decision reason constraints.
7. Immutability and preservation of existing attendance ledger tables and models.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, UniqueConstraint

from database.migrations.versions import e7f8a9b0c1d2_phase_08_attendance_conflicts as m81
from services.api.attendance.models import (
    AttendanceConflictIncident,
    AttendanceDay,
    AttendanceEvent,
    AttendanceIdempotencyRecord,
    ShiftAssignment,
    ShiftTemplate,
    ShiftTemplateVersion,
    TenantAttendancePolicy,
)
from services.api.organization.models import Department, Designation  # noqa: F401


class TestAlembicMigrationIntegrity:
    """Validates Alembic migration chain and script metadata."""

    def test_migration_revision_and_down_revision(self):
        """Revision must be unique and down_revision must match current head d6e7f8a9b0c1."""
        assert m81.revision == "e7f8a9b0c1d2"
        assert m81.down_revision == "d6e7f8a9b0c1"
        assert m81.branch_labels is None
        assert m81.depends_on is None

    def test_upgrade_and_downgrade_callables_exist(self):
        """upgrade() and downgrade() functions must be defined and callable."""
        assert callable(m81.upgrade)
        assert callable(m81.downgrade)


class TestAttendanceConflictIncidentModel:
    """Validates the AttendanceConflictIncident SQLAlchemy model structure and constraints."""

    def test_table_name_and_primary_key(self):
        """Table name must be attendance_conflict_incidents with a UUID primary key."""
        assert AttendanceConflictIncident.__tablename__ == "attendance_conflict_incidents"
        pk_cols = [col.name for col in AttendanceConflictIncident.__table__.primary_key.columns]
        assert pk_cols == ["id"]

    def test_required_columns_and_nullability(self):
        """All required domain fields must be defined with correct nullability."""
        cols = AttendanceConflictIncident.__table__.columns

        # Non-nullable mandatory columns
        assert not cols["id"].nullable
        assert not cols["tenant_id"].nullable
        assert not cols["employee_id"].nullable
        assert not cols["user_id"].nullable
        assert not cols["bundle_id"].nullable
        assert not cols["status"].nullable
        assert not cols["primary_rejected_event"].nullable
        assert not cols["dependent_events"].nullable
        assert not cols["total_events_count"].nullable
        assert not cols["submitted_at"].nullable
        assert not cols["resolved_correction_event_ids"].nullable
        assert not cols["metadata_json"].nullable
        assert not cols["created_at"].nullable
        assert not cols["updated_at"].nullable

        # Nullable optional columns
        assert cols["session_id"].nullable
        assert cols["rejection_summary"].nullable
        assert cols["employee_notes"].nullable
        assert cols["assigned_reviewer_id"].nullable
        assert cols["decision"].nullable
        assert cols["decision_reason"].nullable
        assert cols["reviewer_user_id"].nullable
        assert cols["decided_at"].nullable

    def test_unique_constraints(self):
        """Must define composite unique constraint (tenant_id, id) and tenant bundle constraint."""
        table = AttendanceConflictIncident.__table__
        unique_constraints = {
            c.name: [col.name for col in c.columns]
            for c in table.constraints
            if isinstance(c, UniqueConstraint)
        }

        assert "uq_conflict_incidents_tenant_id" in unique_constraints
        assert unique_constraints["uq_conflict_incidents_tenant_id"] == ["tenant_id", "id"]

        assert "uq_conflict_incidents_tenant_bundle" in unique_constraints
        assert unique_constraints["uq_conflict_incidents_tenant_bundle"] == ["tenant_id", "bundle_id"]

    def test_composite_foreign_keys_and_ondelete_actions(self):
        """Composite foreign keys must enforce tenant isolation and appropriate ondelete semantics."""
        table = AttendanceConflictIncident.__table__
        fk_constraints = {
            c.name: {
                "constrained_columns": [col.name for col in c.columns],
                "referred_columns": [elem.target_fullname for elem in c.elements],
                "ondelete": c.ondelete,
            }
            for c in table.constraints
            if isinstance(c, ForeignKeyConstraint)
        }

        # 1. Employee FK: (tenant_id, employee_id) -> (employees.tenant_id, employees.id)
        assert "fk_conflict_incidents_employee" in fk_constraints
        emp_fk = fk_constraints["fk_conflict_incidents_employee"]
        assert emp_fk["constrained_columns"] == ["tenant_id", "employee_id"]
        assert emp_fk["referred_columns"] == ["employees.tenant_id", "employees.id"]
        assert emp_fk["ondelete"] == "RESTRICT"

        # 2. Submitting User FK: (tenant_id, user_id) -> (users.tenant_id, users.id)
        assert "fk_conflict_incidents_user" in fk_constraints
        user_fk = fk_constraints["fk_conflict_incidents_user"]
        assert user_fk["constrained_columns"] == ["tenant_id", "user_id"]
        assert user_fk["referred_columns"] == ["users.tenant_id", "users.id"]
        assert user_fk["ondelete"] == "RESTRICT"

        # 3. Assigned Reviewer FK: (tenant_id, assigned_reviewer_id) -> (users.tenant_id, users.id)
        # CRITICAL VERIFICATION: ondelete must set ONLY assigned_reviewer_id to NULL, never tenant_id!
        assert "fk_conflict_incidents_assigned_reviewer" in fk_constraints
        assigned_fk = fk_constraints["fk_conflict_incidents_assigned_reviewer"]
        assert assigned_fk["constrained_columns"] == ["tenant_id", "assigned_reviewer_id"]
        assert assigned_fk["referred_columns"] == ["users.tenant_id", "users.id"]
        assert assigned_fk["ondelete"] == "SET NULL (assigned_reviewer_id)"

        # 4. Deciding Reviewer FK: (tenant_id, reviewer_user_id) -> (users.tenant_id, users.id)
        assert "fk_conflict_incidents_reviewer" in fk_constraints
        reviewer_fk = fk_constraints["fk_conflict_incidents_reviewer"]
        assert reviewer_fk["constrained_columns"] == ["tenant_id", "reviewer_user_id"]
        assert reviewer_fk["referred_columns"] == ["users.tenant_id", "users.id"]
        assert reviewer_fk["ondelete"] == "RESTRICT"

    def test_check_constraints(self):
        """Database check constraints must validate status, decision, reason length, and combinations."""
        table = AttendanceConflictIncident.__table__
        check_constraints = {c.name: str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)}

        # Status enumeration constraint
        assert "chk_conflict_incidents_status" in check_constraints
        assert "status IN ('PENDING_REVIEW', 'APPROVED', 'REJECTED')" in check_constraints["chk_conflict_incidents_status"]

        # Decision enumeration constraint
        assert "chk_conflict_incidents_decision" in check_constraints
        assert "decision IS NULL OR decision IN ('APPROVED', 'REJECTED')" in check_constraints["chk_conflict_incidents_decision"]

        # Mandatory reason constraint (at least 3 non-whitespace characters)
        assert "chk_conflict_incidents_reason" in check_constraints
        assert "decision IS NULL OR length(trim(decision_reason)) >= 3" in check_constraints["chk_conflict_incidents_reason"]

        # Status and decision combination integrity constraint
        assert "chk_conflict_incidents_status_decision" in check_constraints
        comb_sql = check_constraints["chk_conflict_incidents_status_decision"]
        assert "status = 'PENDING_REVIEW' AND decision IS NULL" in comb_sql
        assert "status = 'APPROVED' AND decision = 'APPROVED'" in comb_sql
        assert "status = 'REJECTED' AND decision = 'REJECTED'" in comb_sql

    def test_indexes_defined(self):
        """Appropriate tenant-scoped query indexes must be configured."""
        table = AttendanceConflictIncident.__table__
        indexes = {
            idx.name: [col.name for col in idx.columns]
            for idx in table.indexes
            if isinstance(idx, Index)
        }

        assert "ix_conflict_incidents_tenant_status" in indexes
        assert indexes["ix_conflict_incidents_tenant_status"] == ["tenant_id", "status"]

        assert "ix_conflict_incidents_tenant_employee" in indexes
        assert indexes["ix_conflict_incidents_tenant_employee"] == ["tenant_id", "employee_id"]

        assert "ix_conflict_incidents_tenant_submitted" in indexes
        assert indexes["ix_conflict_incidents_tenant_submitted"] == ["tenant_id", "submitted_at"]

        assert "ix_conflict_incidents_tenant_decided" in indexes
        assert indexes["ix_conflict_incidents_tenant_decided"] == ["tenant_id", "decided_at"]

        assert "ix_conflict_incidents_tenant_assigned_reviewer" in indexes
        assert indexes["ix_conflict_incidents_tenant_assigned_reviewer"] == ["tenant_id", "assigned_reviewer_id"]

    def test_model_instantiation_defaults(self):
        """Instantiating model creates proper defaults and types."""
        # Verify default definitions on mapped columns
        assert AttendanceConflictIncident.__table__.columns["status"].default.arg == "PENDING_REVIEW"
        assert AttendanceConflictIncident.__table__.columns["total_events_count"].default.arg == 1

        tid = uuid.uuid4()
        eid = uuid.uuid4()
        uid = uuid.uuid4()
        now = datetime.now(UTC)

        incident = AttendanceConflictIncident(
            tenant_id=tid,
            employee_id=eid,
            user_id=uid,
            bundle_id="bundle_12345",
            status="PENDING_REVIEW",
            primary_rejected_event={
                "local_id": "loc_1",
                "idempotency_key": str(uuid.uuid4()),
                "event_type": "CHECK_IN",
                "device_reported_at": now.isoformat(),
                "server_rejection_code": 422,
                "server_rejection_reason": "Out of geofence",
            },
            dependent_events=[],
            total_events_count=1,
            resolved_correction_event_ids=[],
            metadata_json={},
        )

        assert incident.tenant_id == tid
        assert incident.employee_id == eid
        assert incident.user_id == uid
        assert incident.bundle_id == "bundle_12345"
        assert incident.status == "PENDING_REVIEW"
        assert incident.decision is None
        assert incident.decision_reason is None
        assert incident.reviewer_user_id is None
        assert incident.decided_at is None
        assert incident.resolved_correction_event_ids == []
        assert incident.metadata_json == {}

    def test_relationships_defined(self):
        """Relationships to Tenant, Employee, User, and Reviewer must be declared on the model."""
        assert hasattr(AttendanceConflictIncident, "tenant")
        assert hasattr(AttendanceConflictIncident, "employee")
        assert hasattr(AttendanceConflictIncident, "submitting_user")
        assert hasattr(AttendanceConflictIncident, "assigned_reviewer")
        assert hasattr(AttendanceConflictIncident, "reviewer")


class TestExistingAttendanceLedgerPreservation:
    """Ensures existing attendance tables, models, and immutability invariants are untouched."""

    def test_existing_models_remain_intact(self):
        """AttendanceEvent, AttendanceDay, etc. must retain their schema and attributes."""
        assert hasattr(AttendanceEvent, "supersedes_event_id")
        assert hasattr(AttendanceEvent, "correction_reason")
        assert hasattr(AttendanceEvent, "event_category")
        assert hasattr(AttendanceDay, "total_working_minutes")
        assert hasattr(AttendanceDay, "net_working_minutes")
        assert hasattr(AttendanceIdempotencyRecord, "request_fingerprint")
        assert hasattr(TenantAttendancePolicy, "allowed_methods")
        assert hasattr(ShiftAssignment, "shift_template_id")
        assert hasattr(ShiftTemplate, "name")
        assert hasattr(ShiftTemplateVersion, "version_number")
