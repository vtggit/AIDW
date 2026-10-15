"""Add last_used_at column to feed_credentials.

Nullable TIMESTAMP WITH TIME ZONE recording the last time a feed credential
authenticated successfully. Existing keys start with NULL.

Revision ID: 0105_add_feed_cred_last_used
Revises: 0104_align_reaper_idx_null_stat
"""

from alembic import op

revision = "0105_add_feed_cred_last_used"
down_revision = "0104_align_reaper_idx_null_stat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "feed_credentials" ADD COLUMN IF NOT EXISTS "last_used_at" TIMESTAMP WITH TIME ZONE'
    )


def downgrade() -> None:
    op.execute('ALTER TABLE "feed_credentials" DROP COLUMN IF EXISTS "last_used_at"')
