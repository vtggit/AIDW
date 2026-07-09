"""Add discovered_field_id column to pii_flags.

Revision ID: 0042_add_discovered_field_id_to
Revises: 0041_add_pii_flags
"""

from alembic import op

revision = "0042_add_discovered_field_id_to"
down_revision = "0041_add_pii_flags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "pii_flags" ADD COLUMN IF NOT EXISTS "discovered_field_id" VARCHAR(64) REFERENCES "discovered_fields"("id") ON DELETE SET NULL'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_pii_flags_discovered_field_id" ON "pii_flags" ("discovered_field_id")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_pii_flags_discovered_field_id"')
    op.execute('ALTER TABLE "pii_flags" DROP COLUMN IF EXISTS "discovered_field_id"')
