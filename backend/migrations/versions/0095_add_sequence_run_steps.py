"""Add sequence_run_steps table."""

from alembic import op

revision = "0095_add_sequence_run_steps"
down_revision = "0094_add_uq_sequence_runs_sequen"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS sequence_run_steps (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            run_id VARCHAR(255),
            step_id VARCHAR(255),
            status VARCHAR(255),
            started_at VARCHAR(255),
            finished_at VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sequence_run_steps")
