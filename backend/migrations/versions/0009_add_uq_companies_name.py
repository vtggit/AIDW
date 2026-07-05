"""Add uq_companies_name index on companies(name).

Revision ID: 0009_add_uq_companies_name
Revises: 0008_add_idx_companies_deleted_a
"""

from alembic import op

revision = "0009_add_uq_companies_name"
down_revision = "0008_add_idx_companies_deleted_a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The migration must succeed on existing data containing duplicates: later
    # duplicates (by created_at, then id) are renamed with a short id suffix
    # BEFORE the unique index is created. A no-op on clean data.
    op.execute("""
        UPDATE "companies" AS c
        SET "name" = c."name" || ' [' || substr(c.id::text, 1, 8) || ']'
        WHERE EXISTS (
            SELECT 1 FROM "companies" AS e
            WHERE lower(e."name") = lower(c."name") AND e.id <> c.id
            AND (e.created_at < c.created_at
                 OR (e.created_at = c.created_at AND e.id < c.id))
        )
        """)
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS "uq_companies_name" ON "companies" (LOWER("name"))'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "uq_companies_name"')
