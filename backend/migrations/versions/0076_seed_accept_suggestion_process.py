"""Seed accept-suggestion system process definition.

Revision ID: 0076_seed_accept_suggestion
Revises: 0075_add_ingested_payloads
Create Date: 2024-01-01 00:00:00.000000
"""

from alembic import op

revision = "0076_seed_accept_suggestion"
down_revision = "0075_add_ingested_payloads"
branch_labels = None
depends_on = None


def upgrade():
    # Seed process definition (idempotent)
    op.execute(
        """INSERT INTO process_definitions (id, name, process_key, version, description, status, created_at, updated_at)
           VALUES ('sysproc-accept-suggestion', 'Accept Suggestion', 'accept_suggestion', 1,
                   'System process: accept a schema suggestion into a dashboard item (idempotent).',
                   'system', NOW(), NOW())
           ON CONFLICT (id) DO NOTHING"""
    )

    # Seed process steps (idempotent)
    op.execute(
        """INSERT INTO process_steps (id, process_definition_id, step_key, ordinal, step_type, service_impl, name, created_at, updated_at)
           VALUES ('sps-accept-receive', 'sysproc-accept-suggestion', 'receive', 1, 'start', NULL, 'Accept requested', NOW(), NOW())
           ON CONFLICT (id) DO NOTHING"""
    )
    op.execute(
        """INSERT INTO process_steps (id, process_definition_id, step_key, ordinal, step_type, service_impl, name, created_at, updated_at)
           VALUES ('sps-accept-lookup', 'sysproc-accept-suggestion', 'lookup', 2, 'service', '${suggestionLookupDelegate}', 'Look up suggestion', NOW(), NOW())
           ON CONFLICT (id) DO NOTHING"""
    )
    op.execute(
        """INSERT INTO process_steps (id, process_definition_id, step_key, ordinal, step_type, service_impl, name, created_at, updated_at)
           VALUES ('sps-accept-exists', 'sysproc-accept-suggestion', 'exists', 3, 'gateway', NULL, 'Already accepted?', NOW(), NOW())
           ON CONFLICT (id) DO NOTHING"""
    )
    op.execute(
        """INSERT INTO process_steps (id, process_definition_id, step_key, ordinal, step_type, service_impl, name, created_at, updated_at)
           VALUES ('sps-accept-create', 'sysproc-accept-suggestion', 'create_item', 4, 'service', '${dashboardItemCreatorDelegate}', 'Create dashboard item', NOW(), NOW())
           ON CONFLICT (id) DO NOTHING"""
    )
    op.execute(
        """INSERT INTO process_steps (id, process_definition_id, step_key, ordinal, step_type, service_impl, name, created_at, updated_at)
           VALUES ('sps-accept-existing', 'sysproc-accept-suggestion', 'return_existing', 5, 'end', NULL, 'Return existing item', NOW(), NOW())
           ON CONFLICT (id) DO NOTHING"""
    )
    op.execute(
        """INSERT INTO process_steps (id, process_definition_id, step_key, ordinal, step_type, service_impl, name, created_at, updated_at)
           VALUES ('sps-accept-created', 'sysproc-accept-suggestion', 'created', 6, 'end', NULL, 'Item created', NOW(), NOW())
           ON CONFLICT (id) DO NOTHING"""
    )

    # Seed sequence flows (idempotent)
    op.execute(
        """INSERT INTO sequence_flows (id, process_definition_id, flow_key, source_step, target_step, condition_expression, is_default, name, created_at, updated_at)
           VALUES ('spf-accept-1', 'sysproc-accept-suggestion', 'f_receive_lookup', 'receive', 'lookup', NULL, false, 'to lookup', NOW(), NOW())
           ON CONFLICT (id) DO NOTHING"""
    )
    op.execute(
        """INSERT INTO sequence_flows (id, process_definition_id, flow_key, source_step, target_step, condition_expression, is_default, name, created_at, updated_at)
           VALUES ('spf-accept-2', 'sysproc-accept-suggestion', 'f_lookup_exists', 'lookup', 'exists', NULL, false, 'to gateway', NOW(), NOW())
           ON CONFLICT (id) DO NOTHING"""
    )
    op.execute(
        """INSERT INTO sequence_flows (id, process_definition_id, flow_key, source_step, target_step, condition_expression, is_default, name, created_at, updated_at)
           VALUES ('spf-accept-3', 'sysproc-accept-suggestion', 'f_exists_existing', 'exists', 'return_existing', '${itemExists}', false, 'item exists', NOW(), NOW())
           ON CONFLICT (id) DO NOTHING"""
    )
    op.execute(
        """INSERT INTO sequence_flows (id, process_definition_id, flow_key, source_step, target_step, condition_expression, is_default, name, created_at, updated_at)
           VALUES ('spf-accept-4', 'sysproc-accept-suggestion', 'f_exists_create', 'exists', 'create_item', NULL, true, 'new item', NOW(), NOW())
           ON CONFLICT (id) DO NOTHING"""
    )
    op.execute(
        """INSERT INTO sequence_flows (id, process_definition_id, flow_key, source_step, target_step, condition_expression, is_default, name, created_at, updated_at)
           VALUES ('spf-accept-5', 'sysproc-accept-suggestion', 'f_create_created', 'create_item', 'created', NULL, false, 'to created', NOW(), NOW())
           ON CONFLICT (id) DO NOTHING"""
    )


def downgrade():
    op.execute(
        "DELETE FROM sequence_flows WHERE process_definition_id = 'sysproc-accept-suggestion'"
    )
    op.execute(
        "DELETE FROM process_steps WHERE process_definition_id = 'sysproc-accept-suggestion'"
    )
    op.execute("DELETE FROM process_definitions WHERE id = 'sysproc-accept-suggestion'")
