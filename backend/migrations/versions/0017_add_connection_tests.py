"""Add connection_tests table."""

from alembic import op

revision = "0017_add_connection_tests"
down_revision = "0016_add_supports_delta_to_odata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS connection_tests (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            status VARCHAR(255),
            message VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS connection_tests")
