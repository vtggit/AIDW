import base64
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from app.db.connection import get_cursor
from app.discovery.service import _fetch_metadata

BODY = b"<edmx:Edmx/>"


def test_issue423_surgical(clean_database, monkeypatch):
    secret = "s3cr3t"
    monkeypatch.setenv("AIDW_423_SECRET", secret)
    auth = "Basic " + base64.b64encode(b"svc:" + secret.encode()).decode()

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            ok = self.headers.get("Authorization") == auth
            self.send_response(200 if ok else 401)
            self.end_headers()
            if ok:
                self.wfile.write(BODY)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        sid = "11111111-1111-4111-8111-111111111111"
        base = f"http://127.0.0.1:{port}"
        with get_cursor() as cur:
            cur.execute(
                "INSERT INTO sources(id,name,type,created_at,updated_at)"
                " VALUES(%s,%s,%s,NOW(),NOW())",
                (sid, "t", "odata"),
            )
            cur.execute(
                "INSERT INTO source_connections(id,source_id,endpoint,name,"
                "created_at) VALUES(%s,%s,%s,%s,NOW())",
                (sid + "c", sid, base, "p"),
            )
            cur.execute(
                "INSERT INTO source_credentials(id,source_id,auth_scheme,"
                "principal,secret_ref,name,created_at)"
                " VALUES(%s,%s,%s,%s,%s,%s,NOW())",
                (sid + "d", sid, "basic", "svc", "AIDW_423_SECRET", "p"),
            )
        assert _fetch_metadata(base + "/$metadata") == BODY
    finally:
        srv.shutdown()
