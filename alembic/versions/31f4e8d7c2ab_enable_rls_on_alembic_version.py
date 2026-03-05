"""enable rls on alembic version table

Revision ID: 31f4e8d7c2ab
Revises: 9c2df3d91a7a
Create Date: 2026-03-05 00:00:01.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "31f4e8d7c2ab"
down_revision: Union[str, Sequence[str], None] = "9c2df3d91a7a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TABLE public.alembic_version ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER TABLE public.alembic_version DISABLE ROW LEVEL SECURITY")
