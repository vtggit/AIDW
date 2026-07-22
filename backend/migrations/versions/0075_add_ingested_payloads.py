"""Add ingested_payloads table for raw payload storage.

Revision ID: 0075_add_ingested_payloads
Revises: 0074_add_review_cycle_days_to_pr
Create Date: 2025-01-01 00:00:00.000000
"""

from alembic import op

revision = "0075_add_ingested_payloads"
down_revision = "0074_add_review_cycle_days_to_pr"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE ingested_payloads (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            dataset_id VARCHAR(64) REFERENCES datasets(id) ON DELETE CASCADE,
            business_key VARCHAR(255) NOT NULL,
            payload JSONB NOT NULL,
            ingested_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_ingested_payloads_dataset_business_key UNIQUE (dataset_id, business_key)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_ingested_payloads_dataset_id ON ingested_payloads(dataset_id)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS ingested_payloads")
