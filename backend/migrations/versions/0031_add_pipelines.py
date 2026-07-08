"""Add pipelines table.

Revision ID: 0031_add_pipelines
Revises: 0030_add_field_profiles

A pipeline is the ingest definition for ONE dataset (docs/BEHAVIORAL-ARCHITECTURE.md §3 [CDC]):
which CDC pattern moves its rows and on what schedule. Milestone 4 implements the ``cursor``
pattern in-API; ``delta_token``/``snapshot_diff`` are breadth patterns reserved in the CHECK so
their rows need no migration later. A bare ``col IN (...)`` CHECK passes when the column IS NULL,
so generic CRUD writes that omit it still succeed.
"""

from alembic import op

revision = "0031_add_pipelines"
down_revision = "0030_add_field_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS pipelines (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            dataset_id VARCHAR(64) REFERENCES datasets(id) ON DELETE SET NULL,
            cdc_pattern VARCHAR(32),
            schedule VARCHAR(255),
            is_enabled BOOLEAN,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT chk_pipelines_cdc_pattern
                CHECK (cdc_pattern IN ('cursor', 'delta_token', 'snapshot_diff'))
        );
    """)
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_pipelines_dataset_id" '
        'ON "pipelines" ("dataset_id")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_pipelines_dataset_id"')
    op.execute("DROP TABLE IF EXISTS pipelines")
