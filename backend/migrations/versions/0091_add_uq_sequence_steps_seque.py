"""Add uq_sequence_steps_sequence_id_order_index index on sequence_steps(sequence_id, order_index).

Revision ID: 0091_add_uq_sequence_steps_seque
Revises: 0090_add_order_index_to_sequence
"""

from alembic import op

revision = "0091_add_uq_sequence_steps_seque"
down_revision = "0090_add_order_index_to_sequence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS "uq_sequence_steps_sequence_id_order_index" ON "sequence_steps" ("sequence_id", "order_index")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "uq_sequence_steps_sequence_id_order_index"')
