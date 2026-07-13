"""Add widgets table."""

from alembic import op

revision = "0064_add_widgets"
down_revision = "0063_add_uq_suppression_key_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS widgets (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            label VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS widgets")
