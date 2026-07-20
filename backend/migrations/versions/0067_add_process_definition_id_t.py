"""Add process_definition_id column to process_steps.

Revision ID: 0067_add_process_definition_id_t
Revises: 0066_add_sequence_flows
"""

from alembic import op

revision = "0067_add_process_definition_id_t"
down_revision = "0066_add_sequence_flows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "process_steps" ADD COLUMN IF NOT EXISTS "process_definition_id" VARCHAR(64) REFERENCES "process_definitions"("id") ON DELETE SET NULL'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_process_steps_process_definition_id" ON "process_steps" ("process_definition_id")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_process_steps_process_definition_id"')
    op.execute(
        'ALTER TABLE "process_steps" DROP COLUMN IF EXISTS "process_definition_id"'
    )
