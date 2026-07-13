"""Unique index on suppression_entries.key_hash (RTBF #76).

The [E] lane silently dropped the AC's "with a unique index" qualifier when it built
suppression_entries (0058) — recorded as an engine gap. The index is load-bearing twice over:
key_hash is globally unique BY DESIGN (dataset_id is folded into the HMAC input), and the
erasure executor's suppression insert relies on ON CONFLICT (key_hash) DO NOTHING.
"""

from alembic import op

revision = "0063_add_uq_suppression_key_hash"
down_revision = "0062_add_rows_suppressed_to_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS "uq_suppression_entries_key_hash" '
        'ON "suppression_entries" ("key_hash")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "uq_suppression_entries_key_hash"')
