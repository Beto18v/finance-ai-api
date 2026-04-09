"""add ingestion imports

Revision ID: c8d9e1f2a3b4
Revises: b7c1d2e3f4a5
Create Date: 2026-04-08 18:30:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c8d9e1f2a3b4"
down_revision: str | None = "b7c1d2e3f4a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


import_item_status_enum = postgresql.ENUM(
    "ready",
    "needs_review",
    "duplicate",
    "ignored",
    "imported",
    name="importitemstatus",
    create_type=False,
)
transaction_type_enum = postgresql.ENUM(
    "income",
    "expense",
    "transfer",
    "adjustment",
    name="transactiontype",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    import_item_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "import_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("financial_account_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("file_name", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["financial_account_id"], ["financial_accounts.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_import_sessions_user_created",
        "import_sessions",
        ["user_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "import_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("import_session_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("raw_row", sa.JSON(), nullable=False),
        sa.Column("status", import_item_status_enum, nullable=False),
        sa.Column("status_reason", sa.String(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("occurred_on", sa.Date(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("normalized_description", sa.String(), nullable=True),
        sa.Column("transaction_type", transaction_type_enum, nullable=True),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("duplicate_transaction_id", sa.Uuid(), nullable=True),
        sa.Column("imported_transaction_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.ForeignKeyConstraint(["duplicate_transaction_id"], ["transactions.id"]),
        sa.ForeignKeyConstraint(["import_session_id"], ["import_sessions.id"]),
        sa.ForeignKeyConstraint(["imported_transaction_id"], ["transactions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_import_items_session_row",
        "import_items",
        ["import_session_id", "row_index"],
        unique=True,
    )
    op.create_index(
        "idx_import_items_user_status",
        "import_items",
        ["user_id", "status"],
        unique=False,
    )

    op.execute("ALTER TABLE public.import_sessions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.import_sessions FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.import_items ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.import_items FORCE ROW LEVEL SECURITY")

    op.execute(
        """
        CREATE POLICY import_sessions_select_own
        ON public.import_sessions
        FOR SELECT
        TO authenticated
        USING (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY import_sessions_insert_own
        ON public.import_sessions
        FOR INSERT
        TO authenticated
        WITH CHECK (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY import_sessions_update_own
        ON public.import_sessions
        FOR UPDATE
        TO authenticated
        USING (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        WITH CHECK (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY import_sessions_delete_own
        ON public.import_sessions
        FOR DELETE
        TO authenticated
        USING (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        """
    )

    op.execute(
        """
        CREATE POLICY import_items_select_own
        ON public.import_items
        FOR SELECT
        TO authenticated
        USING (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY import_items_insert_own
        ON public.import_items
        FOR INSERT
        TO authenticated
        WITH CHECK (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY import_items_update_own
        ON public.import_items
        FOR UPDATE
        TO authenticated
        USING (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        WITH CHECK (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY import_items_delete_own
        ON public.import_items
        FOR DELETE
        TO authenticated
        USING (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS import_items_delete_own ON public.import_items")
    op.execute("DROP POLICY IF EXISTS import_items_update_own ON public.import_items")
    op.execute("DROP POLICY IF EXISTS import_items_insert_own ON public.import_items")
    op.execute("DROP POLICY IF EXISTS import_items_select_own ON public.import_items")
    op.execute("DROP POLICY IF EXISTS import_sessions_delete_own ON public.import_sessions")
    op.execute("DROP POLICY IF EXISTS import_sessions_update_own ON public.import_sessions")
    op.execute("DROP POLICY IF EXISTS import_sessions_insert_own ON public.import_sessions")
    op.execute("DROP POLICY IF EXISTS import_sessions_select_own ON public.import_sessions")

    op.execute("ALTER TABLE public.import_items NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.import_items DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.import_sessions NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.import_sessions DISABLE ROW LEVEL SECURITY")

    op.drop_index("idx_import_items_user_status", table_name="import_items")
    op.drop_index("idx_import_items_session_row", table_name="import_items")
    op.drop_table("import_items")

    op.drop_index("idx_import_sessions_user_created", table_name="import_sessions")
    op.drop_table("import_sessions")

    import_item_status_enum.drop(op.get_bind(), checkfirst=True)
