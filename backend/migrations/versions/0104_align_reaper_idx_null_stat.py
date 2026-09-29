"""Recreate idx_sequence_runs_stranded_scheduled with a NULL-tolerant predicate.

The #632 predicate (status = 'pending') missed scheduled runs whose status is
NULL, so the reaper UPDATE (COALESCE(status, 'pending') = 'pending', issue #648)
had no matching partial index. Drop the index and recreate it under the same
name on sequence_runs(updated_at) with the aligned predicate.

Revision ID: 0104_align_reaper_idx_null_stat
Revises: 0103_add_idx_sequence_runs_reap
"""

from alembic import op

revision = "0104_align_reaper_idx_null_stat"
down_revision = "0103_add_idx_sequence_runs_reap"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_sequence_runs_stranded_scheduled"')
    op.execute(
        'CREATE INDEX "idx_sequence_runs_stranded_scheduled" '
        'ON "sequence_runs" ("updated_at") '
        "WHERE triggered_by = 'schedule' AND COALESCE(status, 'pending') = 'pending' "
        "AND started_at IS NOT NULL"
    )


def downgrade() -> None:
    # Restore the #632 definition (status = 'pending').
    op.execute('DROP INDEX IF EXISTS "idx_sequence_runs_stranded_scheduled"')
    op.execute(
        'CREATE INDEX "idx_sequence_runs_stranded_scheduled" '
        'ON "sequence_runs" ("updated_at") '
        "WHERE triggered_by = 'schedule' AND status = 'pending' "
        "AND started_at IS NOT NULL"
    )
