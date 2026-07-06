"""Add source_id column to source_credentials.

Revision ID: 0011_add_source_id_to_source_cre
Revises: 0010_add_source_credentials
"""

from alembic import op

revision = "0011_add_source_id_to_source_cre"
down_revision = "0010_add_source_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "source_credentials" ADD COLUMN IF NOT EXISTS "source_id" VARCHAR(64) REFERENCES "sources"("id") ON DELETE SET NULL'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_source_credentials_source_id" ON "source_credentials" ("source_id")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_source_credentials_source_id"')
    op.execute('ALTER TABLE "source_credentials" DROP COLUMN IF EXISTS "source_id"')
