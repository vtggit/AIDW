"""Add uq_sequence_flows_process_definition_id_flow_key index on sequence_flows(process_definition_id, flow_key).

Revision ID: 0070_add_uq_sequence_flows_proce
Revises: 0069_add_uq_process_steps_proces
"""

from alembic import op

revision = "0070_add_uq_sequence_flows_proce"
down_revision = "0069_add_uq_process_steps_proces"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS "uq_sequence_flows_process_definition_id_flow_key" ON "sequence_flows" ("process_definition_id", "flow_key")'
    )


def downgrade() -> None:
    op.execute(
        'DROP INDEX IF EXISTS "uq_sequence_flows_process_definition_id_flow_key"'
    )
