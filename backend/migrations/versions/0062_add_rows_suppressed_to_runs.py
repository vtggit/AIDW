"""Add rows_suppressed column to runs.

Revision ID: 0062_add_rows_suppressed_to_runs
Revises: 0061_add_deletion_request_id_to
"""

from alembic import op

revision = "0062_add_rows_suppressed_to_runs"
down_revision = "0061_add_deletion_request_id_to"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('ALTER TABLE "runs" ADD COLUMN IF NOT EXISTS "rows_suppressed" INTEGER')


def downgrade() -> None:
    op.execute('ALTER TABLE "runs" DROP COLUMN IF EXISTS "rows_suppressed"')
