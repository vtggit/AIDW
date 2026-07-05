"""Migration tests — the AIDW warehouse-infra baseline (audit_log). AICRM domain-table
assertions were removed with the CRM entities; the warehouse grows its own tables via CodeAgent.
"""
import psycopg2
import pytest


def _get_test_db_connection():
    from app.db.connection import get_connection_params

    return psycopg2.connect(**get_connection_params())


@pytest.mark.usefixtures("test_database", "test_env_setup")
def test_migration_applies_cleanly():
    """The Alembic baseline applies without errors (the conftest ran `alembic upgrade head`)."""
    conn = _get_test_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT version_num FROM alembic_version")
            assert cur.fetchone() is not None
    finally:
        conn.close()


@pytest.mark.usefixtures("test_database", "test_env_setup")
def test_audit_log_table_schema():
    """The infra audit_log table exists after migration with its expected columns."""
    required = {"id", "entity_type", "entity_id", "action", "actor_sub", "timestamp"}
    conn = _get_test_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'audit_log' AND table_schema = 'public'"
            )
            columns = {row[0] for row in cur.fetchall()}
            assert not (required - columns), "audit_log missing: %s" % (required - columns)
    finally:
        conn.close()
