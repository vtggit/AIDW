"""Migration tests.

Verifies:
    - The migration baseline applies cleanly to an empty test database
    - Required core tables exist after migration
    - Table schemas match expected structure

Every test in this module explicitly depends on the test_database and
test_app_env fixtures from conftest.py, which guarantees:
    - an isolated test database is created and destroyed per session
    - DB_NAME is set to the test database name in the environment
    - Alembic migrations have been applied before these tests run

This prevents migration tests from accidentally hitting the developer's
normal database or depending on import-order side effects.
"""

import os
import subprocess

import psycopg2
import pytest


def _get_test_db_connection():
    """Get a psycopg2 connection to the test database.

    Uses get_connection_params() which reads DB_NAME from os.environ
    at call time.  The test_app_env fixture ensures DB_NAME points
    at the isolated test database.
    """
    from app.db.connection import get_connection_params

    return psycopg2.connect(**get_connection_params())


@pytest.mark.usefixtures("test_database", "test_env_setup")
def test_migration_applies_cleanly():
    """The Alembic baseline migration should apply without errors.

    This test leverages the session-scoped test_database fixture from
    conftest.py, which already ran migrations. If the migration failed,
    the fixture would have raised an exception and this test would never
    execute.

    We additionally verify the migration was recorded in alembic_version.
    """
    conn = _get_test_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT version_num FROM alembic_version")
            row = cur.fetchone()
            assert row is not None, "alembic_version table should exist after migration"
            # Derive the expected head from the migration scripts so this does
            # not go stale every time a new migration is added.
            from pathlib import Path

            from alembic.config import Config
            from alembic.script import ScriptDirectory

            cfg = Config()
            cfg.set_main_option(
                "script_location",
                str(Path(__file__).resolve().parent.parent / "migrations"),
            )
            expected_head = ScriptDirectory.from_config(cfg).get_current_head()
            assert (
                row[0] == expected_head
            ), f"DB at {row[0]} but latest migration head is {expected_head}"
    finally:
        conn.close()


@pytest.mark.usefixtures("test_database", "test_env_setup")
def test_core_tables_exist_after_migration():
    """All core application tables should exist after migration."""
    expected_tables = {
        "contacts",
        "audit_log",
        "templates",
        "leads",
        "activities",
        "settings",
    }

    conn = _get_test_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name IN (%s, %s, %s, %s, %s, %s)
            """,
                list(expected_tables),
            )
            existing = {row[0] for row in cur.fetchall()}
            missing = expected_tables - existing
            assert not missing, f"Missing tables after migration: {missing}"
    finally:
        conn.close()


@pytest.mark.usefixtures("test_database", "test_env_setup")
def test_contacts_table_schema():
    """Verify contacts table has expected columns."""
    required_columns = {"id", "name", "email", "created_at", "updated_at"}

    conn = _get_test_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'contacts' AND table_schema = 'public'
            """)
            columns = {row[0] for row in cur.fetchall()}
            missing = required_columns - columns
            assert not missing, f"contacts table missing columns: {missing}"
    finally:
        conn.close()


@pytest.mark.usefixtures("test_database", "test_env_setup")
def test_audit_log_table_schema():
    """Verify audit_log table has expected columns."""
    required_columns = {
        "id",
        "entity_type",
        "entity_id",
        "action",
        "actor_sub",
        "timestamp",
    }

    conn = _get_test_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'audit_log' AND table_schema = 'public'
            """)
            columns = {row[0] for row in cur.fetchall()}
            missing = required_columns - columns
            assert not missing, f"audit_log table missing columns: {missing}"
    finally:
        conn.close()


@pytest.mark.usefixtures("test_database", "test_env_setup")
def test_activities_table_has_indexes():
    """Verify activities table has expected indexes."""
    expected_indexes = {"idx_activities_occurred_at", "idx_activities_status"}

    conn = _get_test_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'activities' AND schemaname = 'public'
            """)
            indexes = {row[0] for row in cur.fetchall()}
            missing = expected_indexes - indexes
            assert not missing, f"activities table missing indexes: {missing}"
    finally:
        conn.close()


@pytest.mark.usefixtures("test_database", "test_env_setup")
def test_settings_table_has_default_id():
    """Verify settings table has a server default for the id column."""
    conn = _get_test_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT column_default
                FROM information_schema.columns
                WHERE table_name = 'settings' AND table_schema = 'public' AND column_name = 'id'
            """)
            row = cur.fetchone()
            assert row is not None, "settings.id column should exist"
            assert row[0] is not None, "settings.id should have a server default"
    finally:
        conn.close()


@pytest.mark.usefixtures("test_database", "test_env_setup")
def test_migration_downgrade_and_upgrade():
    """Verify migration can downgrade and re-upgrade cleanly."""
    backend_dir = os.path.dirname(os.path.dirname(__file__))
    alembic_ini = os.path.join(backend_dir, "alembic.ini")

    # Use the same env that test_app_env sets (DB_NAME = aicrm_test_db)
    env = {**os.environ, "DB_NAME": "aicrm_test_db"}

    # Downgrade to base
    result = subprocess.run(
        ["python3", "-m", "alembic", "-c", alembic_ini, "downgrade", "base"],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Downgrade failed: {result.stderr}"

    # Verify tables are gone
    conn = _get_test_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'contacts'
            """)
            count = cur.fetchone()[0]
            assert count == 0, "contacts table should be dropped after downgrade"
    finally:
        conn.close()

    # Re-upgrade
    result = subprocess.run(
        ["python3", "-m", "alembic", "-c", alembic_ini, "upgrade", "head"],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Re-upgrade failed: {result.stderr}"

    # Verify tables are back
    conn = _get_test_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'contacts'
            """)
            count = cur.fetchone()[0]
            assert count == 1, "contacts table should exist after re-upgrade"
    finally:
        conn.close()
