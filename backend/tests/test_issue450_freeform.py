"""Issue #450 freeform — ``request_id`` must survive %-style formatting.

The production ``LOG_FORMAT`` contains ``%(request_id)s``.  %-style
formatting resolves that key from ``record.__dict__``, so the value has
to be materialised on every record before formatting.  This test proves
the AC-1/AC-2 contract:

* ``setup_logging()`` installs a record factory that puts ``request_id``
  into each record's ``__dict__`` (no reliance on
  ``Formatter(defaults=)`` behaviour).
* Records created outside a request (worker, scripts, startup) render
  ``request_id`` as ``-``.
* Records created while ``set_request_id('req-test')`` is in the
  current context keep the real request id.
* No logging error (e.g. ``KeyError: 'request_id'``) is written to
  stderr while the records are formatted and emitted.

plus the two regression defects:

* A caller-controlled request id containing newline/CR/NUL must not
  split a record across physical lines (line-based log output stays
  intact).
* ``setup_logging()`` must not crash when ``LOG_LEVEL`` holds an
  invalid value.
"""

import io
import logging

from app.observability.logging import (
    LOG_DATE_FORMAT,
    LOG_FORMAT,
    clear_request_id,
    set_request_id,
    setup_logging,
)


def _capturing_handler():
    """Attach a dedicated StreamHandler using the production format.

    Returns ``(handler, buffer)`` so the caller can inspect the
    formatted lines and remove the handler again.
    """
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
    logging.getLogger().addHandler(handler)
    return handler, buffer


def test_issue450_freeform(capsys, monkeypatch):
    """Production LOG_FORMAT renders request_id cleanly in both contexts."""
    setup_logging()

    handler, buffer = _capturing_handler()
    module_logger = logging.getLogger("app.observability.issue450")
    try:
        # --- No request in progress: request_id must render as '-' -------
        clear_request_id()
        module_logger.info("issue450 outside-request marker")

        # --- Request in progress: the real id must render ----------------
        set_request_id("req-test")
        try:
            module_logger.info("issue450 inside-request marker")
        finally:
            clear_request_id()

        # --- Hostile request id: newline/CR/NUL must not split the line --
        set_request_id("req\nINJECTED\r\x00")
        try:
            module_logger.info("issue450 newline-request marker")
        finally:
            clear_request_id()
    finally:
        logging.getLogger().removeHandler(handler)
        handler.flush()

    raw = buffer.getvalue()
    lines = raw.splitlines()

    outside = [line for line in lines if "issue450 outside-request marker" in line]
    inside = [line for line in lines if "issue450 inside-request marker" in line]
    newline = [line for line in lines if "issue450 newline-request marker" in line]

    assert len(outside) == 1
    assert len(inside) == 1
    assert len(newline) == 1
    # Both records formatted cleanly under the production format.
    assert "[-]" in outside[0]
    assert "[req-test]" in inside[0]
    assert "app.observability.issue450" in outside[0]
    assert "app.observability.issue450" in inside[0]

    # Newline/CR/NUL from a hostile request id must not corrupt line-based
    # output: the record stays on a single physical line, the rendered id
    # carries no control characters, and no fragment of the injected id
    # leaks onto any other line.
    assert "[reqINJECTED]" in newline[0]
    assert "\n" not in newline[0]
    assert "\r" not in raw
    assert "\x00" not in raw
    other_lines = [
        line for line in lines if "issue450 newline-request marker" not in line
    ]
    assert not any("INJECTED" in line for line in other_lines)

    # No logging error (KeyError / traceback) was written to stderr.
    stderr_text = capsys.readouterr().err
    assert "KeyError" not in stderr_text
    assert "request_id" not in stderr_text
    assert "During handling" not in stderr_text
    assert "Traceback" not in stderr_text

    # Invalid LOG_LEVEL values must not crash setup_logging().  "HANDLERS"
    # is the sharpest case: it used to resolve to the logging module's
    # HANDLERS dict, which made Logger.setLevel() raise ValueError.
    for bad_level in ("not-a-level", "HANDLERS", "root", "", "10", "info\n"):
        monkeypatch.setenv("LOG_LEVEL", bad_level)
        setup_logging()  # must not raise
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    setup_logging()
