"""Add uq_sequence_runs_sequence_id_partial index on sequence_runs(sequence_id).

Revision ID: 0094_add_uq_sequence_runs_sequen
Revises: 0093_add_idx_sequence_runs_seque
"""

from alembic import op

revision = "0094_add_uq_sequence_runs_sequen"
down_revision = "0093_add_idx_sequence_runs_seque"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS "uq_sequence_runs_sequence_id_partial" ON "sequence_runs" ("sequence_id") WHERE "status" IN (\'pending\', \'running\')'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "uq_sequence_runs_sequence_id_partial"')
