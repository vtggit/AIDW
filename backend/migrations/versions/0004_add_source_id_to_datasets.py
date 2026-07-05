"""Add source_id column to datasets.

Revision ID: 0004_add_source_id_to_datasets
Revises: 0003_add_datasets
"""

from alembic import op

revision = "0004_add_source_id_to_datasets"
down_revision = "0003_add_datasets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "datasets" ADD COLUMN IF NOT EXISTS "source_id" VARCHAR(64) REFERENCES "sources"("id") ON DELETE SET NULL'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_datasets_source_id" ON "datasets" ("source_id")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_datasets_source_id"')
    op.execute('ALTER TABLE "datasets" DROP COLUMN IF EXISTS "source_id"')
