"""Add sources table."""

from alembic import op

revision = "0012_add_sources"
down_revision = "0011_add_suppressions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            type VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sources")
