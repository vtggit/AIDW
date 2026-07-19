"""Add process_definitions table."""

from alembic import op

revision = "0064_add_process_definitions"
down_revision = "0063_add_uq_suppression_key_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS process_definitions (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            process_key VARCHAR(255),
            version VARCHAR(255),
            description VARCHAR(255),
            status VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS process_definitions")
