"""Add schedule_cadence column to load_sequences.

Revision ID: 0097_add_schedule_cadence_to_loa
Revises: 0096_add_uq_sequence_run_steps_r
"""

from alembic import op

revision = "0097_add_schedule_cadence_to_loa"
down_revision = "0096_add_uq_sequence_run_steps_r"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "load_sequences" ADD COLUMN IF NOT EXISTS "schedule_cadence" TEXT'
    )


def downgrade() -> None:
    op.execute('ALTER TABLE "load_sequences" DROP COLUMN IF EXISTS "schedule_cadence"')
