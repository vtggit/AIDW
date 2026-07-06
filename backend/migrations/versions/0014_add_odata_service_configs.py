"""Add odata_service_configs table."""

from alembic import op

revision = "0014_add_odata_service_configs"
down_revision = "0013_add_token_endpoint_to_sourc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS odata_service_configs (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            metadata_path VARCHAR(255),
            default_entity_set VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS odata_service_configs")
