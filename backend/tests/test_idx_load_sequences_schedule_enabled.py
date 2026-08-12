"""Index test — idx_load_sequences_schedule_enabled created by the new migration."""

import psycopg2
import pytest


@pytest.mark.usefixtures("test_database", "test_env_setup")
def test_idx_load_sequences_schedule_enabled_exists():
    from app.db.connection import get_connection_params

    conn = psycopg2.connect(**get_connection_params())
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = current_schema() "
                "AND tablename = %s AND indexname = %s",
                ("load_sequences", "idx_load_sequences_schedule_enabled"),
            )
            rows = cur.fetchall()
            assert (
                len(rows) == 1
            ), "index idx_load_sequences_schedule_enabled missing after migration"
            indexdef = rows[0][0]
            assert indexdef
    finally:
        conn.close()
