"""Add retention_period_days column to retention_policies.

Revision ID: 0046_add_retention_period_days_t
Revises: 0045_add_dataset_id_to_retention
"""

from alembic import op

revision = "0046_add_retention_period_days_t"
down_revision = "0045_add_dataset_id_to_retention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "retention_policies" ADD COLUMN IF NOT EXISTS "retention_period_days" INTEGER'
    )
    op.execute(
        """DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_retention_policies_retention_period_days') THEN ALTER TABLE "retention_policies" ADD CONSTRAINT "chk_retention_policies_retention_period_days" CHECK ("retention_period_days" > 0); END IF; END $$;"""
    )


def downgrade() -> None:
    op.execute(
        'ALTER TABLE "retention_policies" DROP CONSTRAINT IF EXISTS "chk_retention_policies_retention_period_days"'
    )
    op.execute(
        'ALTER TABLE "retention_policies" DROP COLUMN IF EXISTS "retention_period_days"'
    )
