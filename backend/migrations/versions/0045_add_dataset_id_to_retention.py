"""Add dataset_id column to retention_policies.

Revision ID: 0045_add_dataset_id_to_retention
Revises: 0044_add_retention_policies
"""

from alembic import op

revision = "0045_add_dataset_id_to_retention"
down_revision = "0044_add_retention_policies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "retention_policies" ADD COLUMN IF NOT EXISTS "dataset_id" VARCHAR(64) REFERENCES "datasets"("id") ON DELETE CASCADE'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_retention_policies_dataset_id" ON "retention_policies" ("dataset_id")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_retention_policies_dataset_id"')
    op.execute('ALTER TABLE "retention_policies" DROP COLUMN IF EXISTS "dataset_id"')
