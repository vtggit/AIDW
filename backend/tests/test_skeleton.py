"""AIDW warehouse-infra skeleton smoke tests — health, auth, audit, and the audit_log baseline.
Purpose-built for the reduced skeleton (no inherited AICRM domain assumptions); the warehouse
domain grows its own tests via CodeAgent."""
import psycopg2
import pytest


def test_health(client):
    assert client.get("/api/health").status_code == 200


def test_auth_config_is_public(client):
    assert client.get("/api/auth/config").status_code == 200


def test_audit_requires_authentication(client):
    assert client.get("/api/audit").status_code in (401, 403)


def test_audit_admin_ok(client, admin_headers):
    assert client.get("/api/audit", headers=admin_headers).status_code == 200


@pytest.mark.usefixtures("test_database", "test_env_setup")
def test_audit_log_table_exists():
    from app.db.connection import get_connection_params

    conn = psycopg2.connect(**get_connection_params())
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.audit_log')")
            assert cur.fetchone()[0] == "audit_log"
    finally:
        conn.close()
