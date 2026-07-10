"""Add uq_retention_policies_table_class_partial index on retention_policies(table_class).

Revision ID: 0049_add_uq_retention_policies_t
Revises: 0048_add_uq_retention_policies_t
"""

from alembic import op

revision = "0049_add_uq_retention_policies_t"
down_revision = "0048_add_uq_retention_policies_t"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS "uq_retention_policies_table_class_partial" ON "retention_policies" ("table_class") WHERE "dataset_id" IS NULL'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "uq_retention_policies_table_class_partial"')
