"""Add error_detail column to retention_runs.

Revision ID: 0054_add_error_detail_to_retenti
Revises: 0053_add_records_anonymized_to_r
"""

from alembic import op

revision = "0054_add_error_detail_to_retenti"
down_revision = "0053_add_records_anonymized_to_r"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "retention_runs" ADD COLUMN IF NOT EXISTS "error_detail" VARCHAR(1024)'
    )


def downgrade() -> None:
    op.execute('ALTER TABLE "retention_runs" DROP COLUMN IF EXISTS "error_detail"')
