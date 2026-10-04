"""PostgreSQL connection helper."""

import os
import re
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

from app.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER

_DIGITS = re.compile(r"\d+", re.ASCII)


def _statement_timeout_ms() -> int | None:
    """Return ``DB_STATEMENT_TIMEOUT_MS`` as a positive integer, or ``None``.

    Unset, empty, zero, negative, or non-integer values all yield ``None`` so
    connections behave exactly as they do today.
    """
    raw = os.getenv("DB_STATEMENT_TIMEOUT_MS", "")
    if not _DIGITS.fullmatch(raw):
        return None
    value = int(raw)
    return value if value > 0 else None


def get_connection_params() -> dict:
    """Return a dict of connection parameters.

    Reads from os.environ at call time so tests can override DB_NAME
    (or any other DB setting) by setting environment variables before
    the call.  Falls back to the module-level defaults from app.config.

    ``DB_STATEMENT_TIMEOUT_MS`` is read the same way: when it holds a
    positive integer, the parameters carry
    ``options="-c statement_timeout=<value>"`` so PostgreSQL aborts
    runaway queries; any other value is ignored.

    Useful for tests and external tools that need the raw parameters
    rather than a live connection object.
    """
    params = {
        "host": os.getenv("DB_HOST", DB_HOST),
        "port": int(os.getenv("DB_PORT", str(DB_PORT))),
        "dbname": os.getenv("DB_NAME", DB_NAME),
        "user": os.getenv("DB_USER", DB_USER),
        "password": os.getenv("DB_PASSWORD", DB_PASSWORD),
    }
    statement_timeout_ms = _statement_timeout_ms()
    if statement_timeout_ms is not None:
        params["options"] = f"-c statement_timeout={statement_timeout_ms}"
    return params


def get_connection():
    """Return a new psycopg2 connection to the PostgreSQL database."""
    return psycopg2.connect(**get_connection_params())


@contextmanager
def get_cursor():
    """Context manager that yields a server-side cursor and auto-commits or rolls back."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
