"""add user money profile and fx snapshots

Revision ID: a9f1c3d4e5b6
Revises: 31f4e8d7c2ab
Create Date: 2026-03-25 20:30:00.000000

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a9f1c3d4e5b6"
down_revision: str | None = "31f4e8d7c2ab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("base_currency", sa.String(length=3), nullable=True))
    op.add_column("users", sa.Column("timezone", sa.String(length=64), nullable=True))

    op.add_column("transactions", sa.Column("fx_rate", sa.Numeric(precision=18, scale=8), nullable=True))
    op.add_column("transactions", sa.Column("fx_rate_date", sa.Date(), nullable=True))
    op.add_column("transactions", sa.Column("fx_rate_source", sa.String(length=64), nullable=True))
    op.add_column("transactions", sa.Column("base_currency", sa.String(length=3), nullable=True))
    op.add_column(
        "transactions",
        sa.Column("amount_in_base_currency", sa.Numeric(precision=14, scale=2), nullable=True),
    )

    op.create_table(
        "exchange_rates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("base_currency", sa.String(length=3), nullable=False),
        sa.Column("quote_currency", sa.String(length=3), nullable=False),
        sa.Column("rate_date", sa.Date(), nullable=False),
        sa.Column("rate", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "base_currency",
            "quote_currency",
            "rate_date",
            "source",
            name="uq_exchange_rates_pair_date_source",
        ),
    )
    op.create_index(
        "idx_exchange_rates_lookup",
        "exchange_rates",
        ["base_currency", "quote_currency", "rate_date"],
        unique=False,
    )

    op.execute(
        """
        WITH inferred_base AS (
            SELECT
                user_id,
                MIN(currency) AS inferred_currency
            FROM public.transactions
            GROUP BY user_id
            HAVING COUNT(DISTINCT currency) = 1
        )
        UPDATE public.users AS users
        SET base_currency = inferred_base.inferred_currency
        FROM inferred_base
        WHERE users.id = inferred_base.user_id
          AND users.base_currency IS NULL
        """
    )

    op.execute(
        """
        UPDATE public.transactions AS transactions
        SET base_currency = users.base_currency
        FROM public.users AS users
        WHERE transactions.user_id = users.id
          AND users.base_currency IS NOT NULL
          AND transactions.base_currency IS NULL
        """
    )

    op.execute(
        """
        UPDATE public.transactions AS transactions
        SET
            fx_rate = 1.00000000,
            fx_rate_date = DATE(transactions.occurred_at AT TIME ZONE 'UTC'),
            fx_rate_source = 'identity',
            amount_in_base_currency = transactions.amount
        FROM public.users AS users
        WHERE transactions.user_id = users.id
          AND users.base_currency IS NOT NULL
          AND transactions.currency = users.base_currency
        """
    )


def downgrade() -> None:
    op.drop_index("idx_exchange_rates_lookup", table_name="exchange_rates")
    op.drop_table("exchange_rates")

    op.drop_column("transactions", "amount_in_base_currency")
    op.drop_column("transactions", "base_currency")
    op.drop_column("transactions", "fx_rate_source")
    op.drop_column("transactions", "fx_rate_date")
    op.drop_column("transactions", "fx_rate")

    op.drop_column("users", "timezone")
    op.drop_column("users", "base_currency")
