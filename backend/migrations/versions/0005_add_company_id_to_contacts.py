"""Add company_id column to contacts.

Revision ID: 0005_add_company_id_to_contacts
Revises: 0004_add_companies
"""

from alembic import op

revision = "0005_add_company_id_to_contacts"
down_revision = "0004_add_companies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "contacts" ADD COLUMN IF NOT EXISTS "company_id" VARCHAR(64) REFERENCES "companies"("id") ON DELETE SET NULL'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_contacts_company_id" ON "contacts" ("company_id")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_contacts_company_id"')
    op.execute('ALTER TABLE "contacts" DROP COLUMN IF EXISTS "company_id"')
