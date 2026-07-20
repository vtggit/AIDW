"""Composite-FK test — fk_sequence_flows_process_definition_id_source_step_pr_8b381891 on sequence_flows(process_definition_id, source_step) -> process_steps(process_definition_id, step_key)."""

import psycopg2
import pytest


@pytest.mark.usefixtures("test_database", "test_env_setup")
def test_sequence_flows_process_definition_id_source_step_fk():
    from app.db.connection import get_connection_params

    conn = psycopg2.connect(**get_connection_params())
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_get_constraintdef(c.oid) "
                "FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
                "WHERE c.conname = %s AND c.contype = 'f' AND t.relname = %s "
                "AND c.connamespace = current_schema()::regnamespace",
                (
                    "fk_sequence_flows_process_definition_id_source_step_pr_8b381891",
                    "sequence_flows",
                ),
            )
            rows = cur.fetchall()
            assert (
                len(rows) == 1
            ), "composite FK fk_sequence_flows_process_definition_id_source_step_pr_8b381891 missing after migration"
            cdef = rows[0][0].replace('"', "")
            assert "FOREIGN KEY (process_definition_id, source_step)" in cdef, cdef
            assert (
                "REFERENCES process_steps(process_definition_id, step_key)" in cdef
            ), cdef
    finally:
        conn.close()
