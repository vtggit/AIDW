"""Proof for issue #435 — POST /api/connection-tests/{id}/run.

Spins up an in-process HTTP double on 127.0.0.1 that requires an
Authorization header, then exercises the run endpoint against a real
source_connections / odata_service_configs / source_credentials row set.
"""

import base64
import http.server
import threading

import pytest

SECRET_VALUE = "s3cr3t-egress-token"
SECRET_ENV_VAR = "AIDW_ISSUE435_SECRET"
EXPECTED_AUTH = "Basic " + base64.b64encode(
    b"svc-user:" + SECRET_VALUE.encode("utf-8")
).decode("ascii")


class _AuthHandler(http.server.BaseHTTPRequestHandler):
    """In-process double: 200 with a valid Authorization header, 401 otherwise."""

    def do_GET(self):
        auth = self.headers.get("Authorization")
        if auth == EXPECTED_AUTH:
            body = b"<edmx:Edmx/>"
            self.send_response(200)
            self.send_header("Content-Type", "application/xml")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(401)
            self.send_header("Content-Length", "0")
            self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def auth_server():
    server = http.server.HTTPServer(("127.0.0.1", 0), _AuthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def _create_source(client, admin_headers, name):
    resp = client.post("/api/sources", json={"name": name}, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_connection_test(client, admin_headers, source_id, name):
    resp = client.post(
        "/api/connection-tests",
        json={"name": name, "source_id": source_id},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_source_connection(client, admin_headers, source_id, endpoint):
    resp = client.post(
        "/api/source-connections",
        json={"name": "conn", "source_id": source_id, "endpoint": endpoint},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_odata_config(client, admin_headers, source_id):
    resp = client.post(
        "/api/odata-service-configs",
        json={"name": "odata", "source_id": source_id, "metadata_path": "$metadata"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_credential(client, admin_headers, source_id, secret_ref):
    resp = client.post(
        "/api/source-credentials",
        json={
            "name": "cred",
            "source_id": source_id,
            "auth_scheme": "basic",
            "principal": "svc-user",
            "secret_ref": secret_ref,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_issue435_freeform(client, admin_headers, auth_server, monkeypatch):
    # --- happy path: secret present, source requires auth, run succeeds ---
    monkeypatch.setenv(SECRET_ENV_VAR, SECRET_VALUE)

    source_id = _create_source(client, admin_headers, "src-ok")
    test_id = _create_connection_test(client, admin_headers, source_id, "test-ok")
    _create_source_connection(client, admin_headers, source_id, auth_server)
    _create_odata_config(client, admin_headers, source_id)
    _create_credential(client, admin_headers, source_id, SECRET_ENV_VAR)

    resp = client.post(f"/api/connection-tests/{test_id}/run", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert body["latency_ms"] is not None
    assert isinstance(body["latency_ms"], int)
    assert body["tested_at"] is not None
    assert "T" in body["tested_at"]

    # --- failure path: secret env var unset -> auth_failed, no secret leak ---
    monkeypatch.delenv(SECRET_ENV_VAR, raising=False)

    source_id2 = _create_source(client, admin_headers, "src-fail")
    test_id2 = _create_connection_test(client, admin_headers, source_id2, "test-fail")
    _create_source_connection(client, admin_headers, source_id2, auth_server)
    _create_odata_config(client, admin_headers, source_id2)
    _create_credential(client, admin_headers, source_id2, SECRET_ENV_VAR)

    resp2 = client.post(f"/api/connection-tests/{test_id2}/run", headers=admin_headers)
    assert resp2.status_code == 200, resp2.text
    body2 = resp2.json()
    assert body2["status"] == "auth_failed"
    assert body2["message"] is not None
    assert SECRET_VALUE not in body2["message"]
    assert SECRET_VALUE not in resp2.text
