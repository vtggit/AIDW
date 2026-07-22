"""Add review_cycle_days column to process_definitions.

Revision ID: 0074_add_review_cycle_days_to_pr
Revises: 0073_add_fk_sequence_flows_proce
"""

from alembic import op

revision = "0074_add_review_cycle_days_to_pr"
down_revision = "0073_add_fk_sequence_flows_proce"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "process_definitions" ADD COLUMN IF NOT EXISTS "review_cycle_days" INTEGER'
    )
    op.execute(
        """DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_process_definitions_review_cycle_days') THEN ALTER TABLE "process_definitions" ADD CONSTRAINT "chk_process_definitions_review_cycle_days" CHECK ("review_cycle_days" > 0); END IF; END $$;"""
    )


def downgrade() -> None:
    op.execute(
        'ALTER TABLE "process_definitions" DROP CONSTRAINT IF EXISTS "chk_process_definitions_review_cycle_days"'
    )
    op.execute(
        'ALTER TABLE "process_definitions" DROP COLUMN IF EXISTS "review_cycle_days"'
    )
