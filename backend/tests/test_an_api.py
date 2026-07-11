"""Index test — idx_audit_logs_entity_type_entity_id created by the new migration."""

import psycopg2
import pytest


@pytest.mark.usefixtures("test_database", "test_env_setup")
def test_an_crud():
    from app.db.connection import get_connection_params

    conn = psycopg2.connect(**get_connection_params())
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = current_schema() "
                "AND tablename = %s AND indexname = %s",
                ("audit_logs", "idx_audit_logs_entity_type_entity_id"),
            )
            rows = cur.fetchall()
            assert (
                len(rows) == 1
            ), "index idx_audit_logs_entity_type_entity_id missing after migration"
            indexdef = rows[0][0]
            assert "entity_type, entity_id" in indexdef.replace(
                '"', ""
            )  # composite spans these columns, in order (quote-tolerant)
    finally:
        conn.close()
