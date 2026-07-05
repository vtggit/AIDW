"""Add contact_tags table and tags column to contacts.

Revision ID: 0002_add_contact_tags
Revises: 0001_baseline
Create Date: 2025-05-11
"""

from alembic import op

revision = "0002_add_contact_tags"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Table storing the global tag definitions
    op.execute("""
        CREATE TABLE IF NOT EXISTS contact_tags (
            id          VARCHAR(64)  PRIMARY KEY,
            name        VARCHAR(100) NOT NULL,
            color       VARCHAR(20)  NOT NULL DEFAULT '#3b82f6',
            created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_contact_tags_name
        ON contact_tags (LOWER(name));
    """)

    # Junction table: many-to-many between contacts and tags
    op.execute("""
        CREATE TABLE IF NOT EXISTS contact_tag_mapping (
            contact_id  VARCHAR(64) NOT NULL,
            tag_id      VARCHAR(64) NOT NULL,
            assigned_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            PRIMARY KEY (contact_id, tag_id),
            FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES contact_tags(id) ON DELETE CASCADE
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS contact_tag_mapping")
    op.execute("DROP TABLE IF EXISTS contact_tags")
