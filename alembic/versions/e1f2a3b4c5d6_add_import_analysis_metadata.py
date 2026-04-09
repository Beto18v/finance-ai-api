"""add import analysis metadata

Revision ID: e1f2a3b4c5d6
Revises: c8d9e1f2a3b4
Create Date: 2026-04-08 19:20:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: str | None = "c8d9e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "import_sessions",
        sa.Column("analysis_metadata", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("import_sessions", "analysis_metadata")
