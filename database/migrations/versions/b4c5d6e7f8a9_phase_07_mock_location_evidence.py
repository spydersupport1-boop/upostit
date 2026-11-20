"""Phase 7 Milestone 7.2: Add is_mock_location evidence column to attendance_events.

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-11-19 03:45:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4c5d6e7f8a9"
down_revision: str | None = "a3b4c5d6e7f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "attendance_events",
        sa.Column(
            "is_mock_location",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("attendance_events", "is_mock_location")

