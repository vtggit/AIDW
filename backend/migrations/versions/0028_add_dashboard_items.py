"""Add dashboard_items table.

Revision ID: 0028_add_dashboard_items
Revises: 0027_add_dashboards

One rendered item on a dashboard. Accepting a suggestion copies it 1:1 into a dashboard_item
(title/item_type/aggregation), recording source_suggestion_id for provenance. The UNIQUE index on
source_suggestion_id enforces that a suggestion maps to at most one item (accept is idempotent);
NULLs are distinct in Postgres, so hand-created items (no source suggestion) are unconstrained.
CHECK enums mirror suggestions; a bare ``col IN (...)`` CHECK passes on NULL.
"""

from alembic import op

revision = "0028_add_dashboard_items"
down_revision = "0027_add_dashboards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS dashboard_items (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            dashboard_id VARCHAR(64) REFERENCES dashboards(id) ON DELETE SET NULL,
            source_suggestion_id VARCHAR(64) REFERENCES suggestions(id) ON DELETE SET NULL,
            title VARCHAR(255),
            item_type VARCHAR(32),
            aggregation VARCHAR(32),
            position INTEGER,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT chk_dashboard_items_item_type
                CHECK (item_type IN ('kpi', 'bar', 'line', 'pie', 'table')),
            CONSTRAINT chk_dashboard_items_aggregation
                CHECK (aggregation IN ('count', 'sum', 'avg', 'none'))
        );
    """)
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_dashboard_items_dashboard_id" '
        'ON "dashboard_items" ("dashboard_id")'
    )
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS "uq_dashboard_items_source_suggestion_id" '
        'ON "dashboard_items" ("source_suggestion_id")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "uq_dashboard_items_source_suggestion_id"')
    op.execute('DROP INDEX IF EXISTS "idx_dashboard_items_dashboard_id"')
    op.execute("DROP TABLE IF EXISTS dashboard_items")
