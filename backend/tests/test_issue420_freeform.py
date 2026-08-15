"""Proof for issue #420 — egress credential resolution + basic-auth fetch.

An in-process HTTP server on 127.0.0.1 answers 401 (with a
``WWW-Authenticate: Basic charset="UTF-8"`` header) when the
``Authorization`` header is absent or wrong, and 200 with a body when the
header is correct.  The test inserts a ``source_connections`` row and a
``source_credentials`` row (auth_scheme basic, secret_ref pointing at a set
env var), calls ``fetch_bytes`` against the double URL, and asserts the body
is returned.  A second call with the env var unset asserts
``EgressAuthError`` is raised and its message does not contain the secret.
"""

import base64
import http.server
import threading

from app.egress.http import EgressAuthError, fetch_bytes

EXPECTED_BODY = b"issue420-egress-ok"
SECRET_VALUE = "s3cr3t-egress-value"
SECRET_ENV_VAR = "AIDW_ISSUE420_SECRET"
PRINCIPAL = "egress-principal"


class _AuthHandler(http.server.BaseHTTPRequestHandler):
    """Answers 200 with a body when the Basic auth header is correct, else 401."""

    def do_GET(self):
        expected = base64.b64encode(f"{PRINCIPAL}:{SECRET_VALUE}".encode()).decode(
            "ascii"
        )
        auth = self.headers.get("Authorization")
        if auth == f"Basic {expected}":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(EXPECTED_BODY)))
            self.end_headers()
            self.wfile.write(EXPECTED_BODY)
        else:
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic charset="UTF-8"')
            self.send_header("Content-Length", "0")
            self.end_headers()

    def log_message(self, *args):
        # Silence default request logging during the test.
        pass


def _start_server():
    server = http.server.HTTPServer(("127.0.0.1", 0), _AuthHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def test_issue420_freeform(client, admin_headers, monkeypatch):
    server, port = _start_server()
    try:
        base_url = f"http://127.0.0.1:{port}"
        # The "double URL" — a path under the connection endpoint.
        target_url = f"{base_url}/odata/v4/Products"

        # --- Prerequisite rows (created via the API) -----------------------
        # Create the source first and read back the id the API assigned, so
        # the connection and credential reference a row that actually exists.
        resp = client.post(
            "/api/sources",
            headers=admin_headers,
            json={"name": "issue420-source"},
        )
        assert resp.status_code == 201, resp.text
        source_id = resp.json()["id"]

        resp = client.post(
            "/api/source-connections",
            headers=admin_headers,
            json={
                "name": "issue420-connection",
                "endpoint": base_url,
                "source_id": source_id,
            },
        )
        assert resp.status_code == 201, resp.text

        resp = client.post(
            "/api/source-credentials",
            headers=admin_headers,
            json={
                "name": "issue420-credential",
                "auth_scheme": "basic",
                "principal": PRINCIPAL,
                "secret_ref": SECRET_ENV_VAR,
                "source_id": source_id,
            },
        )
        assert resp.status_code == 201, resp.text

        # --- First call: secret env var set -> body returned ---------------
        monkeypatch.setenv(SECRET_ENV_VAR, SECRET_VALUE)
        body = fetch_bytes(target_url)
        assert body == EXPECTED_BODY

        # --- Second call: secret env var unset -> EgressAuthError ----------
        monkeypatch.delenv(SECRET_ENV_VAR, raising=False)
        try:
            fetch_bytes(target_url)
            raised = False
        except EgressAuthError as exc:
            raised = True
            message = str(exc)
        assert raised, "expected EgressAuthError when the secret is unset"
        # The message must never leak the secret value.
        assert SECRET_VALUE not in message
    finally:
        server.shutdown()
        server.server_close()
