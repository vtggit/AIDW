import base64
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

from app.db.connection import get_cursor
from app.ingest.service import _fetch_page, start_run


class H(BaseHTTPRequestHandler):
    auth = body = None

    def do_GET(self):
        ok = self.headers.get("Authorization") == self.auth
        self.send_response(200 if ok else 401)
        self.end_headers()
        if ok:
            self.wfile.write(self.body)

    def log_message(self, *a):
        pass


def test_issue426_surgical(clean_database, monkeypatch):
    secret = "topsecret"
    H.auth = "Basic " + base64.b64encode(b"svc:" + secret.encode()).decode()
    H.body = b'{"value": []}'
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        now = datetime.now(timezone.utc)
        sid = str(uuid4())
        with get_cursor() as c:
            c.execute(
                "INSERT INTO sources (id,name,created_at,updated_at) "
                "VALUES (%s,%s,%s,%s)",
                (sid, "s", now, now),
            )
            c.execute(
                "INSERT INTO source_connections (id,name,source_id,endpoint,"
                "created_at,updated_at) VALUES (%s,%s,%s,%s,%s,%s)",
                (str(uuid4()), "c", sid, base, now, now),
            )
            c.execute(
                "INSERT INTO source_credentials (id,name,source_id,auth_scheme,"
                "principal,secret_ref,created_at,updated_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (str(uuid4()), "k", sid, "basic", "svc", "T426", now, now),
            )
        monkeypatch.setenv("T426", secret)
        assert _fetch_page(base + "/odata/Products") == H.body
        did, pid, fid = str(uuid4()), str(uuid4()), str(uuid4())
        with get_cursor() as c:
            c.execute("DELETE FROM source_credentials WHERE source_id=%s", (sid,))
            c.execute(
                "INSERT INTO datasets (id,name,source_id,created_at,updated_at) "
                "VALUES (%s,%s,%s,%s,%s)",
                (did, "products", sid, now, now),
            )
            c.execute(
                "INSERT INTO pipelines (id,name,dataset_id,created_at,updated_at) "
                "VALUES (%s,%s,%s,%s,%s)",
                (pid, "p", did, now, now),
            )
            c.execute(
                "INSERT INTO discovered_fields (id,dataset_id,name,data_type,"
                "is_key,field_position,created_at,updated_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (fid, did, "ProductID", "string", True, 1, now, now),
            )
        run = start_run(pid)
        assert run["status"] == "failed"
        assert run["error_detail"]
        assert secret not in run["error_detail"]
    finally:
        srv.shutdown()
        srv.server_close()
