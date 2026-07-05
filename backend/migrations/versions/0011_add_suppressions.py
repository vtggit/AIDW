"""Add suppressions — the send-gate enforcement store (#186).

Revision ID: 0011_add_suppressions
Revises: 0010_add_contact_consent
"""

from alembic import op

revision = "0011_add_suppressions"
down_revision = "0010_add_contact_consent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS suppressions (
            id VARCHAR(64) PRIMARY KEY,
            email VARCHAR(300) NOT NULL,
            reason VARCHAR(32) NOT NULL,
            note VARCHAR(500),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        )
        """)
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS "uq_suppressions_email" '
        'ON "suppressions" (LOWER("email"))'
    )


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS "suppressions"')
