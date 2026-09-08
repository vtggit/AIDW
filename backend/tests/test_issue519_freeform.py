"""Proving test for Issue #519: redirect credential gate uses effective origin.

The ``Authorization`` header is re-attached on a redirect only when the redirect
target's effective origin (scheme, lower-cased host, effective port with default
ports normalized) equals the original request's effective origin.  A scheme
downgrade, a port change, a host change, or a malformed redirect port all drop
the header.  Servers are in-process ``http.server.HTTPServer`` doubles bound to
127.0.0.1 port 0 — no external address is ever contacted.
"""

import base64
import http.server
import io
import threading
import urllib.error
from unittest import mock
from unittest.mock import patch

from app.egress import http as egress_http


class _TestServer:
    """Minimal in-process HTTP server for egress redirect tests.

    ``redirect_count`` controls how many times the server issues a 302
    before returning the body.  0 (default) means "always redirect while
    ``redirect_to`` is set"; a positive value means "redirect for the
    first N requests, then return the body".
    """

    def __init__(
        self,
        redirect_to: str | None = None,
        body: bytes = b"OK",
        redirect_count: int = 0,
    ):
        self.headers_received: list[dict] = []
        self.redirect_to = redirect_to
        self.body = body
        self.redirect_count = redirect_count
        self._request_count = 0
        self.port: int = 0
        self._server: http.server.HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> "_TestServer":
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                outer.headers_received.append(dict(self.headers))
                outer._request_count += 1
                should_redirect = outer.redirect_to is not None and (
                    outer.redirect_count == 0
                    or outer._request_count <= outer.redirect_count
                )
                if should_redirect:
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


def _run_fetch(url: str) -> bytes:
    with (
        patch.object(egress_http, "credential_for_url", return_value=_credential()),
        patch.object(egress_http, "validate_destination"),
        patch.object(egress_http, "resolve_secret", return_value="s3cret"),
    ):
        return egress_http.fetch_bytes(url)


def test_issue519_freeform():
    """Effective-origin credential gate: same-origin keeps, any change drops."""
    expected_auth = _expected_auth()

    # --- 1: same-origin redirect (identical scheme, host, port) keeps header ---
    srv = _TestServer(body=b"same", redirect_count=1).start()
    srv.redirect_to = srv.url  # redirect to itself (same origin)
    try:
        result = _run_fetch(srv.url)
        assert result == b"same"
        # Both requests are same-origin → header attached on both
        assert srv.headers_received[0]["Authorization"] == expected_auth
        assert srv.headers_received[1]["Authorization"] == expected_auth
    finally:
        srv.stop()

    # --- 2: same-host DIFFERENT-PORT redirect drops the header ---
    srv_b = _TestServer(body=b"port").start()
    srv_a = _TestServer(redirect_to=srv_b.url).start()
    try:
        result = _run_fetch(srv_a.url)
        assert result == b"port"
        # First request (original) is same-origin → header present
        assert srv_a.headers_received[0]["Authorization"] == expected_auth
        # Second request (different port) → header omitted
        assert "Authorization" not in srv_b.headers_received[0]
    finally:
        srv_a.stop()
        srv_b.stop()

    # --- 3: cross-host redirect (different host, same scheme) drops header ---
    srv_b2 = _TestServer(body=b"host").start()
    cross_host_url = f"http://localhost:{srv_b2.port}/"
    srv_a2 = _TestServer(redirect_to=cross_host_url).start()
    try:
        result = _run_fetch(srv_a2.url)
        assert result == b"host"
        # First request (original, 127.0.0.1) is same-origin → header present
        assert srv_a2.headers_received[0]["Authorization"] == expected_auth
        # Second request (localhost) → different host → header omitted
        assert "Authorization" not in srv_b2.headers_received[0]
    finally:
        srv_a2.stop()
        srv_b2.stop()

    # --- 4: scheme downgrade (https → http) is an origin mismatch ---
    # Cannot make a live HTTPS connection to a plain HTTP server, so we
    # assert the gate logic directly: the effective origins differ.
    https_origin = egress_http._effective_origin("https://127.0.0.1:443/")
    http_origin = egress_http._effective_origin("http://127.0.0.1:8080/")
    assert https_origin == ("https", "127.0.0.1", 443)
    assert http_origin == ("http", "127.0.0.1", 8080)
    assert https_origin != http_origin  # gate would omit the header

    # --- 5: malformed redirect port → origin mismatch → header omitted ---
    # Use a mock opener to observe the second request's headers without
    # making a real connection to the malformed port.
    bad_port_url = "http://127.0.0.1:notaport/"
    captured_requests: list = []

    class _FakeResponse:
        def read(self) -> bytes:
            return b"ok"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def _fake_open(request, timeout=None):
        captured_requests.append(request)
        if len(captured_requests) == 1:
            # First call: simulate a 302 redirect to the malformed-port URL
            raise urllib.error.HTTPError(
                request.full_url,
                302,
                "Found",
                {"Location": bad_port_url},
                io.BytesIO(b""),
            )
        # Second call: return a successful response
        return _FakeResponse()

    with (
        patch.object(egress_http, "credential_for_url", return_value=_credential()),
        patch.object(egress_http, "validate_destination"),
        patch.object(egress_http, "resolve_secret", return_value="s3cret"),
        patch(
            "urllib.request.build_opener",
            return_value=mock.MagicMock(open=_fake_open),
        ),
    ):
        result = egress_http.fetch_bytes("http://127.0.0.1:9999/")

    assert result == b"ok"
    # First request (same origin as the original) carries the header
    assert captured_requests[0].get_header("Authorization") == expected_auth
    # Second request (malformed port → _effective_origin is None → mismatch)
    # must NOT carry the Authorization header
    assert captured_requests[1].get_header("Authorization") is None
    # Gate logic: the malformed port yields no effective origin
    assert egress_http._effective_origin(bad_port_url) is None
