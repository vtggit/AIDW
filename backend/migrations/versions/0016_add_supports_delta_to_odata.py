"""Add supports_delta column to odata_service_configs.

Revision ID: 0016_add_supports_delta_to_odata
Revises: 0015_add_source_id_to_odata_serv
"""

from alembic import op

revision = "0016_add_supports_delta_to_odata"
down_revision = "0015_add_source_id_to_odata_serv"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "odata_service_configs" ADD COLUMN IF NOT EXISTS "supports_delta" BOOLEAN'
    )


def downgrade() -> None:
    op.execute(
        'ALTER TABLE "odata_service_configs" DROP COLUMN IF EXISTS "supports_delta"'
    )
