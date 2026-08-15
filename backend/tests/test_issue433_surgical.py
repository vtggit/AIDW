import base64
import http.server
import threading
import uuid

import pytest

from app.db.connection import get_cursor
from app.series.dashboard_item_series import _fetch_rows


@pytest.fixture
def auth_double(monkeypatch):
    principal = "svc-user"
    secret = "s3cr3t"
    secret_ref = "AIDW_TEST_SECRET"
    monkeypatch.setenv(secret_ref, secret)

    expected_auth = (
        "Basic " + base64.b64encode(f"{principal}:{secret}".encode()).decode()
    )
    body = b'[{"id": 1, "value": 42}]'

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            auth = self.headers.get("Authorization")
            if auth != expected_auth:
                self.send_response(401)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield {
        "base_url": f"http://127.0.0.1:{port}",
        "principal": principal,
        "secret_ref": secret_ref,
        "body": body,
    }

    server.shutdown()
    server.server_close()


def test_issue433_surgical(clean_database, auth_double):
    source_id = str(uuid.uuid4())
    conn_id = str(uuid.uuid4())
    cred_id = str(uuid.uuid4())

    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO sources (id, name) VALUES (%s, %s)",
            (source_id, "src"),
        )
        cur.execute(
            "INSERT INTO source_connections (id, source_id, name, endpoint) "
            "VALUES (%s, %s, %s, %s)",
            (conn_id, source_id, "conn", auth_double["base_url"]),
        )
        cur.execute(
            "INSERT INTO source_credentials (id, source_id, name, auth_scheme, "
            "principal, secret_ref) VALUES (%s, %s, %s, %s, %s, %s)",
            (
                cred_id,
                source_id,
                "cred",
                "basic",
                auth_double["principal"],
                auth_double["secret_ref"],
            ),
        )

    url = f"{auth_double['base_url']}/data"
    result = _fetch_rows(url)
    assert result == auth_double["body"]
