"""Issue #673 — freeform proof: explicit 1m API body ceiling + opt-in statement timeout.

Proves, in a single node:

* AC-1: ``app/nginx.conf`` carries exactly one ``client_max_body_size 1m;``
  directive, and it sits at the server level (not inside any location block).
* AC-2/AC-3: ``get_connection_params()`` reads ``DB_STATEMENT_TIMEOUT_MS``
  from the environment at call time.  With ``60000`` the parameters include
  ``options="-c statement_timeout=60000"`` and a real connection to the test
  database reports ``SHOW statement_timeout`` as ``1min``; with the variable
  unset, empty, ``0``, ``-5`` or ``abc`` no ``options`` key is added at all,
  so connections behave exactly as they do today.
"""

import os
import re

import psycopg2
import pytest

from app.db.connection import get_connection_params

_NGINX_CONF = os.path.normpath(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "app", "nginx.conf"
    )
)


def _strip_nginx_comments(text: str) -> str:
    """Drop ``#`` comments from nginx config text."""
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def _server_level_directives(nginx_code: str) -> list[str]:
    """Return the directives that sit directly inside the server block.

    Block headers and everything nested inside a ``{...}`` block are ignored,
    so a directive found inside a location block is not reported.
    """
    match = re.search(r"\bserver\s*\{", nginx_code)
    assert match is not None, "app/nginx.conf has no server block"
    directives: list[str] = []
    pending: list[str] = []
    depth = 1
    for char in nginx_code[match.end() :]:
        if char == "{":
            depth += 1
            pending = []
        elif char == "}":
            depth -= 1
            pending = []
            if depth == 0:
                break
        elif char == ";":
            pending.append(char)
            if depth == 1:
                directive = "".join(pending).strip()
                if directive:
                    directives.append(directive)
            pending = []
        elif depth == 1:
            pending.append(char)
    return directives


@pytest.mark.usefixtures("test_database", "test_env_setup")
def test_issue673_freeform(monkeypatch):
    # --- AC-1: exactly one server-level ``client_max_body_size 1m;`` -------
    with open(_NGINX_CONF, encoding="utf-8") as fh:
        nginx_text = fh.read()
    directives = _server_level_directives(_strip_nginx_comments(nginx_text))
    ceilings = [
        directive
        for directive in directives
        if re.fullmatch(r"client_max_body_size\s+1m;", directive)
    ]
    assert len(ceilings) == 1, (
        "expected exactly one server-level 'client_max_body_size 1m;', got: "
        f"{directives}"
    )

    # --- AC-2/AC-3: 60000 -> options on the params and on a real connection
    monkeypatch.setenv("DB_STATEMENT_TIMEOUT_MS", "60000")
    params = get_connection_params()
    assert params["options"] == "-c statement_timeout=60000"

    connection = psycopg2.connect(**params)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SHOW statement_timeout;")
            reported = cursor.fetchone()[0]
    finally:
        connection.close()
    assert reported == "1min"

    # --- AC-3: unset, empty, zero, negative and non-integer add no options
    for raw in (None, "", "0", "-5", "abc"):
        if raw is None:
            monkeypatch.delenv("DB_STATEMENT_TIMEOUT_MS", raising=False)
        else:
            monkeypatch.setenv("DB_STATEMENT_TIMEOUT_MS", raw)
        assert "options" not in get_connection_params()
