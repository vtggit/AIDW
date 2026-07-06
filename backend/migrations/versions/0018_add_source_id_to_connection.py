"""Add source_id column to connection_tests.

Revision ID: 0018_add_source_id_to_connection
Revises: 0017_add_connection_tests
"""

from alembic import op

revision = "0018_add_source_id_to_connection"
down_revision = "0017_add_connection_tests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "connection_tests" ADD COLUMN IF NOT EXISTS "source_id" VARCHAR(64) REFERENCES "sources"("id") ON DELETE SET NULL'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_connection_tests_source_id" ON "connection_tests" ("source_id")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_connection_tests_source_id"')
    op.execute('ALTER TABLE "connection_tests" DROP COLUMN IF EXISTS "source_id"')
