"""Index test — uq_sequence_flows_process_definition_id_flow_key created by the new migration."""

import psycopg2
import pytest


@pytest.mark.usefixtures("test_database", "test_env_setup")
def test_sequence_flows_process_definition_id_unique():
    from app.db.connection import get_connection_params

    conn = psycopg2.connect(**get_connection_params())
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = current_schema() "
                "AND tablename = %s AND indexname = %s",
                ("sequence_flows", "uq_sequence_flows_process_definition_id_flow_key"),
            )
            rows = cur.fetchall()
            assert (
                len(rows) == 1
            ), "index uq_sequence_flows_process_definition_id_flow_key missing after migration"
            indexdef = rows[0][0]
            assert "UNIQUE" in indexdef.upper()
            assert "process_definition_id, flow_key" in indexdef.replace(
                '"', ""
            )  # composite spans these columns, in order (quote-tolerant)
    finally:
        conn.close()
