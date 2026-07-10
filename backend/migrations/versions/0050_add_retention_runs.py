"""Add retention_runs table."""

from alembic import op

revision = "0050_add_retention_runs"
down_revision = "0049_add_uq_retention_policies_t"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS retention_runs (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            status VARCHAR(255),
            trigger VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT chk_retention_runs_status
                CHECK (status IN ('pending', 'running', 'succeeded', 'failed')),
            CONSTRAINT chk_retention_runs_trigger
                CHECK (trigger IN ('manual', 'scheduled'))
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS retention_runs")
