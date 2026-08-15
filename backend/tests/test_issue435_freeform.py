"""Proof for issue #435 — POST /api/connection-tests/{id}/run.

Verifies:
  * The literal ``/run`` segment is routed to the run endpoint (not captured as
    an ``entity_id``) and requires the admin role.
  * The run endpoint delegates the fetch to ``app.egress.http.fetch_bytes``
    (reused, not re-implemented) against the source metadata URL.
  * On a 2xx fetch the record is updated to ``ok`` with a non-null ``latency_ms``
    and a ``tested_at`` timestamp.
  * On an auth failure the record is ``auth_failed`` with a secret-free message.
"""

import base64
import http.server
import threading

import app.egress.http as egress_http


def _start_auth_server(monkeypatch):
    """Start an in-process HTTP server on 127.0.0.1 that requires Authorization.

    Returns the base endpoint URL (no trailing slash).
    """
    expected = base64.b64encode(b"svc:topsecret").decode("ascii")

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            auth = self.headers.get("Authorization")
            if auth == f"Basic {expected}":
                body = b"<edmx:Edmx/>"
                self.send_response(200)
                self.send_header("Content-Type", "application/xml")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(401)
                self.send_header("WWW-Authenticate", 'Basic realm="erp"')
                self.send_header("Content-Length", "0")
                self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(server, "shutdown", lambda: None)
    return f"http://127.0.0.1:{port}"


def _create_source(client, admin_headers):
    resp = client.post(
        "/api/sources", json={"name": "issue435-source"}, headers=admin_headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_connection(client, admin_headers, source_id, endpoint):
    resp = client.post(
        "/api/source-connections",
        json={"name": "issue435-conn", "source_id": source_id, "endpoint": endpoint},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_config(client, admin_headers, source_id, metadata_path):
    resp = client.post(
        "/api/odata-service-configs",
        json={
            "name": "issue435-cfg",
            "source_id": source_id,
            "metadata_path": metadata_path,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_credential(client, admin_headers, source_id, secret_ref):
    resp = client.post(
        "/api/source-credentials",
        json={
            "name": "issue435-cred",
            "source_id": source_id,
            "auth_scheme": "basic",
            "principal": "svc",
            "secret_ref": secret_ref,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_test(client, admin_headers, source_id):
    resp = client.post(
        "/api/connection-tests",
        json={"name": "issue435-test", "source_id": source_id},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_issue435_freeform(client, admin_headers, user_headers, monkeypatch):
    endpoint = _start_auth_server(monkeypatch)
    source_id = _create_source(client, admin_headers)
    _create_connection(client, admin_headers, source_id, endpoint)
    _create_config(client, admin_headers, source_id, "$metadata")

    # --- Case 1: credential present -> fetch succeeds -> status 'ok' --------
    monkeypatch.setenv("ISSUE435_SECRET", "topsecret")
    _create_credential(client, admin_headers, source_id, "ISSUE435_SECRET")
    test_id = _create_test(client, admin_headers, source_id)

    # Pin the reuse: capture the ORIGINAL fetch_bytes BEFORE patching, then
    # delegate to that captured original from inside the recorder.  Calling
    # egress_http.fetch_bytes from within the recorder after the patch would
    # recurse into the recorder itself.
    original_fetch = egress_http.fetch_bytes
    calls = []

    def recorder(url, timeout=30):
        calls.append(url)
        return original_fetch(url, timeout=timeout)

    monkeypatch.setattr(egress_http, "fetch_bytes", recorder)

    resp = client.post(f"/api/connection-tests/{test_id}/run", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok", body
    assert body["latency_ms"] is not None
    assert isinstance(body["latency_ms"], int)
    assert body["tested_at"] is not None
    assert body["tested_at"].endswith("+00:00") or body["tested_at"].endswith("Z")

    # The recorder must have been invoked with the metadata URL.
    assert (
        calls
    ), "egress fetch_bytes was not invoked — run endpoint did not reuse egress"
    assert calls[0] == f"{endpoint}/$metadata", calls

    # --- Case 2: env var unset -> auth failure -> status 'auth_failed' ------
    monkeypatch.delenv("ISSUE435_SECRET", raising=False)
    resp2 = client.post(f"/api/connection-tests/{test_id}/run", headers=admin_headers)
    assert resp2.status_code == 200, resp2.text
    body2 = resp2.json()
    assert body2["status"] == "auth_failed", body2
    assert body2["message"] is not None
    assert "topsecret" not in body2["message"]
    assert "svc" not in body2["message"]

    # --- The literal 'run' segment is never captured as an entity_id --------
    resp3 = client.get("/api/connection-tests/run", headers=admin_headers)
    assert resp3.status_code == 404, resp3.text

    # --- The run endpoint requires the admin role ---------------------------
    resp4 = client.post(f"/api/connection-tests/{test_id}/run", headers=user_headers)
    assert resp4.status_code in (401, 403), resp4.text
