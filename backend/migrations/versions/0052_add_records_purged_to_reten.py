"""Add records_purged column to retention_runs.

Revision ID: 0052_add_records_purged_to_reten
Revises: 0051_add_policy_id_to_retention
"""

from alembic import op

revision = "0052_add_records_purged_to_reten"
down_revision = "0051_add_policy_id_to_retention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "retention_runs" ADD COLUMN IF NOT EXISTS "records_purged" INTEGER'
    )
    op.execute(
        """DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_retention_runs_records_purged') THEN ALTER TABLE "retention_runs" ADD CONSTRAINT "chk_retention_runs_records_purged" CHECK ("records_purged" >= 0); END IF; END $$;"""
    )


def downgrade() -> None:
    op.execute(
        'ALTER TABLE "retention_runs" DROP CONSTRAINT IF EXISTS "chk_retention_runs_records_purged"'
    )
    op.execute('ALTER TABLE "retention_runs" DROP COLUMN IF EXISTS "records_purged"')
