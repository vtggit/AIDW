"""Add uq_process_steps_process_definition_id_step_key index on process_steps(process_definition_id, step_key).

Revision ID: 0069_add_uq_process_steps_proces
Revises: 0068_add_process_definition_id_t
"""

from alembic import op

revision = "0069_add_uq_process_steps_proces"
down_revision = "0068_add_process_definition_id_t"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS "uq_process_steps_process_definition_id_step_key" ON "process_steps" ("process_definition_id", "step_key")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "uq_process_steps_process_definition_id_step_key"')
