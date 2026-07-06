"""Add source_credentials table."""

from alembic import op

revision = "0010_add_source_credentials"
down_revision = "0009_add_verify_tls_to_source_co"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS source_credentials (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            auth_scheme VARCHAR(255),
            principal VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS source_credentials")
