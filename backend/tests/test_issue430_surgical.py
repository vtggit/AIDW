"""Proving test for issue #430: _fetch_rows routes through app.egress.http.fetch_bytes."""

import base64
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

from app.dashboard.data_service import _fetch_rows
from app.db.connection import get_cursor


class _AuthDouble(BaseHTTPRequestHandler):
    """Returns the rows body only when the Authorization header is exactly right."""

    expected_auth = ""
    rows_body = b""

    def do_GET(self):
        if self.headers.get("Authorization", "") != self.expected_auth:
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="aidw"')
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(self.rows_body)

    def log_message(self, *args):
        pass


def test_issue430_surgical(clean_database, monkeypatch):
    principal = "chart-reader"
    secret = "s3cret-value"
    secret_env = "AIDW_TEST_CHART_SECRET"
    monkeypatch.setenv(secret_env, secret)

    rows_body = json.dumps({"value": [{"id": 1, "qty": 5}]}).encode("utf-8")
    _AuthDouble.expected_auth = (
        "Basic " + base64.b64encode(f"{principal}:{secret}".encode()).decode()
    )
    _AuthDouble.rows_body = rows_body

    server = HTTPServer(("127.0.0.1", 0), _AuthDouble)
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}"
    url = f"{base_url}/odata/Rows"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        source_id = str(uuid.uuid4())
        conn_id = str(uuid.uuid4())
        cred_id = str(uuid.uuid4())
        with get_cursor() as cur:
            cur.execute(
                "INSERT INTO sources (id, name) VALUES (%s, %s)",
                (source_id, "chart-source"),
            )
            cur.execute(
                "INSERT INTO source_connections (id, name, source_id, endpoint) "
                "VALUES (%s, %s, %s, %s)",
                (conn_id, "chart-conn", source_id, base_url),
            )
            cur.execute(
                "INSERT INTO source_credentials "
                "(id, name, source_id, auth_scheme, principal, secret_ref) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (cred_id, "chart-cred", source_id, "basic", principal, secret_env),
            )

        assert _fetch_rows(url) == rows_body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
