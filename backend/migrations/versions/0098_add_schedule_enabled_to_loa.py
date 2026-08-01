"""Add schedule_enabled column to load_sequences.

Revision ID: 0098_add_schedule_enabled_to_loa
Revises: 0097_add_schedule_cadence_to_loa
"""

from alembic import op

revision = "0098_add_schedule_enabled_to_loa"
down_revision = "0097_add_schedule_cadence_to_loa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "load_sequences" ADD COLUMN IF NOT EXISTS "schedule_enabled" BOOLEAN'
    )


def downgrade() -> None:
    op.execute('ALTER TABLE "load_sequences" DROP COLUMN IF EXISTS "schedule_enabled"')
