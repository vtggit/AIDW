"""Shared test fixtures for AICRM backend.

Provides:
    - Isolated test database (created and destroyed per session)
    - Alembic migration applied to test database
    - FastAPI TestClient wrapped by httpx
    - Auth token fixtures for admin and non-admin users
    - Per-test transaction rollback for data isolation
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


@pytest.fixture(autouse=True)
def clean_database(client):
    """Truncate all application tables before each test for data isolation.

    Order matters: audit_log must be last (or first) since it has no FK
    constraints, but we truncate it last to ensure clean state.
    """
    import psycopg2

    from app.db.connection import get_connection_params

    conn = psycopg2.connect(**get_connection_params())
    try:
        with conn.cursor() as cur:
            # Truncate all tables in a single statement so PostgreSQL handles
            # foreign-key constraints atomically (e.g. contact_tag_mapping has
            # FKs to both contacts and contact_tags).
            tables = [
                "contact_tag_mapping",
                "contact_tags",
                "contact_consent",
                "contacts",
                "templates",
                "leads",
                "deal_outcomes",
                "activities",
                "settings",
                "audit_log",
            ]
            cur.execute("TRUNCATE TABLE " + ", ".join(tables) + " RESTART IDENTITY;")
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
