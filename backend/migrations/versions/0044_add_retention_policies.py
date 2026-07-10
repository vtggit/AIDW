"""Add retention_policies table."""

from alembic import op

revision = "0044_add_retention_policies"
down_revision = "0043_add_dataset_id_to_pii_flags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS retention_policies (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            table_class VARCHAR(255),
            action VARCHAR(255),
            scope VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT chk_retention_policies_table_class
                CHECK (table_class IN ('connection_tests', 'runs', 'discovery_runs', 'ingested_records', 'field_profiles')),
            CONSTRAINT chk_retention_policies_action
                CHECK (action IN ('purge', 'anonymize')),
            CONSTRAINT chk_retention_policies_scope
                CHECK (scope IN ('class', 'dataset'))
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS retention_policies")
