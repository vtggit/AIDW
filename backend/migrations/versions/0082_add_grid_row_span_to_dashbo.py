"""Add grid_row_span column to dashboard_items.

Revision ID: 0082_add_grid_row_span_to_dashbo
Revises: 0081_add_grid_col_start_to_dashb
"""

from alembic import op

revision = "0082_add_grid_row_span_to_dashbo"
down_revision = "0081_add_grid_col_start_to_dashb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "dashboard_items" ADD COLUMN IF NOT EXISTS "grid_row_span" INTEGER'
    )
    op.execute(
        """DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_dashboard_items_grid_row_span') THEN ALTER TABLE "dashboard_items" ADD CONSTRAINT "chk_dashboard_items_grid_row_span" CHECK ("grid_row_span" BETWEEN 1 AND 6); END IF; END $$;"""
    )


def downgrade() -> None:
    op.execute(
        'ALTER TABLE "dashboard_items" DROP CONSTRAINT IF EXISTS "chk_dashboard_items_grid_row_span"'
    )
    op.execute('ALTER TABLE "dashboard_items" DROP COLUMN IF EXISTS "grid_row_span"')
