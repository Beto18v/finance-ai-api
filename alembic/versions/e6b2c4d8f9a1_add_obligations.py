"""add obligations

Revision ID: e6b2c4d8f9a1
Revises: a1b2c3d4e5f6
Create Date: 2026-04-07 13:40:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e6b2c4d8f9a1"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


obligation_cadence_enum = postgresql.ENUM(
    "weekly",
    "biweekly",
    "monthly",
    name="obligationcadence",
    create_type=False,
)
obligation_status_enum = postgresql.ENUM(
    "active",
    "paused",
    "archived",
    name="obligationstatus",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    obligation_cadence_enum.create(bind, checkfirst=True)
    obligation_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "obligations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("expected_financial_account_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("cadence", obligation_cadence_enum, nullable=False),
        sa.Column("next_due_date", sa.Date(), nullable=False),
        sa.Column("monthly_anchor_day", sa.Integer(), nullable=True),
        sa.Column(
            "monthly_anchor_is_month_end",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "status",
            obligation_status_enum,
            nullable=False,
            server_default=sa.text("'active'::obligationstatus"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.ForeignKeyConstraint(
            ["expected_financial_account_id"],
            ["financial_accounts.id"],
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("amount > 0", name="ck_obligations_amount_positive"),
        sa.CheckConstraint(
            """
            (
                cadence = 'monthly'
                AND (
                    monthly_anchor_day BETWEEN 1 AND 31
                    OR monthly_anchor_is_month_end
                )
            )
            OR (
                cadence IN ('weekly', 'biweekly')
                AND monthly_anchor_day IS NULL
            )
            """,
            name="ck_obligations_monthly_anchor",
        ),
    )
    op.create_index(
        "idx_obligations_user_status_due",
        "obligations",
        ["user_id", "status", "next_due_date"],
        unique=False,
    )
    op.create_index(
        "idx_obligations_user_category",
        "obligations",
        ["user_id", "category_id"],
        unique=False,
    )
    op.create_index(
        "idx_obligations_user_expected_account",
        "obligations",
        ["user_id", "expected_financial_account_id"],
        unique=False,
    )

    op.execute("ALTER TABLE public.obligations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.obligations FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY obligations_select_own
        ON public.obligations
        FOR SELECT
        TO authenticated
        USING (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY obligations_insert_own
        ON public.obligations
        FOR INSERT
        TO authenticated
        WITH CHECK (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY obligations_update_own
        ON public.obligations
        FOR UPDATE
        TO authenticated
        USING (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        WITH CHECK (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY obligations_delete_own
        ON public.obligations
        FOR DELETE
        TO authenticated
        USING (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS obligations_delete_own ON public.obligations")
    op.execute("DROP POLICY IF EXISTS obligations_update_own ON public.obligations")
    op.execute("DROP POLICY IF EXISTS obligations_insert_own ON public.obligations")
    op.execute("DROP POLICY IF EXISTS obligations_select_own ON public.obligations")
    op.execute("ALTER TABLE public.obligations NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.obligations DISABLE ROW LEVEL SECURITY")

    op.drop_index("idx_obligations_user_expected_account", table_name="obligations")
    op.drop_index("idx_obligations_user_category", table_name="obligations")
    op.drop_index("idx_obligations_user_status_due", table_name="obligations")
    op.drop_table("obligations")

    obligation_status_enum.drop(op.get_bind(), checkfirst=True)
    obligation_cadence_enum.drop(op.get_bind(), checkfirst=True)
