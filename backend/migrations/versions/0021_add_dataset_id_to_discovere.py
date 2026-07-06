"""Add dataset_id column to discovered_fields.

Revision ID: 0021_add_dataset_id_to_discovere
Revises: 0020_add_tested_at_to_connection
"""

from alembic import op

revision = "0021_add_dataset_id_to_discovere"
down_revision = "0020_add_tested_at_to_connection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "discovered_fields" ADD COLUMN IF NOT EXISTS "dataset_id" VARCHAR(64) REFERENCES "datasets"("id") ON DELETE SET NULL'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_discovered_fields_dataset_id" ON "discovered_fields" ("dataset_id")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_discovered_fields_dataset_id"')
    op.execute('ALTER TABLE "discovered_fields" DROP COLUMN IF EXISTS "dataset_id"')
