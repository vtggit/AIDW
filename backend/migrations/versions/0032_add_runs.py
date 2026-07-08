"""Add runs table.

Revision ID: 0032_add_runs
Revises: 0031_add_pipelines

The ingestion run spine (docs/BEHAVIORAL-ARCHITECTURE.md §2/§3): one row per ingest execution of a
pipeline, carrying status/trigger/timing/row-counts/error. Deliberately separate from discovery's
run spine — different shape and lifecycle. The interim in-API executor and the Milestone 6 worker
write IDENTICAL rows, so nothing here is thrown away when execution moves out of the API.
"""

from alembic import op

revision = "0032_add_runs"
down_revision = "0031_add_pipelines"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            pipeline_id VARCHAR(64) REFERENCES pipelines(id) ON DELETE SET NULL,
            status VARCHAR(32),
            trigger VARCHAR(32),
            started_at TIMESTAMP WITH TIME ZONE,
            finished_at TIMESTAMP WITH TIME ZONE,
            rows_read INTEGER,
            rows_written INTEGER,
            error_detail VARCHAR(1024),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT chk_runs_status
                CHECK (status IN ('pending', 'running', 'succeeded', 'failed')),
            CONSTRAINT chk_runs_trigger
                CHECK (trigger IN ('manual', 'scheduled'))
        );
    """)
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_runs_pipeline_id" ON "runs" ("pipeline_id")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_runs_pipeline_id"')
    op.execute("DROP TABLE IF EXISTS runs")
