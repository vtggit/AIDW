"""Add sequence_steps table."""

from alembic import op

revision = "0089_add_sequence_steps"
down_revision = "0088_add_load_sequences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS sequence_steps (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            sequence_id VARCHAR(255),
            pipeline_id VARCHAR(255),
            label VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sequence_steps")
