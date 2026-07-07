"""Add dashboards table.

Revision ID: 0027_add_dashboards
Revises: 0026_add_suggestion_fields

A dashboard is a named collection of items. Accepting a suggestion lands an item on a dashboard
(a default one is created on first accept); users can also create/rename dashboards via CRUD.
"""

from alembic import op

revision = "0027_add_dashboards"
down_revision = "0026_add_suggestion_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS dashboards (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            description VARCHAR(1024),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS dashboards")
