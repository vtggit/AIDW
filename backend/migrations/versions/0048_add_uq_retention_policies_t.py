"""Add uq_retention_policies_table_class_dataset_id_partial index on retention_policies(table_class, dataset_id).

Revision ID: 0048_add_uq_retention_policies_t
Revises: 0047_add_is_enabled_to_retention
"""

from alembic import op

revision = "0048_add_uq_retention_policies_t"
down_revision = "0047_add_is_enabled_to_retention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS "uq_retention_policies_table_class_dataset_id_partial" ON "retention_policies" ("table_class", "dataset_id") WHERE "dataset_id" IS NOT NULL'
    )


def downgrade() -> None:
    op.execute(
        'DROP INDEX IF EXISTS "uq_retention_policies_table_class_dataset_id_partial"'
    )
