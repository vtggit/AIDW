"""Issue #520 — egress credential resolution and anonymous fallback.

Proves the three acceptance criteria against the real
``app.egress.http`` modules:

1. ``credential_for_url`` matches an endpoint only on an origin and path
   boundary (exact scheme + host + effective port, plus a path prefix that
   ends on a path-segment boundary), so a longer sibling host, a different
   port, a different scheme, or a path that merely shares a textual prefix
   does not resolve another endpoint's credential.  Dot segments are
   normalized, so a path that escapes the boundary via ``..`` does not
   match.
2. When a source has multiple ``source_credentials`` rows, the intended
   active (most recently created) credential is selected deterministically
   rather than the earliest, so a rotated credential takes effect.
3. A URL that resolves to a credential with an unsupported ``auth_scheme``,
   or to no credential at all, performs the anonymous fetch the pre-egress
   callers performed instead of failing closed before the request.

The tests drive the real ``credential_for_url`` / ``fetch_bytes`` path
against in-process HTTP doubles on 127.0.0.1 and seed rows through the
shared ``get_cursor`` helper.
"""

import base64
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from app.db.connection import get_cursor
from app.egress.http import credential_for_url, fetch_bytes

_SECRET_REF = "AIDW_TEST_EGRESS_SECRET_520"
_SENTINEL_SECRET = "SENTINEL-SECRET-520-DO-NOT-LEAK"


class _RequestRecorder:
    """Counts every request the in-process double receives and records the
    Authorization header of each."""

    def __init__(self) -> None:
        self.count = 0
        self.auth_headers: list[str | None] = []
        self._lock = threading.Lock()

    def record(self, auth_header: str | None) -> None:
        with self._lock:
            self.count += 1
            self.auth_headers.append(auth_header)

    @property
    def requests(self) -> int:
        with self._lock:
            return self.count


def _make_handler(recorder: _RequestRecorder):
    """Build a BaseHTTPRequestHandler subclass that records and answers 200."""

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - http.server API
            recorder.record(self.headers.get("Authorization"))
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # silence default stderr logging
            return

    return _Handler


def _start_double():
    """Start an in-process HTTP server on 127.0.0.1.

    Returns ``(url, recorder, server, thread)``.
    """
    recorder = _RequestRecorder()
    handler = _make_handler(recorder)
    server = HTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"http://127.0.0.1:{port}", recorder, server, thread


def _stop_double(server: HTTPServer, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def _seed_source(source_id: str, name: str) -> None:
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO sources (id, name, created_at, updated_at) "
            "VALUES (%s, %s, NOW(), NOW()) ON CONFLICT (id) DO NOTHING",
            (source_id, name),
        )


def _seed_connection(conn_id: str, source_id: str, endpoint: str) -> None:
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO source_connections "
            "(id, source_id, name, endpoint, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, NOW(), NOW()) ON CONFLICT (id) DO NOTHING",
            (conn_id, source_id, f"conn {conn_id}", endpoint),
        )


def _seed_credential(
    cred_id: str,
    source_id: str,
    name: str,
    auth_scheme: str,
    principal: str,
    secret_ref: str,
    created_at: str,
) -> None:
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO source_credentials "
            "(id, source_id, name, auth_scheme, principal, secret_ref, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, NOW()) ON CONFLICT (id) DO NOTHING",
            (cred_id, source_id, name, auth_scheme, principal, secret_ref, created_at),
        )


