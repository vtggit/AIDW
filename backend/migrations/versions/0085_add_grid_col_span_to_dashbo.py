"""Add grid_col_span column to dashboard_item_layouts.

Revision ID: 0085_add_grid_col_span_to_dashbo
Revises: 0084_add_dashboard_item_layouts
"""

from alembic import op

revision = "0085_add_grid_col_span_to_dashbo"
down_revision = "0084_add_dashboard_item_layouts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "dashboard_item_layouts" ADD COLUMN IF NOT EXISTS "grid_col_span" INTEGER'
    )
    op.execute(
        """DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_dashboard_item_layouts_grid_col_span') THEN ALTER TABLE "dashboard_item_layouts" ADD CONSTRAINT "chk_dashboard_item_layouts_grid_col_span" CHECK ("grid_col_span" BETWEEN 1 AND 12); END IF; END $$;"""
    )


def downgrade() -> None:
    op.execute(
        'ALTER TABLE "dashboard_item_layouts" DROP CONSTRAINT IF EXISTS "chk_dashboard_item_layouts_grid_col_span"'
    )
    op.execute(
        'ALTER TABLE "dashboard_item_layouts" DROP COLUMN IF EXISTS "grid_col_span"'
    )
