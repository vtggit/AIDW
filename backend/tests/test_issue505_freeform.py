"""Issue #505 — freeform proof that the egress subsystem fails closed.

This is the gate's proving test.  It drives the real
``app.egress.http.fetch_bytes`` path (reusing ``app.egress.secrets`` and
``app.egress.policy``) against an in-process HTTP double on 127.0.0.1 and a
closed 127.0.0.1 port, and asserts the four fail-closed guarantees:

1. Missing credential (secret env var unset, default policy) -> an
   EgressError-family exception, zero requests recorded, no unauthenticated
   fallback.
2. Denied destination (link-local metadata endpoint, default policy) ->
   EgressDestinationDenied before any connection, zero requests.
3. Strict-mode loopback denial (EGRESS_POLICY=strict) -> EgressDestinationDenied,
   zero requests.
4. Network error (closed port, default policy) -> a typed EgressError-family
   exception whose message contains no secret material.

The test exercises the existing modules without modifying them.
"""

import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.db.connection import get_cursor
from app.egress import EgressError as EgressBaseError
from app.egress.http import (
    EgressError,
    SecretUnavailableAuthError,
    fetch_bytes,
)
from app.egress.policy import EgressDestinationDenied

# A sentinel secret value that must never appear in any exception message.
_SENTINEL_SECRET = "SENTINEL-SECRET-VALUE-DO-NOT-LEAK-505"
# The environment variable name the credential's secret_ref points at.
_SECRET_REF = "AIDW_TEST_EGRESS_SECRET"


class _RequestRecorder:
    """Counts every request the in-process double receives."""

    def __init__(self) -> None:
        self.count = 0
        self._lock = threading.Lock()

    def record(self) -> None:
        with self._lock:
            self.count += 1

    @property
    def requests(self) -> int:
        with self._lock:
            return self.count


def _make_handler(recorder: _RequestRecorder):
    """Build a BaseHTTPRequestHandler subclass that records and answers 200."""

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - http.server API
            recorder.record()
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # silence default stderr logging
            return

    return _Handler


def _seed_source_and_credential(endpoint: str, secret_ref: str) -> None:
    """Insert a source, a source_connection, and a basic-auth source_credential.

    The credential's ``secret_ref`` names an environment variable that the
    caller controls (set or unset) to drive the fail-closed path.  Every
    NOT NULL column (including ``source_connections.name``) is supplied.
    """
    source_id = "src-505-freeform"
    conn_id = "conn-505-freeform"
    cred_id = "cred-505-freeform"
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO sources (id, name, created_at, updated_at) "
            "VALUES (%s, %s, NOW(), NOW()) "
            "ON CONFLICT (id) DO NOTHING",
            (source_id, "issue505 freeform source"),
        )
        cur.execute(
            "INSERT INTO source_connections "
            "(id, source_id, name, endpoint, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, NOW(), NOW()) "
            "ON CONFLICT (id) DO NOTHING",
            (conn_id, source_id, "issue505 freeform connection", endpoint),
        )
        cur.execute(
            "INSERT INTO source_credentials "
            "(id, source_id, name, auth_scheme, principal, secret_ref, created_at, updated_at) "
            "VALUES (%s, %s, %s, 'basic', 'issue505-freeform-principal', %s, NOW(), NOW()) "
            "ON CONFLICT (id) DO NOTHING",
            (cred_id, source_id, "issue505 freeform credential", secret_ref),
        )


def test_issue505_freeform(client, admin_headers, monkeypatch):
    """Prove the four egress fail-closed guarantees end to end.

    ``client``/``admin_headers`` are the harness fixtures (the app is up and the
    test database is available); the egress path is driven directly through
    ``fetch_bytes`` so the in-process double and the closed port are the only
    network surfaces.
    """
    # ------------------------------------------------------------------
    # 1. Missing-credential fail-closed (default policy).
    # ------------------------------------------------------------------
    recorder = _RequestRecorder()
    handler = _make_handler(recorder)
    server = HTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        double_url = f"http://127.0.0.1:{port}/"

        # --- (1) missing credential: secret env var unset, default policy ---
        monkeypatch.delenv(_SECRET_REF, raising=False)
        monkeypatch.delenv("EGRESS_POLICY", raising=False)
        monkeypatch.delenv("EGRESS_ALLOWED_HOSTS", raising=False)
        _seed_source_and_credential(double_url, _SECRET_REF)

        with pytest.raises(EgressBaseError) as missing_exc:
            fetch_bytes(double_url)

        assert isinstance(missing_exc.value, SecretUnavailableAuthError)
        assert recorder.requests == 0
        assert _SENTINEL_SECRET not in str(missing_exc.value)

        # --- (2) denied destination: link-local metadata, default policy ---
        monkeypatch.delenv("EGRESS_POLICY", raising=False)
        monkeypatch.delenv("EGRESS_ALLOWED_HOSTS", raising=False)
        monkeypatch.delenv(_SECRET_REF, raising=False)

        metadata_url = "http://169.254.169.254/latest/meta-data/"
        with pytest.raises(EgressDestinationDenied):
            fetch_bytes(metadata_url)

        assert recorder.requests == 0

        # --- (3) strict-mode loopback denial through the full path ---
        monkeypatch.setenv("EGRESS_POLICY", "strict")
        monkeypatch.delenv("EGRESS_ALLOWED_HOSTS", raising=False)
        monkeypatch.delenv(_SECRET_REF, raising=False)

        with pytest.raises(EgressDestinationDenied):
            fetch_bytes(double_url)

        assert recorder.requests == 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    # ------------------------------------------------------------------
    # 4. Network-error fail-closed (closed port, default policy) — no leak.
    # ------------------------------------------------------------------
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    closed_port = probe.getsockname()[1]
    probe.close()

    monkeypatch.delenv("EGRESS_POLICY", raising=False)
    monkeypatch.delenv("EGRESS_ALLOWED_HOSTS", raising=False)
    # Set the sentinel secret so the credential resolves; the fetch then fails
    # at the network layer (connection refused), not at secret resolution.
    monkeypatch.setenv(_SECRET_REF, _SENTINEL_SECRET)

    endpoint = f"http://127.0.0.1:{closed_port}"
    _seed_source_and_credential(endpoint, _SECRET_REF)

    with pytest.raises(EgressError) as net_exc:
        fetch_bytes(endpoint)

    assert isinstance(net_exc.value, EgressError)
    assert _SENTINEL_SECRET not in str(net_exc.value)
    assert "issue505-freeform-principal" not in str(net_exc.value)
