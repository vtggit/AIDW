import base64
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

from app.db.connection import get_cursor
from app.profiling.service import _fetch_rows


def _default_for(data_type: str, name: str):
    if data_type == "uuid":
        return str(uuid.uuid4())
    if data_type in ("character varying", "text", "name"):
        return f"fixture-{name}"
    if data_type in (
        "integer",
        "bigint",
        "smallint",
        "numeric",
        "double precision",
        "real",
    ):
        return 0
    if data_type == "boolean":
        return False
    if "timestamp" in data_type:
        return datetime.now(timezone.utc)
    if data_type == "jsonb":
        return "{}"
    return f"fixture-{name}"


def _insert_row(cur, table: str, values: dict) -> None:
    cur.execute(
        "SELECT column_name, is_nullable, data_type, column_default "
        "FROM information_schema.columns "
        "WHERE table_name = %s AND table_schema = current_schema()",
        (table,),
    )
    cols = [dict(r) for r in cur.fetchall()]
    chosen = []
    for c in cols:
        name = c["column_name"]
        if name in values:
            chosen.append((name, values[name]))
        elif c["is_nullable"] == "NO" and c["column_default"] is None:
            chosen.append((name, _default_for(c["data_type"], name)))
    col_list = ", ".join(n for n, _ in chosen)
    placeholders = ", ".join(["%s"] * len(chosen))
    cur.execute(
        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})",
        tuple(v for _, v in chosen),
    )


def test_issue428_surgical(clean_database, monkeypatch):
    principal, secret = "svc", "topsecret"
    ref = "AIDW_TEST_SECRET"
    monkeypatch.setenv(ref, secret)
    auth = "Basic " + base64.b64encode(f"{principal}:{secret}".encode()).decode()
    body = b'{"value": [{"id": "1"}]}'

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            ok = self.headers.get("Authorization") == auth
            self.send_response(200 if ok else 401)
            self.send_header("Content-Length", str(len(body) if ok else 0))
            self.end_headers()
            if ok:
                self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        sid = str(uuid.uuid4())
        with get_cursor() as cur:
            _insert_row(cur, "sources", {"id": sid, "name": "s"})
            _insert_row(
                cur,
                "source_connections",
                {"id": str(uuid.uuid4()), "source_id": sid, "endpoint": base},
            )
            _insert_row(
                cur,
                "source_credentials",
                {
                    "id": str(uuid.uuid4()),
                    "source_id": sid,
                    "auth_scheme": "basic",
                    "principal": principal,
                    "secret_ref": ref,
                },
            )
        assert _fetch_rows(f"{base}/Sales?$top=1&$format=json") == body
    finally:
        srv.shutdown()
