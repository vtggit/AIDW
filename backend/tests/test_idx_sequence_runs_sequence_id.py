"""Index test — idx_sequence_runs_sequence_id_status created by the new migration."""

import psycopg2
import pytest


@pytest.mark.usefixtures("test_database", "test_env_setup")
def test_idx_sequence_runs_sequence_id_exists():
    from app.db.connection import get_connection_params

    conn = psycopg2.connect(**get_connection_params())
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = current_schema() "
                "AND tablename = %s AND indexname = %s",
                ("sequence_runs", "idx_sequence_runs_sequence_id_status"),
            )
            rows = cur.fetchall()
            assert (
                len(rows) == 1
            ), "index idx_sequence_runs_sequence_id_status missing after migration"
            indexdef = rows[0][0]
            assert "sequence_id, status" in indexdef.replace(
                '"', ""
            )  # composite spans these columns, in order (quote-tolerant)
    finally:
        conn.close()
