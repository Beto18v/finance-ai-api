"""add accounts and transaction types

Revision ID: 4c4e2e9f6b1a
Revises: 9ed2333b023d
Create Date: 2026-03-30 21:00:00.000000

"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4c4e2e9f6b1a"
down_revision: str | None = "9ed2333b023d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


transaction_type_enum = sa.Enum(
    "income",
    "expense",
    "transfer",
    "adjustment",
    name="transactiontype",
)


def upgrade() -> None:
    bind = op.get_bind()
    transaction_type_enum.create(bind, checkfirst=True)

    op.create_table(
        "financial_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_financial_accounts_user",
        "financial_accounts",
        ["user_id"],
        unique=False,
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_financial_accounts_default_per_user
        ON public.financial_accounts (user_id)
        WHERE is_default
        """
    )

    op.add_column(
        "transactions",
        sa.Column("financial_account_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("transaction_type", transaction_type_enum, nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("transfer_group_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_transactions_financial_account_id_financial_accounts",
        "transactions",
        "financial_accounts",
        ["financial_account_id"],
        ["id"],
    )
    op.alter_column("transactions", "category_id", existing_type=sa.Uuid(), nullable=True)

    financial_accounts_table = sa.table(
        "financial_accounts",
        sa.column("id", sa.Uuid()),
        sa.column("user_id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("currency", sa.String(length=3)),
        sa.column("is_default", sa.Boolean()),
    )

    users = bind.execute(
        sa.text(
            """
            SELECT id, base_currency
            FROM public.users
            """
        )
    ).mappings()
    financial_account_rows = [
        {
            "id": uuid.uuid4(),
            "user_id": user["id"],
            "name": "Main account",
            "currency": user["base_currency"],
            "is_default": True,
        }
        for user in users
    ]
    if financial_account_rows:
        op.bulk_insert(financial_accounts_table, financial_account_rows)

    op.execute(
        """
        UPDATE public.transactions AS transactions
        SET financial_account_id = financial_accounts.id
        FROM public.financial_accounts AS financial_accounts
        WHERE transactions.user_id = financial_accounts.user_id
          AND financial_accounts.is_default
          AND transactions.financial_account_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE public.transactions AS transactions
        SET transaction_type = categories.direction::text::transactiontype
        FROM public.categories AS categories
        WHERE transactions.category_id = categories.id
          AND transactions.transaction_type IS NULL
        """
    )

    op.alter_column(
        "transactions",
        "financial_account_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.alter_column(
        "transactions",
        "transaction_type",
        existing_type=transaction_type_enum,
        nullable=False,
    )
    op.create_index(
        "idx_transactions_user_financial_account",
        "transactions",
        ["user_id", "financial_account_id"],
        unique=False,
    )
    op.create_index(
        "idx_transactions_transfer_group",
        "transactions",
        ["transfer_group_id"],
        unique=False,
    )

    op.execute("ALTER TABLE public.financial_accounts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.financial_accounts FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY financial_accounts_select_own
        ON public.financial_accounts
        FOR SELECT
        TO authenticated
        USING (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY financial_accounts_insert_own
        ON public.financial_accounts
        FOR INSERT
        TO authenticated
        WITH CHECK (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY financial_accounts_update_own
        ON public.financial_accounts
        FOR UPDATE
        TO authenticated
        USING (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        WITH CHECK (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY financial_accounts_delete_own
        ON public.financial_accounts
        FOR DELETE
        TO authenticated
        USING (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS financial_accounts_delete_own ON public.financial_accounts")
    op.execute("DROP POLICY IF EXISTS financial_accounts_update_own ON public.financial_accounts")
    op.execute("DROP POLICY IF EXISTS financial_accounts_insert_own ON public.financial_accounts")
    op.execute("DROP POLICY IF EXISTS financial_accounts_select_own ON public.financial_accounts")
    op.execute("ALTER TABLE public.financial_accounts NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.financial_accounts DISABLE ROW LEVEL SECURITY")

    op.drop_index("idx_transactions_transfer_group", table_name="transactions")
    op.drop_index(
        "idx_transactions_user_financial_account",
        table_name="transactions",
    )
    op.alter_column("transactions", "category_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_constraint(
        "fk_transactions_financial_account_id_financial_accounts",
        "transactions",
        type_="foreignkey",
    )
    op.drop_column("transactions", "transfer_group_id")
    op.drop_column("transactions", "transaction_type")
    op.drop_column("transactions", "financial_account_id")

    op.execute("DROP INDEX IF EXISTS public.uq_financial_accounts_default_per_user")
    op.drop_index("idx_financial_accounts_user", table_name="financial_accounts")
    op.drop_table("financial_accounts")

    transaction_type_enum.drop(op.get_bind(), checkfirst=True)
