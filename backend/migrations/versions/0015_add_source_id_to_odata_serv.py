"""Add source_id column to odata_service_configs.

Revision ID: 0015_add_source_id_to_odata_serv
Revises: 0014_add_odata_service_configs
"""

from alembic import op

revision = "0015_add_source_id_to_odata_serv"
down_revision = "0014_add_odata_service_configs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "odata_service_configs" ADD COLUMN IF NOT EXISTS "source_id" VARCHAR(64) REFERENCES "sources"("id") ON DELETE SET NULL'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_odata_service_configs_source_id" ON "odata_service_configs" ("source_id")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_odata_service_configs_source_id"')
    op.execute('ALTER TABLE "odata_service_configs" DROP COLUMN IF EXISTS "source_id"')
