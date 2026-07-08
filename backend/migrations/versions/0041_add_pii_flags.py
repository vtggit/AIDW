"""Add pii_flags table."""

from alembic import op

revision = "0041_add_pii_flags"
down_revision = "0040_add_last_seen_run_id_to_dis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS pii_flags (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            category VARCHAR(255),
            detection_tier VARCHAR(255),
            status VARCHAR(255),
            confidence DOUBLE PRECISION,
            rationale VARCHAR(255),
            fingerprint VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT chk_pii_flags_category
                CHECK (category IN ('direct_identifier', 'contact', 'government_id', 'financial', 'health', 'date_of_birth', 'location', 'credential', 'network_identifier', 'other')),
            CONSTRAINT chk_pii_flags_detection_tier
                CHECK (detection_tier IN ('schema', 'profile')),
            CONSTRAINT chk_pii_flags_status
                CHECK (status IN ('flagged', 'confirmed', 'dismissed', 'stale'))
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS pii_flags")
