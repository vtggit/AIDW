"""Add deletion_request_id column to suppression_entries.

Revision ID: 0061_add_deletion_request_id_to
Revises: 0060_add_dataset_id_to_suppressi
"""

from alembic import op

revision = "0061_add_deletion_request_id_to"
down_revision = "0060_add_dataset_id_to_suppressi"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "suppression_entries" ADD COLUMN IF NOT EXISTS "deletion_request_id" VARCHAR(64) REFERENCES "deletion_requests"("id") ON DELETE SET NULL'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_suppression_entries_deletion_request_id" ON "suppression_entries" ("deletion_request_id")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_suppression_entries_deletion_request_id"')
    op.execute(
        'ALTER TABLE "suppression_entries" DROP COLUMN IF EXISTS "deletion_request_id"'
    )
