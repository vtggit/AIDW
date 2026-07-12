"""Add suppression_entries table."""

from alembic import op

revision = "0058_add_suppression_entries"
down_revision = "0057_add_deletion_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS suppression_entries (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            key_hash VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS suppression_entries")
