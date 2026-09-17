"""Shared test fixtures for AICRM backend.

Provides:
    - Isolated test database (created and destroyed per session)
    - Alembic migration applied to test database
    - FastAPI TestClient wrapped by httpx
    - Auth token fixtures for admin and non-admin users
    - Per-test cleanup: every application table is emptied before each test
      (seed rows inserted by migrations are kept)
"""

import os
import subprocess

# ---------------------------------------------------------------------------
# Ensure the backend package is importable
# ---------------------------------------------------------------------------
import sys
import tempfile
from collections.abc import Generator
from contextlib import contextmanager

import psycopg2
import psycopg2.sql
import pytest
from alembic.config import Config as AlembicConfig
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# Test database configuration
# ---------------------------------------------------------------------------
_TEST_DB_NAME = "aicrm_test_db"

# Read host/port/user/password from env (same as production config)
_DB_HOST = os.getenv("DB_HOST", "localhost")
_DB_PORT = os.getenv("DB_PORT", "5432")
_DB_USER = os.getenv("DB_USER", "aicrm")
_DB_PASSWORD = os.getenv("DB_PASSWORD", "aicrm")


def _get_admin_connection():
    """Get a connection as the DB superuser for creating/dropping databases.

    Tries the configured user first; falls back to 'postgres' for
    database-level operations if needed.
    """
    # Try connecting as the configured user
    try:
        conn = psycopg2.connect(
            host=_DB_HOST,
            port=_DB_PORT,
            user=_DB_USER,
            password=_DB_PASSWORD,
            dbname="postgres",
        )
        conn.autocommit = True
        return conn
    except psycopg2.OperationalError:
        pass

    # Fall back to postgres superuser
    return psycopg2.connect(
        host=_DB_HOST,
        port=_DB_PORT,
        user="postgres",
        password=_DB_PASSWORD,
        dbname="postgres",
    )


def _create_test_db() -> None:
    """Create the test database if it doesn't exist."""
    conn = _get_admin_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                psycopg2.sql.SQL("SELECT 1 FROM pg_database WHERE datname = %s"),
                [_TEST_DB_NAME],
            )
            exists = cur.fetchone() is not None
            if not exists:
                cur.execute(
                    psycopg2.sql.SQL("CREATE DATABASE {}").format(
                        psycopg2.sql.Identifier(_TEST_DB_NAME)
                    )
                )
    finally:
        conn.close()


def _drop_test_db() -> None:
    """Drop the test database if it exists."""
    conn = _get_admin_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                psycopg2.sql.SQL(
                    "SELECT pid FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()"
                ),
                [_TEST_DB_NAME],
            )
            # Terminate existing connections
            for row in cur.fetchall():
                cur.execute(
                    psycopg2.sql.SQL("SELECT pg_terminate_backend({})").format(
                        psycopg2.sql.Literal(row[0])
                    )
                )
            cur.execute(
                psycopg2.sql.SQL("DROP DATABASE IF EXISTS {}").format(
                    psycopg2.sql.Identifier(_TEST_DB_NAME)
                )
            )
    finally:
        conn.close()


def _run_migrations() -> None:
    """Run Alembic migrations against the test database."""
    env = {
        **os.environ,
        "DB_NAME": _TEST_DB_NAME,
    }
    backend_dir = os.path.dirname(os.path.dirname(__file__))
    alembic_ini = os.path.join(backend_dir, "alembic.ini")

    subprocess.run(
        ["python3", "-m", "alembic", "-c", alembic_ini, "upgrade", "head"],
        cwd=backend_dir,
        env=env,
        check=True,
    )


def _reset_connection_pool() -> None:
    """Close all cached psycopg2 connections so tests get fresh connections."""
    from app.db import connection as db_conn

    if hasattr(db_conn, "_pool") and db_conn._pool is not None:
        try:
            db_conn._pool.close()
        except Exception:
            pass
        db_conn._pool = None


# ---------------------------------------------------------------------------
# Session-scoped fixtures: create DB, run migrations
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def test_database() -> Generator[None, None, None]:
    """Create and migrate the test database for the entire test session."""
    _drop_test_db()
    _create_test_db()
    _run_migrations()
    yield
    _drop_test_db()


# ---------------------------------------------------------------------------
# Application fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def test_app_env():
    """Return environment overrides for the test app."""
    return {
        **os.environ,
        "DB_NAME": _TEST_DB_NAME,
        "AUTH_MODE": "development",
        "AUTH_DEV_TOKEN": "dev-secret-token",
    }


@pytest.fixture(scope="session")
def test_env_setup(test_app_env):
    """Apply test environment variables to os.environ for the test session.

    This fixture actually mutates os.environ so that modules reading
    env vars at call time (e.g. get_connection_params()) see the correct
    test database name.  It cleans up after the session.

    Use this fixture in migration tests and any other tests that need
    the test DB env but don't need the full FastAPI app.
    """
    old_env = dict(os.environ)
    os.environ.clear()
    os.environ.update(test_app_env)
    yield
    os.environ.clear()
    os.environ.update(old_env)


