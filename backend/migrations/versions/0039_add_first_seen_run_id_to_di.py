"""Add first_seen_run_id column to discovered_fields.

Revision ID: 0039_add_first_seen_run_id_to_di
Revises: 0038_add_last_seen_run_id_to_dat
"""

from alembic import op

revision = "0039_add_first_seen_run_id_to_di"
down_revision = "0038_add_last_seen_run_id_to_dat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "discovered_fields" ADD COLUMN IF NOT EXISTS "first_seen_run_id" VARCHAR(64) REFERENCES "discovery_runs"("id") ON DELETE SET NULL'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_discovered_fields_first_seen_run_id" ON "discovered_fields" ("first_seen_run_id")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_discovered_fields_first_seen_run_id"')
    op.execute(
        'ALTER TABLE "discovered_fields" DROP COLUMN IF EXISTS "first_seen_run_id"'
    )
