"""Add deleted_at column to companies.

Revision ID: 0007_add_deleted_at_to_companies
Revises: 0006_add_company_id_to_leads
"""

from alembic import op

revision = "0007_add_deleted_at_to_companies"
down_revision = "0006_add_company_id_to_leads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "companies" ADD COLUMN IF NOT EXISTS "deleted_at" TIMESTAMP WITH TIME ZONE'
    )


def downgrade() -> None:
    op.execute('ALTER TABLE "companies" DROP COLUMN IF EXISTS "deleted_at"')
