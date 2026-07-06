"""Add latency_ms column to connection_tests.

Revision ID: 0019_add_latency_ms_to_connectio
Revises: 0018_add_source_id_to_connection
"""

from alembic import op

revision = "0019_add_latency_ms_to_connectio"
down_revision = "0018_add_source_id_to_connection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "connection_tests" ADD COLUMN IF NOT EXISTS "latency_ms" INTEGER'
    )


def downgrade() -> None:
    op.execute('ALTER TABLE "connection_tests" DROP COLUMN IF EXISTS "latency_ms"')
