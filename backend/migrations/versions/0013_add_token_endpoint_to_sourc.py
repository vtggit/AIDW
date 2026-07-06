"""Add token_endpoint column to source_credentials.

Revision ID: 0013_add_token_endpoint_to_sourc
Revises: 0012_add_secret_ref_to_source_cr
"""

from alembic import op

revision = "0013_add_token_endpoint_to_sourc"
down_revision = "0012_add_secret_ref_to_source_cr"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "source_credentials" ADD COLUMN IF NOT EXISTS "token_endpoint" VARCHAR(255)'
    )


def downgrade() -> None:
    op.execute(
        'ALTER TABLE "source_credentials" DROP COLUMN IF EXISTS "token_endpoint"'
    )
