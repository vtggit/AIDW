"""Add idx_audit_logs_entity_type_entity_id index on audit_logs(entity_type, entity_id).

Revision ID: 0056_add_idx_audit_logs_entity_t
Revises: 0055_add_audit_logs
"""

from alembic import op

revision = "0056_add_idx_audit_logs_entity_t"
down_revision = "0055_add_audit_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_audit_logs_entity_type_entity_id" ON "audit_logs" ("entity_type", "entity_id")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "idx_audit_logs_entity_type_entity_id"')