def test_issue520_freeform(monkeypatch):
    monkeypatch.setenv(_SECRET_REF, _SENTINEL_SECRET)
    monkeypatch.delenv("EGRESS_POLICY", raising=False)
    monkeypatch.delenv("EGRESS_ALLOWED_HOSTS", raising=False)

    # ------------------------------------------------------------------
    # AC 1 — origin (scheme + host + port) and path-segment boundary.
    # ------------------------------------------------------------------
    _seed_source("src-520-main", "issue520 main source")
    _seed_connection("conn-520-main", "src-520-main", "http://api.example.com/api")
    _seed_credential(
        "cred-520-main",
        "src-520-main",
        "issue520 main credential",
        "basic",
        "main-principal",
        _SECRET_REF,
        "2020-01-01 00:00:00+00",
    )

    # Sibling host sharing a textual prefix of the target host.
    _seed_source("src-520-sibhost", "issue520 sibling-host source")
    _seed_connection(
        "conn-520-sibhost", "src-520-sibhost", "http://api.example.comx/api"
    )
    _seed_credential(
        "cred-520-sibhost",
        "src-520-sibhost",
        "issue520 sibling-host credential",
        "basic",
        "sibhost-principal",
        _SECRET_REF,
        "2020-01-01 00:00:00+00",
    )

    # Sibling port on the same host.
    _seed_source("src-520-sibport", "issue520 sibling-port source")
    _seed_connection(
        "conn-520-sibport", "src-520-sibport", "http://api.example.com:8080/api"
    )
    _seed_credential(
        "cred-520-sibport",
        "src-520-sibport",
        "issue520 sibling-port credential",
        "basic",
        "sibport-principal",
        _SECRET_REF,
        "2020-01-01 00:00:00+00",
    )

    # Sibling scheme on the same host/port.
    _seed_source("src-520-sibscheme", "issue520 sibling-scheme source")
    _seed_connection(
        "conn-520-sibscheme", "src-520-sibscheme", "https://api.example.com/api"
    )
    _seed_credential(
        "cred-520-sibscheme",
        "src-520-sibscheme",
        "issue520 sibling-scheme credential",
        "basic",
        "sibscheme-principal",
        _SECRET_REF,
        "2020-01-01 00:00:00+00",
    )

    # Sibling path sharing a textual prefix of the target path.
    _seed_source("src-520-sibpath", "issue520 sibling-path source")
    _seed_connection(
        "conn-520-sibpath", "src-520-sibpath", "http://api.example.com/apix"
    )
    _seed_credential(
        "cred-520-sibpath",
        "src-520-sibpath",
        "issue520 sibling-path credential",
        "basic",
        "sibpath-principal",
        _SECRET_REF,
        "2020-01-01 00:00:00+00",
    )

    # The exact target resolves the main credential, not any sibling.
    resolved = credential_for_url("http://api.example.com/api")
    assert resolved is not None
    assert resolved["id"] == "cred-520-main"
    assert resolved["principal"] == "main-principal"

    # A path genuinely under the /api segment boundary still resolves main.
    resolved_under = credential_for_url("http://api.example.com/api/thing")
    assert resolved_under is not None
    assert resolved_under["id"] == "cred-520-main"

    # The sibling path /apix resolves its own credential when the target is
    # genuinely under /apix (proving the boundary logic is real, not a
    # blanket no-match).
    resolved_sibpath = credential_for_url("http://api.example.com/apix/thing")
    assert resolved_sibpath is not None
    assert resolved_sibpath["id"] == "cred-520-sibpath"

    # The sibling host resolves its own credential for its own host.
    resolved_sibhost = credential_for_url("http://api.example.comx/api")
    assert resolved_sibhost is not None
    assert resolved_sibhost["id"] == "cred-520-sibhost"

    # The sibling port resolves its own credential for its own port.
    resolved_sibport = credential_for_url("http://api.example.com:8080/api")
    assert resolved_sibport is not None
    assert resolved_sibport["id"] == "cred-520-sibport"

    # The sibling scheme resolves its own credential for its own scheme.
    resolved_sibscheme = credential_for_url("https://api.example.com/api")
    assert resolved_sibscheme is not None
    assert resolved_sibscheme["id"] == "cred-520-sibscheme"

    # A dot-segment path that normalizes OUTSIDE the /api boundary must not
    # resolve the main credential (effective path is /secret).
    resolved_dot = credential_for_url("http://api.example.com/api/../secret")
    assert resolved_dot is None

    # ------------------------------------------------------------------
    # AC 2 — deterministic active-credential selection (rotation wins).
    # ------------------------------------------------------------------
    base, recorder, server, thread = _start_double()
    try:
        _seed_source("src-520-fetch", "issue520 fetch source")
        _seed_connection("conn-520-fetch", "src-520-fetch", base)
        _seed_credential(
            "cred-520-fetch-old",
            "src-520-fetch",
            "issue520 old credential",
            "basic",
            "old-principal",
            _SECRET_REF,
            "2020-01-01 00:00:00+00",
        )

        # Only the earliest credential exists; the resolver picks it.
        resolved_old = credential_for_url(f"{base}/odata")
        assert resolved_old is not None
        assert resolved_old["id"] == "cred-520-fetch-old"

        # Rotate: add a later-created credential. The resolver must now pick
        # the most recently created row, not the earliest.
        _seed_credential(
            "cred-520-fetch-rotated",
            "src-520-fetch",
            "issue520 rotated credential",
            "basic",
            "rotated-principal",
            _SECRET_REF,
            "2024-06-01 00:00:00+00",
        )
        resolved_rotated = credential_for_url(f"{base}/odata")
        assert resolved_rotated is not None
        assert resolved_rotated["id"] == "cred-520-fetch-rotated"
        assert resolved_rotated["principal"] == "rotated-principal"

        # The rotated credential's Authorization header is what the fetch sends.
        expected_token = base64.b64encode(
            f"rotated-principal:{_SENTINEL_SECRET}".encode()
        ).decode("ascii")
        recorder.count = 0
        recorder.auth_headers.clear()
        body = fetch_bytes(f"{base}/odata")
        assert body == b"ok"
        assert recorder.requests == 1
        assert recorder.auth_headers[0] == f"Basic {expected_token}"

        # ------------------------------------------------------------------
        # AC 3a — unsupported auth_scheme performs the anonymous fetch.
        # ------------------------------------------------------------------
        _seed_credential(
            "cred-520-fetch-unsupported",
            "src-520-fetch",
            "issue520 unsupported credential",
            "oauth2",
            "unsupported-principal",
            _SECRET_REF,
            "2025-01-01 00:00:00+00",
        )
        resolved_unsupported = credential_for_url(f"{base}/odata")
        assert resolved_unsupported is not None
        assert resolved_unsupported["id"] == "cred-520-fetch-unsupported"
        assert resolved_unsupported["auth_scheme"] == "oauth2"

        recorder.count = 0
        recorder.auth_headers.clear()
        body_unsupported = fetch_bytes(f"{base}/odata")
        assert body_unsupported == b"ok"
        assert recorder.requests == 1
        # Anonymous: no Authorization header was attached.
        assert recorder.auth_headers[0] is None
    finally:
        _stop_double(server, thread)

    # ------------------------------------------------------------------
    # AC 3b — no credential at all performs the anonymous fetch.
    # ------------------------------------------------------------------
    anon_base, anon_recorder, anon_server, anon_thread = _start_double()
    try:
        # No source_connection is seeded for this host:port, so the URL
        # resolves to no credential. The fetch must still go out anonymously.
        assert credential_for_url(f"{anon_base}/anything") is None
        anon_recorder.count = 0
        anon_recorder.auth_headers.clear()
        body_anon = fetch_bytes(f"{anon_base}/anything")
        assert body_anon == b"ok"
        assert anon_recorder.requests == 1
        assert anon_recorder.auth_headers[0] is None
    finally:
        _stop_double(anon_server, anon_thread)
