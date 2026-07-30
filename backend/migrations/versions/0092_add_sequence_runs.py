"""Add sequence_runs table."""

from alembic import op

revision = "0092_add_sequence_runs"
down_revision = "0091_add_uq_sequence_steps_seque"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS sequence_runs (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            sequence_id VARCHAR(255),
            status VARCHAR(255),
            started_at VARCHAR(255),
            finished_at VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sequence_runs")
