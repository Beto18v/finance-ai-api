"""enable rls on public tables

Revision ID: 9c2df3d91a7a
Revises: bfc04dbb3e27
Create Date: 2026-03-05 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "9c2df3d91a7a"
down_revision: Union[str, Sequence[str], None] = "bfc04dbb3e27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TABLE public.users ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.categories ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.transactions ENABLE ROW LEVEL SECURITY")

    op.execute("ALTER TABLE public.users FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.categories FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.transactions FORCE ROW LEVEL SECURITY")

    # Uses Supabase JWT claim convention; if claim is missing, expression is NULL -> denied.
    op.execute(
        """
        CREATE POLICY users_select_own
        ON public.users
        FOR SELECT
        TO authenticated
        USING (id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY users_insert_own
        ON public.users
        FOR INSERT
        TO authenticated
        WITH CHECK (id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY users_update_own
        ON public.users
        FOR UPDATE
        TO authenticated
        USING (id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        WITH CHECK (id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY users_delete_own
        ON public.users
        FOR DELETE
        TO authenticated
        USING (id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        """
    )

    op.execute(
        """
        CREATE POLICY categories_select_own
        ON public.categories
        FOR SELECT
        TO authenticated
        USING (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY categories_insert_own
        ON public.categories
        FOR INSERT
        TO authenticated
        WITH CHECK (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY categories_update_own
        ON public.categories
        FOR UPDATE
        TO authenticated
        USING (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        WITH CHECK (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY categories_delete_own
        ON public.categories
        FOR DELETE
        TO authenticated
        USING (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        """
    )

    op.execute(
        """
        CREATE POLICY transactions_select_own
        ON public.transactions
        FOR SELECT
        TO authenticated
        USING (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY transactions_insert_own
        ON public.transactions
        FOR INSERT
        TO authenticated
        WITH CHECK (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY transactions_update_own
        ON public.transactions
        FOR UPDATE
        TO authenticated
        USING (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        WITH CHECK (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY transactions_delete_own
        ON public.transactions
        FOR DELETE
        TO authenticated
        USING (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP POLICY IF EXISTS transactions_delete_own ON public.transactions")
    op.execute("DROP POLICY IF EXISTS transactions_update_own ON public.transactions")
    op.execute("DROP POLICY IF EXISTS transactions_insert_own ON public.transactions")
    op.execute("DROP POLICY IF EXISTS transactions_select_own ON public.transactions")

    op.execute("DROP POLICY IF EXISTS categories_delete_own ON public.categories")
    op.execute("DROP POLICY IF EXISTS categories_update_own ON public.categories")
    op.execute("DROP POLICY IF EXISTS categories_insert_own ON public.categories")
    op.execute("DROP POLICY IF EXISTS categories_select_own ON public.categories")

    op.execute("DROP POLICY IF EXISTS users_delete_own ON public.users")
    op.execute("DROP POLICY IF EXISTS users_update_own ON public.users")
    op.execute("DROP POLICY IF EXISTS users_insert_own ON public.users")
    op.execute("DROP POLICY IF EXISTS users_select_own ON public.users")

    op.execute("ALTER TABLE public.transactions NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.categories NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.users NO FORCE ROW LEVEL SECURITY")

    op.execute("ALTER TABLE public.transactions DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.categories DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.users DISABLE ROW LEVEL SECURITY")
