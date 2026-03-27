"""merge heads after fx snapshot

Revision ID: f3c4e5d6a7b8
Revises: 6bf0f8578784, a9f1c3d4e5b6
Create Date: 2026-03-25 20:35:00.000000

"""

from collections.abc import Sequence


# revision identifiers, used by Alembic.
revision: str = "f3c4e5d6a7b8"
down_revision: tuple[str, str] = ("6bf0f8578784", "a9f1c3d4e5b6")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
