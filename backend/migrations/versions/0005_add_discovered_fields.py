"""Add discovered_fields table."""

from alembic import op

revision = "0005_add_discovered_fields"
down_revision = "0004_add_source_id_to_datasets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS discovered_fields (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            data_type VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS discovered_fields")
