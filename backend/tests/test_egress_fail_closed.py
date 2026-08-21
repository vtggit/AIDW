"""Issue #505 — egress fail-closed behavior.

Proves that the egress subsystem refuses to send an outbound request when a
precondition fails, and that no request (authenticated or unauthenticated)
reaches the network in those cases.  Each test drives the real
``app.egress.http.fetch_bytes`` path against an in-process HTTP double on
127.0.0.1 (or a closed port) and asserts the double recorded zero requests.

The tests exercise the existing modules (``app.egress.http``,
``app.egress.secrets``, ``app.egress.policy``) without modifying them.
"""

import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.db.connection import get_cursor
from app.egress import EgressError as EgressBaseError
from app.egress.http import (
    EgressAuthError,
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


@pytest.fixture
def http_double():
    """Start an in-process HTTP server on 127.0.0.1 and yield (url, recorder)."""
    recorder = _RequestRecorder()
    handler = _make_handler(recorder)
    server = HTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}/", recorder
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def closed_port():
    """Yield a 127.0.0.1 port that is guaranteed to be closed (connection refused)."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


def _seed_source_and_credential(monkeypatch, endpoint: str, secret_ref: str) -> None:
    """Insert a source, a source_connection, and a basic-auth source_credential.

    The credential's ``secret_ref`` names an environment variable that the
    caller controls (set or unset) to drive the fail-closed path.  Every
    NOT NULL column (including ``source_connections.name``) is supplied.
    """
    source_id = "src-505"
    conn_id = "conn-505"
    cred_id = "cred-505"
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO sources (id, name, created_at, updated_at) "
            "VALUES (%s, %s, NOW(), NOW()) "
            "ON CONFLICT (id) DO NOTHING",
            (source_id, "issue505 source"),
        )
        cur.execute(
            "INSERT INTO source_connections "
            "(id, source_id, name, endpoint, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, NOW(), NOW()) "
            "ON CONFLICT (id) DO NOTHING",
            (conn_id, source_id, "issue505 connection", endpoint),
        )
        cur.execute(
            "INSERT INTO source_credentials "
            "(id, source_id, name, auth_scheme, principal, secret_ref, created_at, updated_at) "
            "VALUES (%s, %s, %s, 'basic', 'issue505-principal', %s, NOW(), NOW()) "
            "ON CONFLICT (id) DO NOTHING",
            (cred_id, source_id, "issue505 credential", secret_ref),
        )


def test_missing_credential_fail_closed(http_double, monkeypatch):
    """With the secret env var unset (default policy), fetch_bytes raises an
    EgressError-family exception, the double records zero requests, and no
    unauthenticated fallback request is sent."""
    url, recorder = http_double
    monkeypatch.delenv(_SECRET_REF, raising=False)
    monkeypatch.delenv("EGRESS_POLICY", raising=False)
    monkeypatch.delenv("EGRESS_ALLOWED_HOSTS", raising=False)
    _seed_source_and_credential(monkeypatch, url, _SECRET_REF)

    with pytest.raises(EgressBaseError) as excinfo:
        fetch_bytes(url)

    # The raised error is the missing-secret variant (an EgressError-family type).
    assert isinstance(excinfo.value, SecretUnavailableAuthError)
    # No request of any kind reached the double — no authenticated, no fallback.
    assert recorder.requests == 0
    # The secret value (absent here) must not appear in the message.
    assert _SENTINEL_SECRET not in str(excinfo.value)


def test_denied_destination_fail_closed(http_double, monkeypatch):
    """fetch_bytes against the link-local metadata endpoint (default policy)
    raises EgressDestinationDenied before any connection is opened, and the
    in-process double on 127.0.0.1 records zero requests."""
    _url, recorder = http_double
    monkeypatch.delenv("EGRESS_POLICY", raising=False)
    monkeypatch.delenv("EGRESS_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv(_SECRET_REF, raising=False)

    metadata_url = "http://169.254.169.254/latest/meta-data/"
    with pytest.raises(EgressDestinationDenied):
        fetch_bytes(metadata_url)

    # The denied destination is never connected to; the double saw nothing.
    assert recorder.requests == 0


def test_strict_mode_loopback_denial(http_double, monkeypatch):
    """With EGRESS_POLICY=strict, fetch_bytes against the 127.0.0.1 double
    raises EgressDestinationDenied and the double records zero requests."""
    url, recorder = http_double
    monkeypatch.setenv("EGRESS_POLICY", "strict")
    monkeypatch.delenv("EGRESS_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv(_SECRET_REF, raising=False)

    with pytest.raises(EgressDestinationDenied):
        fetch_bytes(url)

    assert recorder.requests == 0


def test_network_error_fail_closed_no_secret_leak(closed_port, monkeypatch):
    """fetch_bytes against a closed 127.0.0.1 port (default policy) raises a
    typed EgressError-family exception whose message contains no secret
    material (the sentinel set via the credential's secret_ref)."""
    monkeypatch.delenv("EGRESS_POLICY", raising=False)
    monkeypatch.delenv("EGRESS_ALLOWED_HOSTS", raising=False)
    # Set the sentinel secret so a credential resolves; the fetch then fails at
    # the network layer (connection refused), not at secret resolution.
    monkeypatch.setenv(_SECRET_REF, _SENTINEL_SECRET)

    endpoint = f"http://127.0.0.1:{closed_port}"
    _seed_source_and_credential(monkeypatch, endpoint, _SECRET_REF)

    with pytest.raises(EgressError) as excinfo:
        fetch_bytes(endpoint)

    # Typed EgressError-family (the base egress HTTP error).
    assert isinstance(excinfo.value, EgressError)
    # The sentinel secret value must be absent from the exception message.
    assert _SENTINEL_SECRET not in str(excinfo.value)
    # The principal is also never leaked.
    assert "issue505-principal" not in str(excinfo.value)
