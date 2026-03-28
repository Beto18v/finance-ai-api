"""enforce positive transaction amount

Revision ID: f7c9a12b4d3e
Revises: a9f1c3d4e5b6
Create Date: 2026-03-27 20:00:00.000000

"""

from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f7c9a12b4d3e"
down_revision: str | None = "a9f1c3d4e5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_transactions_amount_positive",
        "transactions",
        "amount > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_transactions_amount_positive",
        "transactions",
        type_="check",
    )
