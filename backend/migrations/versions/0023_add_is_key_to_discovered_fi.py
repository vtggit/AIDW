"""Add is_key column to discovered_fields.

Revision ID: 0023_add_is_key_to_discovered_fi
Revises: 0022_add_is_nullable_to_discover
"""

from alembic import op

revision = "0023_add_is_key_to_discovered_fi"
down_revision = "0022_add_is_nullable_to_discover"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "discovered_fields" ADD COLUMN IF NOT EXISTS "is_key" BOOLEAN'
    )


def downgrade() -> None:
    op.execute('ALTER TABLE "discovered_fields" DROP COLUMN IF EXISTS "is_key"')
