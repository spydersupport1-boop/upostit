"""Phase 7 Milestone 7.4: HR Fraud Review Queue, Decision Workflows & Audit Ledger.

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-11-19 21:50:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d6e7f8a9b0c1"
down_revision: str | None = "c5d6e7f8a9b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create fraud_reviews table
    op.create_table(
        "fraud_reviews",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("attendance_event_id", sa.UUID(), nullable=False),
        sa.Column("reviewer_user_id", sa.UUID(), nullable=False),
        sa.Column("reviewer_role", sa.String(length=32), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fraud_reviews_tenant_id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "attendance_event_id"],
            ["attendance_events.tenant_id", "attendance_events.id"],
            name="fk_fraud_reviews_event",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "reviewer_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_fraud_reviews_reviewer",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "decision IN ('APPROVED', 'REJECTED')",
            name="chk_fraud_reviews_decision",
        ),
        sa.CheckConstraint(
            "length(trim(reason)) >= 3",
            name="chk_fraud_reviews_reason",
        ),
    )

    op.create_index(
        "ix_fraud_reviews_tenant_event",
        "fraud_reviews",
        ["tenant_id", "attendance_event_id"],
        unique=False,
    )
    op.create_index(
        "ix_fraud_reviews_tenant_reviewer",
        "fraud_reviews",
        ["tenant_id", "reviewer_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_fraud_reviews_tenant_decision",
        "fraud_reviews",
        ["tenant_id", "decision"],
        unique=False,
    )
    op.create_index(
        "ix_fraud_reviews_tenant_decided",
        "fraud_reviews",
        ["tenant_id", "decided_at"],
        unique=False,
    )

    # Enable and force Row-Level Security on fraud_reviews
    op.execute("ALTER TABLE fraud_reviews ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE fraud_reviews FORCE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY tenant_isolation ON fraud_reviews
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
    """)
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON fraud_reviews TO authenticated, service_role;"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON fraud_reviews;")
    op.drop_table("fraud_reviews")

