"""Add dataset_id column to deletion_requests.

Revision ID: 0059_add_dataset_id_to_deletion
Revises: 0058_add_suppression_entries
"""

from alembic import op

revision = "0059_add_dataset_id_to_deletion"
down_revision = "0058_add_suppression_entries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "deletion_requests" ADD COLUMN IF NOT EXISTS "dataset_id" VARCHAR(64) REFERENCES "datasets"("id") ON DELETE SET NULL'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_deletion_requests_dataset_id" ON "deletion_requests" ("dataset_id")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_deletion_requests_dataset_id"')
    op.execute('ALTER TABLE "deletion_requests" DROP COLUMN IF EXISTS "dataset_id"')
