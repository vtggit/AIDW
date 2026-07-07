"""Add dashboard_item_fields table.

Revision ID: 0029_add_dashboard_item_fields
Revises: 0028_add_dashboard_items

The role-tagged field satellite of dashboard_items (no JSONB), copied from a suggestion's
suggestion_fields on accept. Each row binds a discovered_field to an item in a role, so a rendered
item's axes/measures are real FK references. FK ON DELETE SET NULL per convention.
"""

from alembic import op

revision = "0029_add_dashboard_item_fields"
down_revision = "0028_add_dashboard_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS dashboard_item_fields (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            dashboard_item_id VARCHAR(64) REFERENCES dashboard_items(id) ON DELETE SET NULL,
            discovered_field_id VARCHAR(64) REFERENCES discovered_fields(id) ON DELETE SET NULL,
            field_role VARCHAR(32),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT chk_dashboard_item_fields_role
                CHECK (field_role IN ('measure', 'dimension', 'temporal', 'display'))
        );
    """)
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_dashboard_item_fields_dashboard_item_id" '
        'ON "dashboard_item_fields" ("dashboard_item_id")'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_dashboard_item_fields_discovered_field_id" '
        'ON "dashboard_item_fields" ("discovered_field_id")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_dashboard_item_fields_discovered_field_id"')
    op.execute('DROP INDEX IF EXISTS "idx_dashboard_item_fields_dashboard_item_id"')
    op.execute("DROP TABLE IF EXISTS dashboard_item_fields")
