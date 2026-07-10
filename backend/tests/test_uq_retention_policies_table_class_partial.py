"""Index test — uq_retention_policies_table_class_partial created by the new migration."""

import psycopg2
import pytest


@pytest.mark.usefixtures("test_database", "test_env_setup")
def test_uq_retention_policies_table_class_partial_exists():
    from app.db.connection import get_connection_params

    conn = psycopg2.connect(**get_connection_params())
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = current_schema() "
                "AND tablename = %s AND indexname = %s",
                ("retention_policies", "uq_retention_policies_table_class_partial"),
            )
            rows = cur.fetchall()
            assert (
                len(rows) == 1
            ), "index uq_retention_policies_table_class_partial missing after migration"
            indexdef = rows[0][0]
            assert "UNIQUE" in indexdef.upper()
            assert "WHERE" in indexdef.upper()
    finally:
        conn.close()
