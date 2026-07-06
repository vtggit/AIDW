"""Add source_connections table."""

from alembic import op

revision = "0006_add_source_connections"
down_revision = "0005_add_discovered_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS source_connections (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            endpoint VARCHAR(255),
            protocol_version VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS source_connections")