@pytest.fixture(scope="function")
def app(test_database, test_app_env):
    """Create a Fresh FastAPI app instance for each test.

    The app is created with test-specific environment variables.
    Connection pool is reset before each test.
    Auth config modules are reloaded so env changes take effect.
    """
    import importlib

    # Temporarily override environment
    old_env = dict(os.environ)
    os.environ.update(test_app_env)

    # Reset DB connection pool so we connect to the test database
    _reset_connection_pool()

    # Reload auth config modules so they pick up the new env vars
    import app.auth.config as auth_config
    import app.auth.dependencies as auth_deps
    import app.auth.security as auth_security

    importlib.reload(auth_config)
    importlib.reload(auth_security)
    importlib.reload(auth_deps)

    # Import app factory after env is set and modules are reloaded
    from app.main import create_app

    application = create_app()

    yield application

    # Restore environment
    os.environ.clear()
    os.environ.update(old_env)

    # Reset pool after test
    _reset_connection_pool()


@pytest.fixture(scope="function")
def client(app):
    """Return a FastAPI TestClient wrapped around the test app."""
    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Auth token fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_token():
    """Development-mode admin token."""
    return "dev-secret-token:admin"


@pytest.fixture
def user_token():
    """Development-mode non-admin user token."""
    return "dev-secret-token:user"


@pytest.fixture
def admin_headers(admin_token):
    """Authorization headers for admin user."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def user_headers(user_token):
    """Authorization headers for non-admin user."""
    return {"Authorization": f"Bearer {user_token}"}


# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------


# Tables the migrations SEED (0076-0078: the built-in process definitions with their steps and
# flows). They reference only each other and nothing references them, so every other table can
# be truncated with CASCADE without touching them; rows a test adds to them are deleted, the
# seeded rows stay. Child tables first.
_SEEDED_TABLES = ("sequence_flows", "process_steps", "process_definitions")
_seed_ids: dict = {}
_app_tables: list = []  # read once per session: migrations do not run between tests


@pytest.fixture(autouse=True)
def clean_database(client):
    """Empty every application table before each test, so no test sees another test's rows.

    The table list is read from the database (every table of the current schema except
    Alembic's bookkeeping), so a new migration's tables are covered without touching this
    fixture. Seeded tables keep exactly the rows the migrations inserted: their ids are
    captured once, before the first test has written anything.
    """
    import psycopg2
    import psycopg2.errors  # noqa: F401  (the FK-violation class used below)

    from app.db.connection import get_connection_params

    conn = psycopg2.connect(**get_connection_params())
    try:
        with conn.cursor() as cur:
            if not _app_tables:
                cur.execute(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = current_schema() AND tablename <> 'alembic_version' "
                    "ORDER BY tablename"
                )
                _app_tables.extend(row[0] for row in cur.fetchall())
            tables = list(_app_tables)
            for table in _SEEDED_TABLES:
                if table not in tables:
                    continue
                if table not in _seed_ids:
                    cur.execute(f'SELECT id FROM "{table}"')
                    _seed_ids[table] = [row[0] for row in cur.fetchall()]
                cur.execute(
                    f'DELETE FROM "{table}" WHERE NOT (id = ANY(%s))',
                    (_seed_ids[table],),
                )
            rest = [t for t in tables if t not in _SEEDED_TABLES]
            if rest:
                # TRUNCATE costs a file operation per table, and a test writes to a handful of
                # them: one probe finds the tables that hold rows, and only those are emptied.
                cur.execute(
                    " UNION ALL ".join(
                        f"SELECT '{t}' WHERE EXISTS (SELECT 1 FROM \"{t}\")"
                        for t in rest
                    )
                )
                rest = [row[0] for row in cur.fetchall()]
            if "audit_log" in rest:
                cur.execute('TRUNCATE TABLE "audit_log" RESTART IDENTITY;')
                rest.remove("audit_log")
            # A test leaves a handful of rows, so DELETE beats TRUNCATE (a file operation per
            # table). A parent whose children still hold rows fails its DELETE; it is retried
            # after them. Whatever is left after the passes falls back to TRUNCATE ... CASCADE.
            pending = rest
            for _ in range(len(rest) + 1):
                if not pending:
                    break
                blocked = []
                for table in pending:
                    cur.execute("SAVEPOINT clean_one")
                    try:
                        cur.execute(f'DELETE FROM "{table}"')
                        cur.execute("RELEASE SAVEPOINT clean_one")
                    except psycopg2.errors.ForeignKeyViolation:
                        cur.execute("ROLLBACK TO SAVEPOINT clean_one")
                        blocked.append(table)
                if len(blocked) == len(pending):
                    break
                pending = blocked
            if pending:
                cur.execute(
                    "TRUNCATE TABLE "
                    + ", ".join(f'"{t}"' for t in pending)
                    + " RESTART IDENTITY CASCADE;"
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@pytest.fixture
def empty_audit_log(client):
    """Ensure the audit log is empty before a test."""
    # Handled by clean_database autouse fixture
    pass
