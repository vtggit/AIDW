"""Add triggered_by column to sequence_runs.

Revision ID: 0101_add_triggered_by_to_sequenc
Revises: 0100_add_idx_load_sequences_sche
"""

from alembic import op

revision = "0101_add_triggered_by_to_sequenc"
down_revision = "0100_add_idx_load_sequences_sche"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "sequence_runs" ADD COLUMN IF NOT EXISTS "triggered_by" TEXT'
    )


def downgrade() -> None:
    op.execute('ALTER TABLE "sequence_runs" DROP COLUMN IF EXISTS "triggered_by"')
