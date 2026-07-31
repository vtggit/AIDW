"""Add uq_sequence_run_steps_run_id_step_id index on sequence_run_steps(run_id, step_id).

Revision ID: 0096_add_uq_sequence_run_steps_r
Revises: 0095_add_sequence_run_steps
"""

from alembic import op

revision = "0096_add_uq_sequence_run_steps_r"
down_revision = "0095_add_sequence_run_steps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS "uq_sequence_run_steps_run_id_step_id" ON "sequence_run_steps" ("run_id", "step_id")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "uq_sequence_run_steps_run_id_step_id"')
