"""Add source_id column to source_connections.

Revision ID: 0007_add_source_id_to_source_con
Revises: 0006_add_source_connections
"""

from alembic import op

revision = "0007_add_source_id_to_source_con"
down_revision = "0006_add_source_connections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "source_connections" ADD COLUMN IF NOT EXISTS "source_id" VARCHAR(64) REFERENCES "sources"("id") ON DELETE SET NULL'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_source_connections_source_id" ON "source_connections" ("source_id")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_source_connections_source_id"')
    op.execute('ALTER TABLE "source_connections" DROP COLUMN IF EXISTS "source_id"')
