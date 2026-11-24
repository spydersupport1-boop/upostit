"""Phase 11 Milestone 11.5: Multi-Device Attendance Conflict Detection, Arbitration & Resolution.

Revision ID: c1d2e3f4a5b6
Revises: b5c6d7e8f9a0
Create Date: 2026-11-24 00:50:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: str | None = "b5c6d7e8f9a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add Phase 11.5 multi-device columns to attendance_conflict_incidents
    op.add_column(
        "attendance_conflict_incidents",
        sa.Column("conflict_code", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "attendance_conflict_incidents",
        sa.Column(
            "severity",
            sa.String(length=20),
            server_default="MEDIUM",
            nullable=False,
        ),
    )
    op.add_column(
        "attendance_conflict_incidents",
        sa.Column(
            "classification",
            sa.String(length=40),
            server_default="NEEDS_MANAGER_REVIEW",
            nullable=False,
        ),
    )
    op.add_column(
        "attendance_conflict_incidents",
        sa.Column("employee_clarification", sa.Text(), nullable=True),
    )
    op.add_column(
        "attendance_conflict_incidents",
        sa.Column("clarification_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "attendance_conflict_incidents",
        sa.Column("clarification_submitted_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 2. Add performance index on conflict_code and severity
    op.create_index(
        "ix_conflict_incidents_tenant_code",
        "attendance_conflict_incidents",
        ["tenant_id", "conflict_code"],
        unique=False,
    )
    op.create_index(
        "ix_conflict_incidents_tenant_severity",
        "attendance_conflict_incidents",
        ["tenant_id", "severity"],
        unique=False,
    )

    # 3. Update check constraints to support Phase 11.5 lifecycle statuses and decisions
    op.drop_constraint(
        "chk_conflict_incidents_status",
        "attendance_conflict_incidents",
        type_="check",
    )
    op.create_check_constraint(
        "chk_conflict_incidents_status",
        "attendance_conflict_incidents",
        "status IN ('PENDING_REVIEW', 'APPROVED', 'REJECTED', 'NEEDS_CLARIFICATION', 'UNRESOLVED', 'ESCALATED_HR', 'AUTO_RESOLVED')",
    )

    op.drop_constraint(
        "chk_conflict_incidents_decision",
        "attendance_conflict_incidents",
        type_="check",
    )
    op.create_check_constraint(
        "chk_conflict_incidents_decision",
        "attendance_conflict_incidents",
        "decision IS NULL OR decision IN ('APPROVED', 'REJECTED', 'ACCEPT_SEQUENCE', 'REJECT_INVALID_EVENTS', 'REQUEST_CLARIFICATION', 'MARK_UNRESOLVED', 'ESCALATE_HR')",
    )

    op.create_check_constraint(
        "chk_conflict_incidents_severity",
        "attendance_conflict_incidents",
        "severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
    )

    op.drop_constraint(
        "chk_conflict_incidents_status_decision",
        "attendance_conflict_incidents",
        type_="check",
    )


def downgrade() -> None:
    op.drop_constraint(
        "chk_conflict_incidents_severity",
        "attendance_conflict_incidents",
        type_="check",
    )
    op.drop_constraint(
        "chk_conflict_incidents_decision",
        "attendance_conflict_incidents",
        type_="check",
    )
    op.drop_constraint(
        "chk_conflict_incidents_status",
        "attendance_conflict_incidents",
        type_="check",
    )

    op.create_check_constraint(
        "chk_conflict_incidents_status",
        "attendance_conflict_incidents",
        "status IN ('PENDING_REVIEW', 'APPROVED', 'REJECTED')",
    )
    op.create_check_constraint(
        "chk_conflict_incidents_decision",
        "attendance_conflict_incidents",
        "decision IS NULL OR decision IN ('APPROVED', 'REJECTED')",
    )
    op.create_check_constraint(
        "chk_conflict_incidents_status_decision",
        "attendance_conflict_incidents",
        "(status = 'PENDING_REVIEW' AND decision IS NULL AND decided_at IS NULL AND reviewer_user_id IS NULL) OR "
        "(status = 'APPROVED' AND decision = 'APPROVED' AND decided_at IS NOT NULL AND reviewer_user_id IS NOT NULL) OR "
        "(status = 'REJECTED' AND decision = 'REJECTED' AND decided_at IS NOT NULL AND reviewer_user_id IS NOT NULL)",
    )

    op.drop_index("ix_conflict_incidents_tenant_severity", table_name="attendance_conflict_incidents")
    op.drop_index("ix_conflict_incidents_tenant_code", table_name="attendance_conflict_incidents")

    op.drop_column("attendance_conflict_incidents", "clarification_submitted_at")
    op.drop_column("attendance_conflict_incidents", "clarification_requested_at")
    op.drop_column("attendance_conflict_incidents", "employee_clarification")
    op.drop_column("attendance_conflict_incidents", "classification")
    op.drop_column("attendance_conflict_incidents", "severity")
    op.drop_column("attendance_conflict_incidents", "conflict_code")

