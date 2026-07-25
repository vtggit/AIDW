"""Add dashboard_item_layouts table."""

from alembic import op

revision = "0084_add_dashboard_item_layouts"
down_revision = "0083_add_grid_columns_to_dashboa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS dashboard_item_layouts (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            user_id VARCHAR(255),
            dashboard_item_id VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS dashboard_item_layouts")
