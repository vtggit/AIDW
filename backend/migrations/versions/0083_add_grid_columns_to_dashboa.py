"""Add grid_columns column to dashboards.

Revision ID: 0083_add_grid_columns_to_dashboa
Revises: 0082_add_grid_row_span_to_dashbo
"""

from alembic import op

revision = "0083_add_grid_columns_to_dashboa"
down_revision = "0082_add_grid_row_span_to_dashbo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "dashboards" ADD COLUMN IF NOT EXISTS "grid_columns" INTEGER'
    )
    op.execute(
        """DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_dashboards_grid_columns') THEN ALTER TABLE "dashboards" ADD CONSTRAINT "chk_dashboards_grid_columns" CHECK ("grid_columns" BETWEEN 1 AND 12); END IF; END $$;"""
    )


def downgrade() -> None:
    op.execute(
        'ALTER TABLE "dashboards" DROP CONSTRAINT IF EXISTS "chk_dashboards_grid_columns"'
    )
    op.execute('ALTER TABLE "dashboards" DROP COLUMN IF EXISTS "grid_columns"')
