"""Add deletion_requests table."""

from alembic import op

revision = "0057_add_deletion_requests"
down_revision = "0056_add_idx_audit_logs_entity_t"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS deletion_requests (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            subject_key VARCHAR(255),
            subject_key_hash VARCHAR(255),
            status VARCHAR(255),
            reason VARCHAR(255),
            error_detail VARCHAR(255),
            attempts INTEGER,
            records_deleted INTEGER,
            profiles_cleared INTEGER,
            verified_by VARCHAR(255),
            verified_at VARCHAR(255),
            completed_at VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT chk_deletion_requests_status
                CHECK (status IN ('received', 'verifying', 'executing', 'completed', 'rejected'))
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS deletion_requests")
