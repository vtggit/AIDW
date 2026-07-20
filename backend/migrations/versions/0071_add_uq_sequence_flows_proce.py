"""Add uq_sequence_flows_process_definition_id_source_step_partial index on sequence_flows(process_definition_id, source_step).

Revision ID: 0071_add_uq_sequence_flows_proce
Revises: 0070_add_uq_sequence_flows_proce
"""

from alembic import op

revision = "0071_add_uq_sequence_flows_proce"
down_revision = "0070_add_uq_sequence_flows_proce"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS "uq_sequence_flows_process_definition_id_source_step_partial" ON "sequence_flows" ("process_definition_id", "source_step") WHERE "is_default"'
    )


def downgrade() -> None:
    op.execute(
        'DROP INDEX IF EXISTS "uq_sequence_flows_process_definition_id_source_step_partial"'
    )
