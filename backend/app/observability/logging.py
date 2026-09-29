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
import re
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
    """Log record that carries the current request ID.

    ``request_id`` is a plain instance attribute, always present in the
    record's ``__dict__``: %-style formatters resolve ``%(request_id)s``
    from the record's ``__dict__`` and never see class-level properties,
    so the value is materialised up front by :func:`_record_factory`.
    """


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


# Request IDs are caller-controllable (e.g. the X-Request-ID header).
# ASCII control characters (newline, CR, NUL, ...) would split one record
# across physical lines and corrupt line-based log output, so they are
# stripped when the value is materialised onto the record.
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")


def _sanitize_request_id(value: object) -> str:
    """Return ``value`` with ASCII control characters removed."""
    if not isinstance(value, str):
        value = str(value)
    return _CONTROL_CHARS_RE.sub("", value)


# Canonical LOG_LEVEL names.  Anything else falls back to INFO instead of
# crashing setup_logging() (e.g. values that happen to shadow attributes
# of the logging module such as "handlers" or "root", which would make
# Logger.setLevel() raise).
_LOG_LEVELS = {
    "NOTSET": logging.NOTSET,
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def _resolve_log_level(raw: object) -> int:
    """Map a LOG_LEVEL value to a numeric logging level.

    Only the canonical level names are accepted; unknown or hostile
    values fall back to ``INFO``.
    """
    if not isinstance(raw, str):
        return logging.INFO
    return _LOG_LEVELS.get(raw.strip().upper(), logging.INFO)


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
    """Factory that produces _RequestIDLogRecord instances.

    Resolves the request ID from the current context (defaulting to the
    stable value ``"-"`` when no request is in progress) and stores it
    directly on the record so the formatter can always find it in
    ``record.__dict__`` before formatting.
    """
    record = _RequestIDLogRecord(name, level, fn, lno, msg, args, exc_info, func, sinfo)
    record.request_id = _sanitize_request_id(get_request_id() or "-")
    return record


def setup_logging() -> None:
    """
    Configure application-wide structured logging.

    Should be called once during app bootstrap.  Configures the root logger
    with a formatter that includes the request ID when available.
    """
    raw_level = os.getenv("LOG_LEVEL", LOG_LEVEL)
    level = _resolve_log_level(raw_level)

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

    logging.getLogger(__name__).info("Logging initialised at level %s", raw_level)
