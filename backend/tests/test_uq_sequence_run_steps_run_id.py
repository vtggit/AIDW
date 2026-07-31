"""Index test — uq_sequence_run_steps_run_id_step_id created by the new migration."""

import psycopg2
import pytest


@pytest.mark.usefixtures("test_database", "test_env_setup")
def test_uq_sequence_run_steps_run_id_exists():
    from app.db.connection import get_connection_params

    conn = psycopg2.connect(**get_connection_params())
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = current_schema() "
                "AND tablename = %s AND indexname = %s",
                ("sequence_run_steps", "uq_sequence_run_steps_run_id_step_id"),
            )
            rows = cur.fetchall()
            assert (
                len(rows) == 1
            ), "index uq_sequence_run_steps_run_id_step_id missing after migration"
            indexdef = rows[0][0]
            assert "UNIQUE" in indexdef.upper()
            assert "run_id, step_id" in indexdef.replace(
                '"', ""
            )  # composite spans these columns, in order (quote-tolerant)
    finally:
        conn.close()
