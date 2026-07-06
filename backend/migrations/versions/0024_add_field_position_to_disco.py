"""Add field_position column to discovered_fields.

Revision ID: 0024_add_field_position_to_disco
Revises: 0023_add_is_key_to_discovered_fi
"""

from alembic import op

revision = "0024_add_field_position_to_disco"
down_revision = "0023_add_is_key_to_discovered_fi"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "discovered_fields" ADD COLUMN IF NOT EXISTS "field_position" INTEGER'
    )


def downgrade() -> None:
    op.execute('ALTER TABLE "discovered_fields" DROP COLUMN IF EXISTS "field_position"')
