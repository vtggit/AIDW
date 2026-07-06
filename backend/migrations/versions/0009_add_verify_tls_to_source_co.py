"""Add verify_tls column to source_connections.

Revision ID: 0009_add_verify_tls_to_source_co
Revises: 0008_add_timeout_seconds_to_sour
"""

from alembic import op

revision = "0009_add_verify_tls_to_source_co"
down_revision = "0008_add_timeout_seconds_to_sour"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "source_connections" ADD COLUMN IF NOT EXISTS "verify_tls" BOOLEAN'
    )


def downgrade() -> None:
    op.execute('ALTER TABLE "source_connections" DROP COLUMN IF EXISTS "verify_tls"')
