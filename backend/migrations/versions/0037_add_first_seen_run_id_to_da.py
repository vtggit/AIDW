"""Add first_seen_run_id column to datasets.

Revision ID: 0037_add_first_seen_run_id_to_da
Revises: 0036_add_source_id_to_discovery
"""

from alembic import op

revision = "0037_add_first_seen_run_id_to_da"
down_revision = "0036_add_source_id_to_discovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "datasets" ADD COLUMN IF NOT EXISTS "first_seen_run_id" VARCHAR(64) REFERENCES "discovery_runs"("id") ON DELETE SET NULL'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_datasets_first_seen_run_id" ON "datasets" ("first_seen_run_id")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_datasets_first_seen_run_id"')
    op.execute('ALTER TABLE "datasets" DROP COLUMN IF EXISTS "first_seen_run_id"')
