"""Add process_steps table."""

from alembic import op

revision = "0065_add_process_steps"
down_revision = "0064_add_process_definitions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS process_steps (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            step_key VARCHAR(255),
            ordinal INTEGER,
            step_type VARCHAR(255),
            service_impl VARCHAR(255),
            candidate_groups VARCHAR(255),
            form_key VARCHAR(255),
            timer_duration INTEGER,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS process_steps")
