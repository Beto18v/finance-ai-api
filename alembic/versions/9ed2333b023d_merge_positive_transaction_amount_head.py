"""merge positive transaction amount head

Revision ID: 9ed2333b023d
Revises: f3c4e5d6a7b8, f7c9a12b4d3e
Create Date: 2026-03-27 20:15:12.164978

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9ed2333b023d'
down_revision: Union[str, Sequence[str], None] = ('f3c4e5d6a7b8', 'f7c9a12b4d3e')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
