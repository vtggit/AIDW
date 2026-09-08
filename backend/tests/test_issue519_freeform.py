"""Proving test for Issue #519: redirect credential gate uses effective origin.

The gate must re-attach the Basic ``Authorization`` header on a redirect only when the
redirect target's effective origin (scheme + effective port, with default ports
normalized) equals the original request's effective origin.  A scheme downgrade
(https -> http) or any port change is an origin mismatch and the header is omitted;
a malformed or unparseable redirect port is also treated as an origin mismatch (the
header is omitted, never a crash).

All real servers are in-process ``http.server.HTTPServer`` doubles bound to 127.0.0.1
on ephemeral ports (port 0).  The https and malformed-port cases use a fake opener so
no external address is ever contacted.
"""

import base64
import http.server
import threading
import urllib.error
from unittest.mock import patch

from app.egress import http as egress_http


class _TestServer:
    """Minimal in-process HTTP server for egress redirect tests."""

    def __init__(self, redirect_to: str | None = None, body: bytes = b"OK"):
        self.headers_received: list[dict] = []
        self.redirect_to = redirect_to
        self.body = body
        self.port: int = 0
        self._server: http.server.HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> "_TestServer":
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                outer.headers_received.append(dict(self.headers))
                if outer.redirect_to:
                    self.send_response(302)
                    self.send_header("Location", outer.redirect_to)
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(outer.body)))
                    self.end_headers()
                    self.wfile.write(outer.body)

            def log_message(self, *args):
                pass

        self._server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        if self._thread:
            self._thread.join(timeout=5)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"


class _FakeResponse:
    """A context-manager response whose read() returns a fixed body."""

    def __init__(self, body: bytes):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _redirect(location: str):
    """A fake-opener step that raises a 302 redirect to *location*."""

    def _step(request):
        raise urllib.error.HTTPError(
            url=request.full_url,
            code=302,
            msg="Found",
            hdrs={"Location": location},
            fp=None,
        )

    return _step


def _body(body: bytes):
    """A fake-opener step that returns a 200 response with *body*."""

    def _step(request):
        return _FakeResponse(body)

    return _step


def _fake_opener(script: list):
    """Build a fake opener whose open() follows *script* and records requests.

    Each entry in *script* is a callable invoked with the Request; it either
    raises (redirect/error) or returns a response-like object.  Every request's
    headers are recorded in ``opener.requests`` in order.
    """

    class _Opener:
        def __init__(self):
            self.requests: list[dict] = []
            self._i = 0

        def open(self, request, timeout=None):
            self.requests.append(dict(request.headers))
            step = script[self._i]
            self._i += 1
            return step(request)

    return _Opener()


def _credential() -> dict:
    return {
        "id": 1,
        "name": "test",
        "auth_scheme": "basic",
        "principal": "user",
        "secret_ref": "env://FAKE_SECRET",
        "token_endpoint": None,
        "source_id": 1,
        "created_at": None,
        "updated_at": None,
    }


def _expected_auth() -> str:
    return "Basic " + base64.b64encode(b"user:s3cret").decode()


def _run_fetch(url: str, opener=None) -> bytes:
    """Run fetch_bytes with the credential/secret/destination stubs applied."""
    patches = [
        patch.object(egress_http, "credential_for_url", return_value=_credential()),
        patch.object(egress_http, "validate_destination"),
        patch.object(egress_http, "resolve_secret", return_value="s3cret"),
    ]
    if opener is not None:
        patches.append(
            patch.object(
                egress_http.urllib.request, "build_opener", return_value=opener
            )
        )
    for p in patches:
        p.start()
    try:
        return egress_http.fetch_bytes(url)
    finally:
        for p in reversed(patches):
            p.stop()


def test_issue519_freeform():
    """The redirect credential gate keys on effective origin, not bare host."""
    expected_auth = _expected_auth()

    # --- 1: same-host, different-port redirect is an origin mismatch ---
    srv_b = _TestServer(body=b"hello").start()
    srv_a = _TestServer(redirect_to=srv_b.url).start()
    try:
        result = _run_fetch(srv_a.url)
        assert result == b"hello"
        # The original request (same effective origin) still carries the header.
        assert srv_a.headers_received[0]["Authorization"] == expected_auth
        # The redirect target is a different port, so the header is dropped.
        assert "Authorization" not in srv_b.headers_received[0]
    finally:
        srv_a.stop()
        srv_b.stop()

    # --- 2: cross-host redirect is an origin mismatch ---
    srv_b2 = _TestServer(body=b"world").start()
    cross_host_url = f"http://localhost:{srv_b2.port}/"
    srv_a2 = _TestServer(redirect_to=cross_host_url).start()
    try:
        result = _run_fetch(srv_a2.url)
        assert result == b"world"
        assert srv_a2.headers_received[0]["Authorization"] == expected_auth
        assert "Authorization" not in srv_b2.headers_received[0]
    finally:
        srv_a2.stop()
        srv_b2.stop()

    # --- 3: scheme downgrade (https -> http) is an origin mismatch ---
    opener = _fake_opener(
        [
            _redirect("http://127.0.0.1:8080/"),
            _body(b"downgraded"),
        ]
    )
    result = _run_fetch("https://127.0.0.1:443/", opener=opener)
    assert result == b"downgraded"
    # The original https request carried the header.
    assert opener.requests[0]["Authorization"] == expected_auth
    # The http redirect target did not (scheme changed).
    assert "Authorization" not in opener.requests[1]

    # --- 4: malformed / unparseable redirect port is an origin mismatch ---
    # The redirect Location carries a non-numeric port.  The gate must treat it
    # as an origin mismatch and omit the header without raising.
    opener = _fake_opener(
        [
            _redirect("http://127.0.0.1:notaport/"),
            _body(b"malformed"),
        ]
    )
    result = _run_fetch("https://127.0.0.1:443/", opener=opener)
    assert result == b"malformed"
    # The original https request carried the header.
    assert opener.requests[0]["Authorization"] == expected_auth
    # The malformed-port target did not (treated as an origin mismatch).
    assert "Authorization" not in opener.requests[1]
