"""Seed RTBF Erasure system process definition."""

from alembic import op

revision = "0077_seed_rtbf_erasure"
down_revision = "0076_seed_accept_suggestion"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        INSERT INTO process_definitions (id, name, process_key, version, description, status, created_at, updated_at)
        VALUES ('sysproc-rtbf-erasure', 'RTBF Erasure', 'rtbf_erasure', 1, 'System process: erase a subject on a verified deletion request (all-or-nothing).', 'system', NOW(), NOW())
        ON CONFLICT (id) DO NOTHING;
    """)

    op.execute("""
        INSERT INTO process_steps (id, step_key, ordinal, step_type, service_impl, name, process_definition_id, created_at, updated_at)
        VALUES
            ('sps-rtbf-claimed', 'claimed', 1, 'start', NULL, 'Request claimed', 'sysproc-rtbf-erasure', NOW(), NOW()),
            ('sps-rtbf-erase', 'erase', 2, 'service', '${recordEraser}', 'Erase op-log and landing rows', 'sysproc-rtbf-erasure', NOW(), NOW()),
            ('sps-rtbf-scrub', 'scrub', 3, 'service', '${profileScrubber}', 'Scrub field-profile stats', 'sysproc-rtbf-erasure', NOW(), NOW()),
            ('sps-rtbf-suppress', 'suppress', 4, 'service', '${suppressionWriter}', 'Write suppression entry', 'sysproc-rtbf-erasure', NOW(), NOW()),
            ('sps-rtbf-committed', 'committed', 5, 'gateway', NULL, 'Transaction committed?', 'sysproc-rtbf-erasure', NOW(), NOW()),
            ('sps-rtbf-finalize', 'finalize', 6, 'service', '${requestFinalizer}', 'Finalize request', 'sysproc-rtbf-erasure', NOW(), NOW()),
            ('sps-rtbf-retry', 'retry', 7, 'end', NULL, 'Reset for retry', 'sysproc-rtbf-erasure', NOW(), NOW()),
            ('sps-rtbf-completed', 'completed', 8, 'end', NULL, 'Erasure completed', 'sysproc-rtbf-erasure', NOW(), NOW())
        ON CONFLICT (id) DO NOTHING;
    """)

    op.execute("""
        INSERT INTO sequence_flows (id, flow_key, source_step, target_step, condition_expression, is_default, name, process_definition_id, created_at, updated_at)
        VALUES
            ('spf-rtbf-1', 'f_claimed_erase', 'claimed', 'erase', NULL, false, 'to erase', 'sysproc-rtbf-erasure', NOW(), NOW()),
            ('spf-rtbf-2', 'f_erase_scrub', 'erase', 'scrub', NULL, false, 'to scrub', 'sysproc-rtbf-erasure', NOW(), NOW()),
            ('spf-rtbf-3', 'f_scrub_suppress', 'scrub', 'suppress', NULL, false, 'to suppress', 'sysproc-rtbf-erasure', NOW(), NOW()),
            ('spf-rtbf-4', 'f_suppress_committed', 'suppress', 'committed', NULL, false, 'to gateway', 'sysproc-rtbf-erasure', NOW(), NOW()),
            ('spf-rtbf-5', 'f_committed_retry', 'committed', 'retry', '${failed}', false, 'on failure', 'sysproc-rtbf-erasure', NOW(), NOW()),
            ('spf-rtbf-6', 'f_committed_finalize', 'committed', 'finalize', NULL, true, 'committed', 'sysproc-rtbf-erasure', NOW(), NOW()),
            ('spf-rtbf-7', 'f_finalize_completed', 'finalize', 'completed', NULL, false, 'to completed', 'sysproc-rtbf-erasure', NOW(), NOW())
        ON CONFLICT (id) DO NOTHING;
    """)


def downgrade():
    op.execute(
        "DELETE FROM sequence_flows WHERE process_definition_id = 'sysproc-rtbf-erasure';"
    )
    op.execute(
        "DELETE FROM process_steps WHERE process_definition_id = 'sysproc-rtbf-erasure';"
    )
    op.execute("DELETE FROM process_definitions WHERE id = 'sysproc-rtbf-erasure';")
