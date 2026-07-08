"""Add ingested_records table.

Revision ID: 0034_add_ingested_records
Revises: 0033_add_delta_cursors

The substrate-agnostic CDC op-log (docs/BEHAVIORAL-ARCHITECTURE.md §3): one row per
(dataset, business_key) recording the LATEST op seen for that source record plus run provenance —
so delete/lineage/idempotent-replay semantics are representable independent of the Milestone 6
typed landing tables (which will carry the actual payload columns). UNIQUE(dataset_id,
business_key) is the idempotent-replay guarantee: re-ingesting the same page updates rows in
place, never duplicates them.
"""

from alembic import op

revision = "0034_add_ingested_records"
down_revision = "0033_add_delta_cursors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS ingested_records (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            run_id VARCHAR(64) REFERENCES runs(id) ON DELETE SET NULL,
            dataset_id VARCHAR(64) REFERENCES datasets(id) ON DELETE SET NULL,
            business_key VARCHAR(255),
            op VARCHAR(16),
            ingested_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT chk_ingested_records_op
                CHECK (op IN ('insert', 'update', 'delete'))
        );
    """)
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_ingested_records_run_id" '
        'ON "ingested_records" ("run_id")'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_ingested_records_dataset_id" '
        'ON "ingested_records" ("dataset_id")'
    )
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS "uq_ingested_records_dataset_key" '
        'ON "ingested_records" ("dataset_id", "business_key")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "uq_ingested_records_dataset_key"')
    op.execute('DROP INDEX IF EXISTS "idx_ingested_records_dataset_id"')
    op.execute('DROP INDEX IF EXISTS "idx_ingested_records_run_id"')
    op.execute("DROP TABLE IF EXISTS ingested_records")
