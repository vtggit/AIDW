"""Add idx_sequence_runs_sequence_id_status index on sequence_runs(sequence_id, status).

Revision ID: 0093_add_idx_sequence_runs_seque
Revises: 0092_add_sequence_runs
"""

from alembic import op

revision = "0093_add_idx_sequence_runs_seque"
down_revision = "0092_add_sequence_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_sequence_runs_sequence_id_status" ON "sequence_runs" ("sequence_id", "status")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_sequence_runs_sequence_id_status"')
