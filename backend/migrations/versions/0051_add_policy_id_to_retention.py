"""Add policy_id column to retention_runs.

Revision ID: 0051_add_policy_id_to_retention
Revises: 0050_add_retention_runs
"""

from alembic import op

revision = "0051_add_policy_id_to_retention"
down_revision = "0050_add_retention_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "retention_runs" ADD COLUMN IF NOT EXISTS "policy_id" VARCHAR(64) REFERENCES "retention_policies"("id") ON DELETE SET NULL'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_retention_runs_policy_id" ON "retention_runs" ("policy_id")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_retention_runs_policy_id"')
    op.execute('ALTER TABLE "retention_runs" DROP COLUMN IF EXISTS "policy_id"')
