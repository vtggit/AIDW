"""Add grid_col_span column to dashboard_items.

Revision ID: 0080_add_grid_col_span_to_dashbo
Revises: 0079_add_retry_limit_to_process
"""

from alembic import op

revision = "0080_add_grid_col_span_to_dashbo"
down_revision = "0079_add_retry_limit_to_process"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "dashboard_items" ADD COLUMN IF NOT EXISTS "grid_col_span" INTEGER'
    )
    op.execute(
        """DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_dashboard_items_grid_col_span') THEN ALTER TABLE "dashboard_items" ADD CONSTRAINT "chk_dashboard_items_grid_col_span" CHECK ("grid_col_span" BETWEEN 1 AND 12); END IF; END $$;"""
    )


def downgrade() -> None:
    op.execute(
        'ALTER TABLE "dashboard_items" DROP CONSTRAINT IF EXISTS "chk_dashboard_items_grid_col_span"'
    )
    op.execute('ALTER TABLE "dashboard_items" DROP COLUMN IF EXISTS "grid_col_span"')
