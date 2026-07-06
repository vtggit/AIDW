"""Add is_nullable column to discovered_fields.

Revision ID: 0022_add_is_nullable_to_discover
Revises: 0021_add_dataset_id_to_discovere
"""

from alembic import op

revision = "0022_add_is_nullable_to_discover"
down_revision = "0021_add_dataset_id_to_discovere"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "discovered_fields" ADD COLUMN IF NOT EXISTS "is_nullable" BOOLEAN'
    )


def downgrade() -> None:
    op.execute('ALTER TABLE "discovered_fields" DROP COLUMN IF EXISTS "is_nullable"')
