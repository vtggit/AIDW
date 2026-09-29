"""Add idx_sequence_runs_stranded_scheduled partial index on sequence_runs(updated_at).

Partial index for the worker reaper (reap_stranded_scheduled in app/worker/loop.py),
whose UPDATE filters on triggered_by/status/started_at and range-scans updated_at:
WHERE triggered_by = 'schedule' AND status = 'pending' AND started_at IS NOT NULL.

Revision ID: 0103_add_idx_sequence_runs_reap
Revises: 0102_add_feed_credentials
"""

from alembic import op

revision = "0103_add_idx_sequence_runs_reap"
down_revision = "0102_add_feed_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_sequence_runs_stranded_scheduled" '
        'ON "sequence_runs" ("updated_at") '
        "WHERE triggered_by = 'schedule' AND status = 'pending' "
        "AND started_at IS NOT NULL"
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_sequence_runs_stranded_scheduled"')
