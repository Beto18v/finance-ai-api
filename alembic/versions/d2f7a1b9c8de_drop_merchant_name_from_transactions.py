"""drop merchant_name from transactions

Revision ID: d2f7a1b9c8de
Revises: c1a2d3e4f5a6
Create Date: 2026-03-06 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d2f7a1b9c8de"
down_revision: Union[str, Sequence[str], None] = "c1a2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column("transactions", "merchant_name")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("transactions", sa.Column("merchant_name", sa.String(), nullable=True))
