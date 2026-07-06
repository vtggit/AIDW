"""Add secret_ref column to source_credentials.

Revision ID: 0012_add_secret_ref_to_source_cr
Revises: 0011_add_source_id_to_source_cre
"""

from alembic import op

revision = "0012_add_secret_ref_to_source_cr"
down_revision = "0011_add_source_id_to_source_cre"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "source_credentials" ADD COLUMN IF NOT EXISTS "secret_ref" VARCHAR(255)'
    )


def downgrade() -> None:
    op.execute('ALTER TABLE "source_credentials" DROP COLUMN IF EXISTS "secret_ref"')
