"""add obligation recurring candidate key

Revision ID: b7c1d2e3f4a5
Revises: e6b2c4d8f9a1
Create Date: 2026-04-07 18:25:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7c1d2e3f4a5"
down_revision: str | None = "e6b2c4d8f9a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "obligations",
        sa.Column("source_recurring_candidate_key", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "idx_obligations_user_recurring_candidate_key",
        "obligations",
        ["user_id", "source_recurring_candidate_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_obligations_user_recurring_candidate_key",
        table_name="obligations",
    )
    op.drop_column("obligations", "source_recurring_candidate_key")
