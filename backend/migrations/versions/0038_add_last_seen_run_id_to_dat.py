"""Add last_seen_run_id column to datasets.

Revision ID: 0038_add_last_seen_run_id_to_dat
Revises: 0037_add_first_seen_run_id_to_da
"""

from alembic import op

revision = "0038_add_last_seen_run_id_to_dat"
down_revision = "0037_add_first_seen_run_id_to_da"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "datasets" ADD COLUMN IF NOT EXISTS "last_seen_run_id" VARCHAR(64) REFERENCES "discovery_runs"("id") ON DELETE SET NULL'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_datasets_last_seen_run_id" ON "datasets" ("last_seen_run_id")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_datasets_last_seen_run_id"')
    op.execute('ALTER TABLE "datasets" DROP COLUMN IF EXISTS "last_seen_run_id"')
