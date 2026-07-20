"""Add sequence_flows table."""

from alembic import op

revision = "0065_add_sequence_flows"
down_revision = "0064_add_process_definitions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS sequence_flows (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            flow_key VARCHAR(255),
            source_step VARCHAR(255),
            target_step VARCHAR(255),
            condition_expression VARCHAR(255),
            is_default BOOLEAN,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sequence_flows")
