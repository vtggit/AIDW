"""Add idx_companies_deleted_at_partial index on companies(deleted_at).

Revision ID: 0008_add_idx_companies_deleted_a
Revises: 0007_add_deleted_at_to_companies
"""

from alembic import op

revision = "0008_add_idx_companies_deleted_a"
down_revision = "0007_add_deleted_at_to_companies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_companies_deleted_at_partial" ON "companies" ("deleted_at") WHERE "deleted_at" IS NULL'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_companies_deleted_at_partial"')
