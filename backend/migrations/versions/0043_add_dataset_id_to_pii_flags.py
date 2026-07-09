"""Add dataset_id column to pii_flags.

Revision ID: 0043_add_dataset_id_to_pii_flags
Revises: 0042_add_discovered_field_id_to
"""

from alembic import op

revision = "0043_add_dataset_id_to_pii_flags"
down_revision = "0042_add_discovered_field_id_to"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "pii_flags" ADD COLUMN IF NOT EXISTS "dataset_id" VARCHAR(64) REFERENCES "datasets"("id") ON DELETE SET NULL'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_pii_flags_dataset_id" ON "pii_flags" ("dataset_id")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_pii_flags_dataset_id"')
    op.execute('ALTER TABLE "pii_flags" DROP COLUMN IF EXISTS "dataset_id"')
