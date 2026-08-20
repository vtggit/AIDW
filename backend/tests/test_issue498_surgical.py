"""Proving test for issue #498: surgical egress credential resolution."""

import base64
import http.server
import inspect
import threading

import pytest

import app.egress.http as egress_http
import app.egress.secrets as egress_secrets
from app.egress import SecretRefInvalid, SecretUnavailable


class _RequestRecorder:
    """Records requests hitting the in-process HTTP server."""

    def __init__(self):
        self.requests: list[dict] = []
        self._lock = threading.Lock()

    def record(self, method, path, headers):
        with self._lock:
            self.requests.append(
                {"method": method, "path": path, "headers": dict(headers)}
            )


class _Handler(http.server.BaseHTTPRequestHandler):
    recorder: _RequestRecorder

    def do_GET(self):
        self.recorder.record("GET", self.path, self.headers)
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


@pytest.fixture()
def http_server():
    recorder = _RequestRecorder()
    handler = type("BoundHandler", (_Handler,), {"recorder": recorder})
    server = http.server.HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield recorder, f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    thread.join(timeout=5)


def _make_credential_row(**overrides):
    """Build a credential dict mimicking a DB row."""
    row = {
        "id": 1,
        "name": "test-cred",
        "auth_scheme": "basic",
        "principal": "admin",
        "secret_ref": "TEST_SECRET_VAR",
        "token_endpoint": None,
        "source_id": 1,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    }
    row.update(overrides)
    return row


def test_issue498_surgical(monkeypatch, http_server):
    recorder, base_url = http_server
    url = f"{base_url}/api/data"

    # --- AC: no local resolve_secret in http.py source ---
    src = inspect.getsource(egress_http)
    assert (
        "def resolve_secret" not in src
    ), "http.py must not define its own resolve_secret"
    assert (
        "os.environ.get" not in src
    ), "http.py must not use os.environ.get for secret fallback"

    # --- AC: bridge exception classes exist with correct MRO ---
    assert issubclass(
        egress_http.SecretUnavailableAuthError, egress_http.EgressAuthError
    )
    assert issubclass(egress_http.SecretUnavailableAuthError, SecretUnavailable)
    assert issubclass(
        egress_http.SecretRefInvalidAuthError, egress_http.EgressAuthError
    )
    assert issubclass(egress_http.SecretRefInvalidAuthError, SecretRefInvalid)

    # --- AC: resolution uses app.egress.secrets.resolve_secret ---
    assert egress_http.resolve_secret is egress_secrets.resolve_secret

    # --- Helper to patch credential_for_url ---
    def _patch_credential(row):
        monkeypatch.setattr(egress_http, "credential_for_url", lambda u: row)

    # --- Case 1: unset env var → SecretUnavailableAuthError ---
    monkeypatch.delenv("TEST_SECRET_VAR", raising=False)
    _patch_credential(_make_credential_row(secret_ref="TEST_SECRET_VAR"))
    with pytest.raises(egress_http.SecretUnavailableAuthError) as exc_info:
        egress_http.fetch_bytes(url)
    assert isinstance(exc_info.value, egress_http.EgressAuthError)
    assert isinstance(exc_info.value, SecretUnavailable)
    assert len(recorder.requests) == 0
    assert "s3cret" not in str(exc_info.value)

    # --- Case 2: empty env var → SecretUnavailableAuthError ---
    monkeypatch.setenv("TEST_SECRET_VAR", "")
    _patch_credential(_make_credential_row(secret_ref="TEST_SECRET_VAR"))
    with pytest.raises(egress_http.SecretUnavailableAuthError) as exc_info:
        egress_http.fetch_bytes(url)
    assert isinstance(exc_info.value, egress_http.EgressAuthError)
    assert isinstance(exc_info.value, SecretUnavailable)
    assert len(recorder.requests) == 0

    # --- Case 3: malformed ref (empty string) → SecretRefInvalidAuthError ---
    _patch_credential(_make_credential_row(secret_ref=""))
    with pytest.raises(egress_http.SecretRefInvalidAuthError) as exc_info:
        egress_http.fetch_bytes(url)
    assert isinstance(exc_info.value, egress_http.EgressAuthError)
    assert isinstance(exc_info.value, SecretRefInvalid)
    assert len(recorder.requests) == 0

    # --- Case 4: malformed ref (None → "") → SecretRefInvalidAuthError ---
    _patch_credential(_make_credential_row(secret_ref=None))
    with pytest.raises(egress_http.SecretRefInvalidAuthError) as exc_info:
        egress_http.fetch_bytes(url)
    assert isinstance(exc_info.value, egress_http.EgressAuthError)
    assert isinstance(exc_info.value, SecretRefInvalid)
    assert len(recorder.requests) == 0

    # --- Case 5: malformed ref (lowercase) → SecretRefInvalidAuthError ---
    _patch_credential(_make_credential_row(secret_ref="bad_ref"))
    with pytest.raises(egress_http.SecretRefInvalidAuthError) as exc_info:
        egress_http.fetch_bytes(url)
    assert isinstance(exc_info.value, egress_http.EgressAuthError)
    assert isinstance(exc_info.value, SecretRefInvalid)
    assert len(recorder.requests) == 0

    # --- Case 6: empty principal → EgressAuthError ---
    monkeypatch.setenv("TEST_SECRET_VAR", "s3cret")
    _patch_credential(_make_credential_row(principal=""))
    with pytest.raises(egress_http.EgressAuthError) as exc_info:
        egress_http.fetch_bytes(url)
    assert len(recorder.requests) == 0
    assert "s3cret" not in str(exc_info.value)

    # --- Case 7: whitespace principal → EgressAuthError ---
    _patch_credential(_make_credential_row(principal="   "))
    with pytest.raises(egress_http.EgressAuthError) as exc_info:
        egress_http.fetch_bytes(url)
    assert len(recorder.requests) == 0
    assert "s3cret" not in str(exc_info.value)

    # --- Positive control: well-formed credential → one request, Basic auth ---
    monkeypatch.setenv("TEST_SECRET_VAR", "s3cret")
    _patch_credential(
        _make_credential_row(principal="admin", secret_ref="TEST_SECRET_VAR")
    )
    result = egress_http.fetch_bytes(url)
    assert result == b"ok"
    assert len(recorder.requests) == 1
    expected_token = base64.b64encode(b"admin:s3cret").decode("ascii")
    auth_header = recorder.requests[0]["headers"].get("Authorization")
    assert auth_header == f"Basic {expected_token}"
