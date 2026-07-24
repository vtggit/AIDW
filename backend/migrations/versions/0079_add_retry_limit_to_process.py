"""Add retry_limit column to process_steps.

Revision ID: 0079_add_retry_limit_to_process
Revises: 0078_seed_cdc_refresh
"""

from alembic import op

revision = "0079_add_retry_limit_to_process"
down_revision = "0078_seed_cdc_refresh"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "process_steps" ADD COLUMN IF NOT EXISTS "retry_limit" INTEGER'
    )
    op.execute(
        """DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_process_steps_retry_limit') THEN ALTER TABLE "process_steps" ADD CONSTRAINT "chk_process_steps_retry_limit" CHECK ("retry_limit" > 0); END IF; END $$;"""
    )


def downgrade() -> None:
    op.execute(
        'ALTER TABLE "process_steps" DROP CONSTRAINT IF EXISTS "chk_process_steps_retry_limit"'
    )
    op.execute('ALTER TABLE "process_steps" DROP COLUMN IF EXISTS "retry_limit"')
