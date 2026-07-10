"""Add is_enabled column to retention_policies.

Revision ID: 0047_add_is_enabled_to_retention
Revises: 0046_add_retention_period_days_t
"""

from alembic import op

revision = "0047_add_is_enabled_to_retention"
down_revision = "0046_add_retention_period_days_t"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "retention_policies" ADD COLUMN IF NOT EXISTS "is_enabled" BOOLEAN'
    )


def downgrade() -> None:
    op.execute('ALTER TABLE "retention_policies" DROP COLUMN IF EXISTS "is_enabled"')
