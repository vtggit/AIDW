"""Add idx_load_sequences_schedule_enabled index on load_sequences(schedule_enabled).

Revision ID: 0100_add_idx_load_sequences_sche
Revises: 0099_add_last_fired_at_to_load_s
"""

from alembic import op

revision = "0100_add_idx_load_sequences_sche"
down_revision = "0099_add_last_fired_at_to_load_s"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_load_sequences_schedule_enabled" ON "load_sequences" ("schedule_enabled")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_load_sequences_schedule_enabled"')
