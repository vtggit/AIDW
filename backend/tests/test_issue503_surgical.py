"""Proving test for Issue #503: redirect handling + auth-header host scoping."""

import base64
import http.server
import threading
from unittest.mock import patch

import pytest

from app.egress import http as egress_http
from app.egress.policy import EgressDestinationDenied


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


def test_issue503_surgical():
    """Verify redirect handling and auth-header host scoping in fetch_bytes."""
    credential = {
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
    expected_auth = "Basic " + base64.b64encode(b"user:s3cret").decode()

    # --- 1: same-host redirect keeps Authorization header ---
    srv_b = _TestServer(body=b"hello").start()
    srv_a = _TestServer(redirect_to=srv_b.url).start()
    try:
        with (
            patch.object(egress_http, "credential_for_url", return_value=credential),
            patch.object(egress_http, "validate_destination"),
            patch.object(egress_http, "resolve_secret", return_value="s3cret"),
        ):
            result = egress_http.fetch_bytes(srv_a.url)
        assert result == b"hello"
        assert srv_a.headers_received[0]["Authorization"] == expected_auth
        assert srv_b.headers_received[0]["Authorization"] == expected_auth
    finally:
        srv_a.stop()
        srv_b.stop()

    # --- 2: cross-host redirect drops Authorization header ---
    srv_b2 = _TestServer(body=b"world").start()
    cross_host_url = f"http://localhost:{srv_b2.port}/"
    srv_a2 = _TestServer(redirect_to=cross_host_url).start()
    try:
        with (
            patch.object(egress_http, "credential_for_url", return_value=credential),
            patch.object(egress_http, "validate_destination"),
            patch.object(egress_http, "resolve_secret", return_value="s3cret"),
        ):
            result = egress_http.fetch_bytes(srv_a2.url)
        assert result == b"world"
        assert srv_a2.headers_received[0]["Authorization"] == expected_auth
        assert "Authorization" not in srv_b2.headers_received[0]
    finally:
        srv_a2.stop()
        srv_b2.stop()

    # --- 3: denied redirect destination raises EgressDestinationDenied ---
    srv_b3 = _TestServer(body=b"denied").start()
    srv_a3 = _TestServer(redirect_to=srv_b3.url).start()

    def _deny_on_redirect(url: str):
        if url != srv_a3.url:
            raise EgressDestinationDenied(f"denied: {url}")

    try:
        with (
            patch.object(egress_http, "credential_for_url", return_value=None),
            patch.object(
                egress_http,
                "validate_destination",
                side_effect=_deny_on_redirect,
            ),
            pytest.raises(EgressDestinationDenied),
        ):
            egress_http.fetch_bytes(srv_a3.url)
        # The denied destination must NOT have received a request.
        assert len(srv_b3.headers_received) == 0
    finally:
        srv_a3.stop()
        srv_b3.stop()

    # --- 4: exactly 3 redirects succeed ---
    srv_d = _TestServer(body=b"three").start()
    srv_c = _TestServer(redirect_to=srv_d.url).start()
    srv_b4 = _TestServer(redirect_to=srv_c.url).start()
    srv_a4 = _TestServer(redirect_to=srv_b4.url).start()
    try:
        with (
            patch.object(egress_http, "credential_for_url", return_value=None),
            patch.object(egress_http, "validate_destination"),
        ):
            result = egress_http.fetch_bytes(srv_a4.url)
        assert result == b"three"
    finally:
        srv_a4.stop()
        srv_b4.stop()
        srv_c.stop()
        srv_d.stop()

    # --- 5: 4th redirect raises EgressError ---
    srv_e = _TestServer(body=b"final").start()
    srv_d2 = _TestServer(redirect_to=srv_e.url).start()
    srv_c2 = _TestServer(redirect_to=srv_d2.url).start()
    srv_b5 = _TestServer(redirect_to=srv_c2.url).start()
    srv_a5 = _TestServer(redirect_to=srv_b5.url).start()
    try:
        with (
            patch.object(egress_http, "credential_for_url", return_value=None),
            patch.object(egress_http, "validate_destination"),
            pytest.raises(egress_http.EgressError),
        ):
            egress_http.fetch_bytes(srv_a5.url)
    finally:
        srv_a5.stop()
        srv_b5.stop()
        srv_c2.stop()
        srv_d2.stop()
        srv_e.stop()
