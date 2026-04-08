"""add balance direction for ledger

Revision ID: a1b2c3d4e5f6
Revises: 4c4e2e9f6b1a
Create Date: 2026-04-06 22:30:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "4c4e2e9f6b1a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


balance_direction_enum = sa.Enum("in", "out", name="balancedirection")


def upgrade() -> None:
    bind = op.get_bind()
    balance_direction_enum.create(bind, checkfirst=True)

    op.add_column(
        "transactions",
        sa.Column("balance_direction", balance_direction_enum, nullable=True),
    )

    _backfill_income_and_expense(bind)
    _raise_for_legacy_ledger_rows(bind)
    _raise_for_remaining_null_balance_directions(bind)

    op.alter_column(
        "transactions",
        "balance_direction",
        existing_type=balance_direction_enum,
        nullable=False,
    )
    op.create_check_constraint(
        "ck_transactions_balance_direction_matches_type",
        "transactions",
        """
        (transaction_type = 'income' AND balance_direction = 'in')
        OR (transaction_type = 'expense' AND balance_direction = 'out')
        OR (
            transaction_type IN ('transfer', 'adjustment')
            AND balance_direction IN ('in', 'out')
        )
        """,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_transactions_balance_direction_matches_type",
        "transactions",
        type_="check",
    )
    op.drop_column("transactions", "balance_direction")
    balance_direction_enum.drop(op.get_bind(), checkfirst=True)


def _backfill_income_and_expense(bind) -> None:
    bind.execute(
        sa.text(
            """
            UPDATE public.transactions
            SET balance_direction = CASE
                WHEN transaction_type = 'income' THEN 'in'::balancedirection
                WHEN transaction_type = 'expense' THEN 'out'::balancedirection
                ELSE balance_direction
            END
            """
        )
    )


def _raise_for_legacy_ledger_rows(bind) -> None:
    legacy_rows = _fetch_legacy_ledger_rows(bind)
    _raise_for_detected_legacy_ledger_rows(legacy_rows)


def _fetch_legacy_ledger_rows(bind) -> list[dict[str, str | None]]:
    rows = bind.execute(
        sa.text(
            """
            SELECT
                id::text AS id,
                transaction_type::text AS transaction_type,
                transfer_group_id::text AS transfer_group_id
            FROM public.transactions
            WHERE transaction_type IN ('transfer', 'adjustment')
            ORDER BY occurred_at ASC, created_at ASC NULLS LAST, id ASC
            """
        )
    ).mappings()
    return [dict(row) for row in rows]


def _raise_for_detected_legacy_ledger_rows(
    legacy_rows: list[dict[str, str | None]],
) -> None:
    if not legacy_rows:
        return

    formatted_rows = ", ".join(
        _format_legacy_row(row)
        for row in legacy_rows[:10]
    )
    if len(legacy_rows) > 10:
        formatted_rows = f"{formatted_rows}, ... ({len(legacy_rows)} total)"

    raise RuntimeError(
        "Migration cannot infer balance_direction for legacy transfer/"
        "adjustment rows created before transfer and adjustment flows were "
        "supported end to end. The safe path is to clean or manually "
        "backfill that data outside the migration before "
        f"rerunning it. Rows detected: {formatted_rows}"
    )


def _format_legacy_row(row: dict[str, str | None]) -> str:
    if row["transaction_type"] == "transfer":
        transfer_group_id = row["transfer_group_id"] or "<null>"
        return f"{row['id']} (transfer group {transfer_group_id})"
    return f"{row['id']} (adjustment)"


def _raise_for_remaining_null_balance_directions(bind) -> None:
    remaining_null_count = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM public.transactions
            WHERE balance_direction IS NULL
            """
        )
    ).scalar_one()
    if remaining_null_count == 0:
        return

    raise RuntimeError(
        "Migration left transactions.balance_direction as NULL for "
        f"{remaining_null_count} rows. Complete the legacy backfill and retry."
    )
