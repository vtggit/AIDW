"""Add tested_at column to connection_tests.

Revision ID: 0020_add_tested_at_to_connection
Revises: 0019_add_latency_ms_to_connectio
"""

from alembic import op

revision = "0020_add_tested_at_to_connection"
down_revision = "0019_add_latency_ms_to_connectio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "connection_tests" ADD COLUMN IF NOT EXISTS "tested_at" VARCHAR(32)'
    )


def downgrade() -> None:
    op.execute('ALTER TABLE "connection_tests" DROP COLUMN IF EXISTS "tested_at"')
