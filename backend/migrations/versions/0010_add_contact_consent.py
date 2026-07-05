"""Add contact_consent — normalized per-channel consent (#185).

Revision ID: 0010_add_contact_consent
Revises: 0009_add_uq_companies_name
"""

from alembic import op

revision = "0010_add_contact_consent"
down_revision = "0009_add_uq_companies_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS contact_consent (
            id VARCHAR(64) PRIMARY KEY,
            contact_id VARCHAR(64) NOT NULL
                REFERENCES contacts(id) ON DELETE CASCADE,
            channel VARCHAR(32) NOT NULL DEFAULT 'email',
            status VARCHAR(16) NOT NULL,
            source VARCHAR(64),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_contact_consent_contact_channel
                UNIQUE (contact_id, channel)
        )
        """)
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_contact_consent_contact_id" '
        'ON "contact_consent" ("contact_id")'
    )


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS "contact_consent"')
