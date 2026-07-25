"""Add grid_col_start column to dashboard_item_layouts.

Revision ID: 0086_add_grid_col_start_to_dashb
Revises: 0085_add_grid_col_span_to_dashbo
"""

from alembic import op

revision = "0086_add_grid_col_start_to_dashb"
down_revision = "0085_add_grid_col_span_to_dashbo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "dashboard_item_layouts" ADD COLUMN IF NOT EXISTS "grid_col_start" INTEGER'
    )
    op.execute(
        """DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_dashboard_item_layouts_grid_col_start') THEN ALTER TABLE "dashboard_item_layouts" ADD CONSTRAINT "chk_dashboard_item_layouts_grid_col_start" CHECK ("grid_col_start" > 0); END IF; END $$;"""
    )


def downgrade() -> None:
    op.execute(
        'ALTER TABLE "dashboard_item_layouts" DROP CONSTRAINT IF EXISTS "chk_dashboard_item_layouts_grid_col_start"'
    )
    op.execute(
        'ALTER TABLE "dashboard_item_layouts" DROP COLUMN IF EXISTS "grid_col_start"'
    )
