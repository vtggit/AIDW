"""Add delta_cursors table.

Revision ID: 0033_add_delta_cursors
Revises: 0032_add_runs

The watermark for the cursor CDC pattern: which discovered_field a pipeline pages on
(``cursor_field_id``), the kind of comparison its values need, and the high-water value the last
successful run reached (``cursor_value``, stored as a string — ISO timestamps and zero-padded
numerics compare correctly as text at the API tier; the typed compare happens in the ingest
module). UNIQUE(pipeline_id) — one live cursor per pipeline — is what makes cursor bootstrap +
advance idempotent. FKs ON DELETE SET NULL per convention.
"""

from alembic import op

revision = "0033_add_delta_cursors"
down_revision = "0032_add_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS delta_cursors (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            pipeline_id VARCHAR(64) REFERENCES pipelines(id) ON DELETE SET NULL,
            cursor_field_id VARCHAR(64) REFERENCES discovered_fields(id) ON DELETE SET NULL,
            last_run_id VARCHAR(64) REFERENCES runs(id) ON DELETE SET NULL,
            cursor_kind VARCHAR(32),
            cursor_value VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT chk_delta_cursors_cursor_kind
                CHECK (cursor_kind IN ('timestamp', 'numeric', 'string'))
        );
    """)
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS "uq_delta_cursors_pipeline_id" '
        'ON "delta_cursors" ("pipeline_id")'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_delta_cursors_cursor_field_id" '
        'ON "delta_cursors" ("cursor_field_id")'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_delta_cursors_last_run_id" '
        'ON "delta_cursors" ("last_run_id")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_delta_cursors_last_run_id"')
    op.execute('DROP INDEX IF EXISTS "idx_delta_cursors_cursor_field_id"')
    op.execute('DROP INDEX IF EXISTS "uq_delta_cursors_pipeline_id"')
    op.execute("DROP TABLE IF EXISTS delta_cursors")
