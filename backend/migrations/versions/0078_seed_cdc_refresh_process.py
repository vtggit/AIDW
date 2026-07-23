"""seed CDC refresh process definition, steps, and flows.

Revision ID: 0078_seed_cdc_refresh
Revises: 0077_seed_rtbf_erasure
Create Date: 2024-01-01 00:00:00.000000
"""

from alembic import op

revision = "0078_seed_cdc_refresh"
down_revision = "0077_seed_rtbf_erasure"
branch_labels = None
depends_on = None


def upgrade():
    # Seed process definition (idempotent)
    op.execute("""INSERT INTO process_definitions
           (id, name, process_key, version, description, status, created_at, updated_at)
           VALUES ('sysproc-cdc-refresh', 'CDC Source Refresh', 'cdc_refresh', 1,
                   'System process: refresh a source via CDC — fetch a page and apply rows to the op-log.',
                   'system', NOW(), NOW())
           ON CONFLICT (id) DO NOTHING;""")

    # Seed process steps (idempotent)
    op.execute("""INSERT INTO process_steps
           (id, process_definition_id, step_key, ordinal, step_type, service_impl, name, created_at, updated_at)
           VALUES
             ('sps-cdc-claimed', 'sysproc-cdc-refresh', 'claimed', 1, 'start', NULL, 'Run claimed', NOW(), NOW()),
             ('sps-cdc-context', 'sysproc-cdc-refresh', 'load_context', 2, 'service', '${contextLoader}', 'Load pipeline context', NOW(), NOW()),
             ('sps-cdc-fetch', 'sysproc-cdc-refresh', 'fetch_page', 3, 'service', '${sourcePageFetcher}', 'Fetch source page', NOW(), NOW()),
             ('sps-cdc-apply', 'sysproc-cdc-refresh', 'apply_rows', 4, 'service', '${rowsApplier}', 'Apply rows and advance watermark', NOW(), NOW()),
             ('sps-cdc-outcome', 'sysproc-cdc-refresh', 'outcome', 5, 'gateway', NULL, 'Run succeeded?', NOW(), NOW()),
             ('sps-cdc-fail', 'sysproc-cdc-refresh', 'record_failure', 6, 'service', '${runFailer}', 'Record failure', NOW(), NOW()),
             ('sps-cdc-success', 'sysproc-cdc-refresh', 'record_success', 7, 'service', '${runFinalizer}', 'Record success', NOW(), NOW()),
             ('sps-cdc-failed', 'sysproc-cdc-refresh', 'failed', 8, 'end', NULL, 'Run failed', NOW(), NOW()),
             ('sps-cdc-succeeded', 'sysproc-cdc-refresh', 'succeeded', 9, 'end', NULL, 'Run succeeded', NOW(), NOW())
           ON CONFLICT (id) DO NOTHING;""")

    # Seed sequence flows (idempotent)
    op.execute("""INSERT INTO sequence_flows
           (id, process_definition_id, flow_key, source_step, target_step, condition_expression, is_default, name, created_at, updated_at)
           VALUES
             ('spf-cdc-1', 'sysproc-cdc-refresh', 'f_claimed_context', 'claimed', 'load_context', NULL, false, 'to context', NOW(), NOW()),
             ('spf-cdc-2', 'sysproc-cdc-refresh', 'f_context_fetch', 'load_context', 'fetch_page', NULL, false, 'to fetch', NOW(), NOW()),
             ('spf-cdc-3', 'sysproc-cdc-refresh', 'f_fetch_apply', 'fetch_page', 'apply_rows', NULL, false, 'to apply', NOW(), NOW()),
             ('spf-cdc-4', 'sysproc-cdc-refresh', 'f_apply_outcome', 'apply_rows', 'outcome', NULL, false, 'to gateway', NOW(), NOW()),
             ('spf-cdc-5', 'sysproc-cdc-refresh', 'f_outcome_fail', 'outcome', 'record_failure', '${failed}', false, 'on failure', NOW(), NOW()),
             ('spf-cdc-6', 'sysproc-cdc-refresh', 'f_outcome_success', 'outcome', 'record_success', NULL, true, 'on success', NOW(), NOW()),
             ('spf-cdc-7', 'sysproc-cdc-refresh', 'f_fail_failed', 'record_failure', 'failed', NULL, false, 'to failed', NOW(), NOW()),
             ('spf-cdc-8', 'sysproc-cdc-refresh', 'f_success_succeeded', 'record_success', 'succeeded', NULL, false, 'to succeeded', NOW(), NOW())
           ON CONFLICT (id) DO NOTHING;""")


def downgrade():
    # Delete flows by fixed ids
    op.execute(
        """DELETE FROM sequence_flows WHERE id IN
           ('spf-cdc-1', 'spf-cdc-2', 'spf-cdc-3', 'spf-cdc-4', 'spf-cdc-5', 'spf-cdc-6', 'spf-cdc-7', 'spf-cdc-8');"""
    )
    # Delete steps by fixed ids
    op.execute(
        """DELETE FROM process_steps WHERE id IN
           ('sps-cdc-claimed', 'sps-cdc-context', 'sps-cdc-fetch', 'sps-cdc-apply', 'sps-cdc-outcome',
            'sps-cdc-fail', 'sps-cdc-success', 'sps-cdc-failed', 'sps-cdc-succeeded');"""
    )
    # Delete definition by fixed id
    op.execute("DELETE FROM process_definitions WHERE id = 'sysproc-cdc-refresh';")
