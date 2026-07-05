"""Add company_id column to leads.

Revision ID: 0006_add_company_id_to_leads
Revises: 0005_add_company_id_to_contacts
"""

from alembic import op

revision = "0006_add_company_id_to_leads"
down_revision = "0005_add_company_id_to_contacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "leads" ADD COLUMN IF NOT EXISTS "company_id" VARCHAR(64) REFERENCES "companies"("id") ON DELETE SET NULL'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_leads_company_id" ON "leads" ("company_id")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_leads_company_id"')
    op.execute('ALTER TABLE "leads" DROP COLUMN IF EXISTS "company_id"')
