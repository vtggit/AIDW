"""Add grid_row_span column to dashboard_item_layouts.

Revision ID: 0087_add_grid_row_span_to_dashbo
Revises: 0086_add_grid_col_start_to_dashb
"""

from alembic import op

revision = "0087_add_grid_row_span_to_dashbo"
down_revision = "0086_add_grid_col_start_to_dashb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "dashboard_item_layouts" ADD COLUMN IF NOT EXISTS "grid_row_span" INTEGER'
    )
    op.execute(
        """DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_dashboard_item_layouts_grid_row_span') THEN ALTER TABLE "dashboard_item_layouts" ADD CONSTRAINT "chk_dashboard_item_layouts_grid_row_span" CHECK ("grid_row_span" BETWEEN 1 AND 6); END IF; END $$;"""
    )


def downgrade() -> None:
    op.execute(
        'ALTER TABLE "dashboard_item_layouts" DROP CONSTRAINT IF EXISTS "chk_dashboard_item_layouts_grid_row_span"'
    )
    op.execute(
        'ALTER TABLE "dashboard_item_layouts" DROP COLUMN IF EXISTS "grid_row_span"'
    )
