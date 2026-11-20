"""Phase 9.4: Overtime rule default & pre-approval enhancements and record rule association.

Revision ID: a4b5c6d7e8f9
Revises: f2a3b4c5d6e7
Create Date: 2026-11-20 14:18:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4b5c6d7e8f9"
down_revision: str | None = "f2a3b4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add is_default and requires_pre_approval to overtime_rules
    op.add_column(
        "overtime_rules",
        sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "overtime_rules",
        sa.Column("requires_pre_approval", sa.Boolean(), server_default="false", nullable=False),
    )
    op.create_index(
        "ix_overtime_rules_tenant_default",
        "overtime_rules",
        ["tenant_id", "is_default"],
        unique=False,
    )

    # 2. Add overtime_rule_id to overtime_records
    op.add_column(
        "overtime_records",
        sa.Column("overtime_rule_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_overtime_records_rule",
        "overtime_records",
        "overtime_rules",
        ["tenant_id", "overtime_rule_id"],
        ["tenant_id", "id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_overtime_records_tenant_rule",
        "overtime_records",
        ["tenant_id", "overtime_rule_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_overtime_records_tenant_rule", table_name="overtime_records")
    op.drop_constraint("fk_overtime_records_rule", "overtime_records", type_="foreignkey")
    op.drop_column("overtime_records", "overtime_rule_id")

    op.drop_index("ix_overtime_rules_tenant_default", table_name="overtime_rules")
    op.drop_column("overtime_rules", "requires_pre_approval")
    op.drop_column("overtime_rules", "is_default")

