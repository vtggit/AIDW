"""Add suggestion_fields table.

Revision ID: 0026_add_suggestion_fields
Revises: 0025_add_suggestions

The role-tagged field satellite of ``suggestions`` (no JSONB — chart config is normalized rows).
Each row binds one discovered_field to a suggestion in a role (measure / dimension / temporal /
display), so a suggestion's axes/measures are real FK references into ``discovered_fields``, not
free text. FK ON DELETE SET NULL matches the standing convention: if a field vanishes upstream the
binding nulls out and the reconciler marks the dependent suggestion ``stale``.
"""

from alembic import op

revision = "0026_add_suggestion_fields"
down_revision = "0025_add_suggestions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS suggestion_fields (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            suggestion_id VARCHAR(64) REFERENCES suggestions(id) ON DELETE SET NULL,
            discovered_field_id VARCHAR(64) REFERENCES discovered_fields(id) ON DELETE SET NULL,
            field_role VARCHAR(32),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT chk_suggestion_fields_role
                CHECK (field_role IN ('measure', 'dimension', 'temporal', 'display'))
        );
    """)
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_suggestion_fields_suggestion_id" '
        'ON "suggestion_fields" ("suggestion_id")'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_suggestion_fields_discovered_field_id" '
        'ON "suggestion_fields" ("discovered_field_id")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_suggestion_fields_discovered_field_id"')
    op.execute('DROP INDEX IF EXISTS "idx_suggestion_fields_suggestion_id"')
    op.execute("DROP TABLE IF EXISTS suggestion_fields")
