"""Add field_profiles table.

Revision ID: 0030_add_field_profiles
Revises: 0029_add_dashboard_item_fields

Per-field statistics computed from a sampled data page (the interim profiler). One row per
discovered_field (UNIQUE), carrying the row/null/distinct counts + min/max/most-common that the
profile-tier re-scorer uses to confirm or demote schema-tier suggestions with REAL cardinality —
the thing that does not exist at the schema tier. FK ON DELETE SET NULL per convention.
"""

from alembic import op

revision = "0030_add_field_profiles"
down_revision = "0029_add_dashboard_item_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS field_profiles (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            discovered_field_id VARCHAR(64) REFERENCES discovered_fields(id) ON DELETE SET NULL,
            row_count INTEGER,
            null_count INTEGER,
            distinct_count INTEGER,
            min_value VARCHAR(255),
            max_value VARCHAR(255),
            most_common_value VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
    """)
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS "uq_field_profiles_discovered_field_id" '
        'ON "field_profiles" ("discovered_field_id")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "uq_field_profiles_discovered_field_id"')
    op.execute("DROP TABLE IF EXISTS field_profiles")
