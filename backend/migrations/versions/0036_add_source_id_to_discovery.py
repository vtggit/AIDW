"""Add source_id column to discovery_runs.

Revision ID: 0036_add_source_id_to_discovery
Revises: 0035_add_discovery_runs
"""

from alembic import op

revision = "0036_add_source_id_to_discovery"
down_revision = "0035_add_discovery_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "discovery_runs" ADD COLUMN IF NOT EXISTS "source_id" VARCHAR(64) REFERENCES "sources"("id") ON DELETE SET NULL'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_discovery_runs_source_id" ON "discovery_runs" ("source_id")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_discovery_runs_source_id"')
    op.execute('ALTER TABLE "discovery_runs" DROP COLUMN IF EXISTS "source_id"')
