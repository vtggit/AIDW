"""Add dataset_id column to suppression_entries.

Revision ID: 0060_add_dataset_id_to_suppressi
Revises: 0059_add_dataset_id_to_deletion
"""

from alembic import op

revision = "0060_add_dataset_id_to_suppressi"
down_revision = "0059_add_dataset_id_to_deletion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "suppression_entries" ADD COLUMN IF NOT EXISTS "dataset_id" VARCHAR(64) REFERENCES "datasets"("id") ON DELETE SET NULL'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_suppression_entries_dataset_id" ON "suppression_entries" ("dataset_id")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_suppression_entries_dataset_id"')
    op.execute('ALTER TABLE "suppression_entries" DROP COLUMN IF EXISTS "dataset_id"')
