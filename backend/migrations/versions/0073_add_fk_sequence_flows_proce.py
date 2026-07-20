"""Add composite FK fk_sequence_flows_process_definition_id_target_step_pr_761200ea on sequence_flows(process_definition_id, target_step) -> process_steps(process_definition_id, step_key).

Revision ID: 0073_add_fk_sequence_flows_proce
Revises: 0072_add_fk_sequence_flows_proce
"""

from alembic import op

revision = "0073_add_fk_sequence_flows_proce"
down_revision = "0072_add_fk_sequence_flows_proce"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_sequence_flows_process_definition_id_target_step_pr_761200ea') THEN ALTER TABLE "sequence_flows" ADD CONSTRAINT "fk_sequence_flows_process_definition_id_target_step_pr_761200ea" FOREIGN KEY ("process_definition_id", "target_step") REFERENCES "process_steps" ("process_definition_id", "step_key") ON DELETE CASCADE; END IF; END $$;"""
    )


def downgrade() -> None:
    op.execute(
        'ALTER TABLE "sequence_flows" DROP CONSTRAINT IF EXISTS "fk_sequence_flows_process_definition_id_target_step_pr_761200ea"'
    )
