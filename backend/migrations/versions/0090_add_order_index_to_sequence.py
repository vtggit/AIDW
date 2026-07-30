"""Add order_index column to sequence_steps.

Revision ID: 0090_add_order_index_to_sequence
Revises: 0089_add_sequence_steps
"""

from alembic import op

revision = "0090_add_order_index_to_sequence"
down_revision = "0089_add_sequence_steps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "sequence_steps" ADD COLUMN IF NOT EXISTS "order_index" INTEGER'
    )
    op.execute(
        """DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_sequence_steps_order_index') THEN ALTER TABLE "sequence_steps" ADD CONSTRAINT "chk_sequence_steps_order_index" CHECK ("order_index" >= 0); END IF; END $$;"""
    )


def downgrade() -> None:
    op.execute(
        'ALTER TABLE "sequence_steps" DROP CONSTRAINT IF EXISTS "chk_sequence_steps_order_index"'
    )
    op.execute('ALTER TABLE "sequence_steps" DROP COLUMN IF EXISTS "order_index"')
