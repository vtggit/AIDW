"""Index test — idx_companies_deleted_at_partial created by the new migration."""

import psycopg2
import pytest


@pytest.mark.usefixtures("test_database", "test_env_setup")
def test_idx_companies_deleted_at_partial_exists():
    from app.db.connection import get_connection_params

    conn = psycopg2.connect(**get_connection_params())
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = current_schema() "
                "AND tablename = %s AND indexname = %s",
                ("companies", "idx_companies_deleted_at_partial"),
            )
            rows = cur.fetchall()
            assert (
                len(rows) == 1
            ), "index idx_companies_deleted_at_partial missing after migration"
            indexdef = rows[0][0]
            assert "WHERE" in indexdef.upper()
    finally:
        conn.close()
