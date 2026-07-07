"""Add suggestions table.

Revision ID: 0025_add_suggestions
Revises: 0024_add_field_position_to_disco

The dashboard-suggestion inbox. Each row is one candidate dashboard item the engine derived
automatically from a dataset's discovered schema (schema-tier) — item_type/aggregation/role-tagged
fields mirror the canonical model in docs/BEHAVIORAL-ARCHITECTURE.md §3. CHECK constraints pin the
small enums; the (dataset_id, fingerprint) UNIQUE index makes regeneration idempotent — the engine
computes a fingerprint from a suggestion's semantic identity so a re-discovery of the same schema
never duplicates a row. A bare ``col IN (...)`` CHECK passes when the column IS NULL (NULL IN → NULL,
not FALSE), so generic CRUD writes that omit these columns still succeed; the engine always sets them.
"""

from alembic import op

revision = "0025_add_suggestions"
down_revision = "0024_add_field_position_to_disco"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS suggestions (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            dataset_id VARCHAR(64) REFERENCES datasets(id) ON DELETE SET NULL,
            title VARCHAR(255),
            item_type VARCHAR(32),
            aggregation VARCHAR(32),
            score DOUBLE PRECISION,
            rationale VARCHAR(1024),
            strategy VARCHAR(32),
            status VARCHAR(32),
            fingerprint VARCHAR(64),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT chk_suggestions_item_type
                CHECK (item_type IN ('kpi', 'bar', 'line', 'pie', 'table')),
            CONSTRAINT chk_suggestions_aggregation
                CHECK (aggregation IN ('count', 'sum', 'avg', 'none')),
            CONSTRAINT chk_suggestions_strategy
                CHECK (strategy IN ('schema-only', 'profile')),
            CONSTRAINT chk_suggestions_status
                CHECK (status IN ('suggested', 'accepted', 'dismissed', 'stale'))
        );
    """)
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_suggestions_dataset_id" '
        'ON "suggestions" ("dataset_id")'
    )
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS "uq_suggestions_dataset_fingerprint" '
        'ON "suggestions" ("dataset_id", "fingerprint")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "uq_suggestions_dataset_fingerprint"')
    op.execute('DROP INDEX IF EXISTS "idx_suggestions_dataset_id"')
    op.execute("DROP TABLE IF EXISTS suggestions")
