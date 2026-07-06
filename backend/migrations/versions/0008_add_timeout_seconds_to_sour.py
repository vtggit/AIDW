"""Add timeout_seconds column to source_connections.

Revision ID: 0008_add_timeout_seconds_to_sour
Revises: 0007_add_source_id_to_source_con
"""

from alembic import op

revision = "0008_add_timeout_seconds_to_sour"
down_revision = "0007_add_source_id_to_source_con"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "source_connections" ADD COLUMN IF NOT EXISTS "timeout_seconds" INTEGER'
    )


def downgrade() -> None:
    op.execute(
        'ALTER TABLE "source_connections" DROP COLUMN IF EXISTS "timeout_seconds"'
    )
