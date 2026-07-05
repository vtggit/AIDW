"""Structured logging configuration for AICRM backend.

Sets up a consistent log format that includes:
    - timestamp (ISO-8601)
    - log level
    - logger name
    - message
    - request_id (when available from context)

Usage
-----
Call ``setup_logging()`` once during application startup (main.py).
After that, every ``logging.getLogger(__name__)`` call produces
structured output that is easier to grep and correlate.
"""

import logging
import os
from contextvars import ContextVar

# ---------------------------------------------------------------------------
# Context variable for the current request ID
# ---------------------------------------------------------------------------
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    """Return the request ID for the current request context."""
    return request_id_var.get()


def set_request_id(request_id: str) -> None:
    """Set the request ID for the current request context."""
    request_id_var.set(request_id)


def clear_request_id() -> None:
    """Clear the request ID after the request completes."""
    request_id_var.set(None)


# ---------------------------------------------------------------------------
# Custom log record factory that injects request_id
# ---------------------------------------------------------------------------


class _RequestIDLogRecord(logging.LogRecord):
    """Log record that carries the current request ID."""

    @property
    def request_id(self) -> str:
        rid = get_request_id()
        return rid or "-"


# ---------------------------------------------------------------------------
# Log format
# ---------------------------------------------------------------------------

# Compact but structured enough to parse with grep/awk.
# Example:
#   2024-01-15T10:30:00.123Z INFO  [req-abc123] app.auth.security: JWT validation failed: token expired
LOG_FORMAT: str = os.getenv(
    "LOG_FORMAT",
    "%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s",
)
LOG_DATE_FORMAT: str = "%Y-%m-%dT%H:%M:%S%z"
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


def _record_factory(
    name: str,
    level: int,
    fn: str,
    lno: int,
    msg: str,
    args: tuple,
    exc_info: tuple,
    func: str = None,
    sinfo: str = None,
) -> logging.LogRecord:
    """Factory that produces _RequestIDLogRecord instances."""
    return _RequestIDLogRecord(name, level, fn, lno, msg, args, exc_info, func, sinfo)


def setup_logging() -> None:
    """
    Configure application-wide structured logging.

    Should be called once during app bootstrap.  Configures the root logger
    with a formatter that includes the request ID when available.
    """
    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)

    # Use our custom record factory so every log record carries request_id
    logging.setLogRecordFactory(_record_factory)

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))

    root = logging.getLogger()
    root.setLevel(level)
    # Avoid duplicates if uvicorn also configures a handler
    if not root.handlers:
        root.addHandler(handler)

    # Reduce noise from dependencies
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("watchfiles").setLevel(logging.WARNING)

    logging.getLogger(__name__).info("Logging initialised at level %s", LOG_LEVEL)
