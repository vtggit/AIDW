"""Add last_fired_at column to load_sequences.

Revision ID: 0099_add_last_fired_at_to_load_s
Revises: 0098_add_schedule_enabled_to_loa
"""

from alembic import op

revision = "0099_add_last_fired_at_to_load_s"
down_revision = "0098_add_schedule_enabled_to_loa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "load_sequences" ADD COLUMN IF NOT EXISTS "last_fired_at" TIMESTAMP WITH TIME ZONE'
    )


def downgrade() -> None:
    op.execute('ALTER TABLE "load_sequences" DROP COLUMN IF EXISTS "last_fired_at"')
