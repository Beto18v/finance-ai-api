"""add policy to alembic_version

Revision ID: c1a2d3e4f5a6
Revises: 31f4e8d7c2ab
Create Date: 2026-03-05 00:00:02.000000

"""

from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c1a2d3e4f5a6"
down_revision: str | Sequence[str] | None = "31f4e8d7c2ab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Keep RLS enabled (as requested), but add at least one policy to satisfy
    # Supabase Security Advisor and to avoid accidentally exposing this table.
    op.execute("ALTER TABLE public.alembic_version ENABLE ROW LEVEL SECURITY")

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_policies
                WHERE schemaname = 'public'
                  AND tablename = 'alembic_version'
                  AND policyname = 'alembic_version_service_role_all'
            ) THEN
                CREATE POLICY alembic_version_service_role_all
                ON public.alembic_version
                FOR ALL
                TO service_role
                USING (true)
                WITH CHECK (true);
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "DROP POLICY IF EXISTS alembic_version_service_role_all ON public.alembic_version"
    )
