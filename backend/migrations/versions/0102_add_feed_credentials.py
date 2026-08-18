"""Add feed_credentials table."""

from alembic import op

revision = "0102_add_feed_credentials"
down_revision = "0101_add_triggered_by_to_sequenc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS feed_credentials (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            principal VARCHAR(255),
            key_hash VARCHAR(255),
            key_prefix VARCHAR(255),
            revoked BOOLEAN,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS feed_credentials")
