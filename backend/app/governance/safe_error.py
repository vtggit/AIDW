"""Fixed-shape, message-free error detail for audit rows (issue #823).

``safe_error_detail`` renders an exception for persistence in an ``error_detail``
column (the retention sweep's failure path, the erasure executor's retry reset)
without ever leaking the exception's message: the detail is built only from the
exception's class name and, for a database error, its SQLSTATE code —
"IntegrityError (SQLSTATE 23503)". The message text, its ``DETAIL``/``HINT``
lines, and any value in them never reach the audit row; the full exception is
still written to the server log at the failure site, as before.

The function never raises: an exception whose class name cannot be read degrades
to ``"unknown failure"``, and a database error whose SQLSTATE code cannot be
read degrades to the class name alone.
"""

from __future__ import annotations

UNKNOWN_FAILURE = "unknown failure"


def safe_error_detail(exc: BaseException) -> str:
    """Render ``exc`` as a fixed-shape detail string.

    The shape is ``"<ClassName>"``, or — for a database error that carries a
    SQLSTATE code — ``"<ClassName> (SQLSTATE <code>)"``. Only the class name
    and the code are used: the message, its DETAIL/HINT lines, and any value in
    them are never read. Never raises: returns ``"unknown failure"`` when the
    class name cannot be read, and the class name alone when the SQLSTATE code
    cannot be read.
    """
    try:
        class_name = type(exc).__name__
    except Exception:
        return UNKNOWN_FAILURE
    if not isinstance(class_name, str) or not class_name.strip():
        return UNKNOWN_FAILURE
    code = getattr(exc, "pgcode", None)
    if isinstance(code, str) and code.strip():
        return f"{class_name} (SQLSTATE {code.strip()})"
    return class_name
