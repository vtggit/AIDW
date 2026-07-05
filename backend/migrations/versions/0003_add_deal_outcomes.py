"""Add deal_outcomes table for win/loss reason tracking.

Revision ID: 0003_add_deal_outcomes
Revises: 0002_add_contact_tags
Create Date: 2026-05-14
"""

from alembic import op

revision = "0003_add_deal_outcomes"
down_revision = "0002_add_contact_tags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS deal_outcomes (
            id                VARCHAR(64)  PRIMARY KEY,
            lead_id           VARCHAR(64)  NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
            outcome           VARCHAR(10)  NOT NULL CHECK (outcome IN ('won', 'lost')),
            reason_category   VARCHAR(50)  NOT NULL DEFAULT 'other',
            reason_text       TEXT,
            competitor_name   VARCHAR(200),
            created_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_deal_outcomes_lead_id
        ON deal_outcomes (lead_id);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_deal_outcomes_outcome
        ON deal_outcomes (outcome);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS deal_outcomes")
