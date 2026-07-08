"""Add last_seen_run_id column to discovered_fields.

Revision ID: 0040_add_last_seen_run_id_to_dis
Revises: 0039_add_first_seen_run_id_to_di
"""

from alembic import op

revision = "0040_add_last_seen_run_id_to_dis"
down_revision = "0039_add_first_seen_run_id_to_di"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "discovered_fields" ADD COLUMN IF NOT EXISTS "last_seen_run_id" VARCHAR(64) REFERENCES "discovery_runs"("id") ON DELETE SET NULL'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_discovered_fields_last_seen_run_id" ON "discovered_fields" ("last_seen_run_id")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_discovered_fields_last_seen_run_id"')
    op.execute(
        'ALTER TABLE "discovered_fields" DROP COLUMN IF EXISTS "last_seen_run_id"'
    )
