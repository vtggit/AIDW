"""Add records_anonymized column to retention_runs.

Revision ID: 0053_add_records_anonymized_to_r
Revises: 0052_add_records_purged_to_reten
"""

from alembic import op

revision = "0053_add_records_anonymized_to_r"
down_revision = "0052_add_records_purged_to_reten"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "retention_runs" ADD COLUMN IF NOT EXISTS "records_anonymized" INTEGER'
    )
    op.execute(
        """DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_retention_runs_records_anonymized') THEN ALTER TABLE "retention_runs" ADD CONSTRAINT "chk_retention_runs_records_anonymized" CHECK ("records_anonymized" >= 0); END IF; END $$;"""
    )


def downgrade() -> None:
    op.execute(
        'ALTER TABLE "retention_runs" DROP CONSTRAINT IF EXISTS "chk_retention_runs_records_anonymized"'
    )
    op.execute(
        'ALTER TABLE "retention_runs" DROP COLUMN IF EXISTS "records_anonymized"'
    )
