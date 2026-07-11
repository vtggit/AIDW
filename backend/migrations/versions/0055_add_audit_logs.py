"""Add audit_logs table."""

from alembic import op

revision = "0055_add_audit_logs"
down_revision = "0054_add_error_detail_to_retenti"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            actor VARCHAR(255),
            entity_type VARCHAR(255),
            entity_id VARCHAR(255),
            detail VARCHAR(255),
            action VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT chk_audit_logs_action
                CHECK (action IN ('create', 'update', 'delete'))
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_logs")
