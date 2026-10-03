"""Issue #657 — freeform proof: typed egress transport errors + per-connection fetch timeouts.

Proves, in a single node:

* AC-1/AC-5/AC-6: ``app.egress.http.fetch_bytes`` wraps ``TimeoutError``,
  ``socket.timeout``, non-HTTP ``urllib.error.URLError``, and ``OSError``
  in the typed ``EgressTransportError``.  Its message is exactly
  ``{ClassName} while contacting {host} after {timeout}s`` — *host* is the
  request URL's hostname (userinfo never included, ``<unknown>`` when the
  URL has none) and *timeout* is the value passed to ``fetch_bytes`` in
  seconds — and it never includes credentials, headers, response bodies,
  or raw exception text.
* AC-4: ``EgressTransportError`` subclasses the canonical ``EgressError``
  exported from ``app.egress`` (and the HTTP-layer ``EgressError`` in
  ``app.egress.http``), so package-level ``except EgressError`` handles it.
* AC-2/AC-3: discovery, ingest, and the connection test all pass
  ``source_connections.timeout_seconds`` (120) to the fetch, pass 30 when
  the column is NULL, and a stored value of 0 fails the operation with a
  clear error naming ``timeout_seconds`` (and no fetch is attempted).
"""

import socket
import urllib.error
from datetime import datetime, timezone
from uuid import uuid4

import pytest

import app.egress.http as egress_http
from app.db.connection import get_cursor
from app.egress import EgressError as EgressBaseError
from app.egress.http import (
    EgressError,
    EgressTransportError,
    _transport_error,
    fetch_bytes,
    resolve_fetch_timeout,
)
from app.ingest.service import IngestError, start_run

_ENDPOINT = "https://svc.example/odata"
_METADATA_URL = f"{_ENDPOINT}/$metadata"
_PAGE_URL = f"{_ENDPOINT}/products?$top=500&$format=json"
_TRANSPORT_URL = "http://127.0.0.1:9/metadata"

# Sentinel secret value that must never appear in any exposed error message.
_SENTINEL_SECRET = "SENTINEL-SECRET-657-DO-NOT-LEAK"
_SECRET_REF = "ISSUE657_SECRET"
# Raw exception text that must never be copied into a typed error message.
_RAW_TEXT = "raw-exception-text-must-not-leak"

_EDMX = b"""<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">
  <edmx:DataServices>
    <Schema Namespace="Demo" xmlns="http://docs.oasis-open.org/odata/ns/edm">
      <EntityType Name="Product">
        <Key><PropertyRef Name="ProductID"/></Key>
        <Property Name="ProductID" Type="Edm.Int32" Nullable="false"/>
        <Property Name="Name" Type="Edm.String"/>
      </EntityType>
      <EntityContainer Name="Container">
        <EntitySet Name="Products" EntityType="Demo.Product"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""


class _FakeOpener:
    """Stand-in for urllib's opener: records the timeout it is asked to use
    and raises the supplied transport exception on ``open``."""

    def __init__(self, exc):
        self._exc = exc
        self.timeout = None

    def open(self, request, timeout=None):
        self.timeout = timeout
        raise self._exc


def test_issue657_freeform(client, admin_headers, monkeypatch):
    # ------------------------------------------------------------------
    # AC-4: the transport error is a subclass of the canonical EgressError
    # exported from app.egress (and of the HTTP-layer EgressError).
    # ------------------------------------------------------------------
    assert issubclass(EgressTransportError, EgressBaseError)
    assert issubclass(EgressTransportError, EgressError)
    assert issubclass(EgressError, EgressBaseError)

    # ------------------------------------------------------------------
    # resolve_fetch_timeout contract: NULL -> 30, 1-600 -> identity,
    # anything else -> ValueError naming timeout_seconds (no raw echo).
    # ------------------------------------------------------------------
    assert resolve_fetch_timeout(None) == 30
    assert resolve_fetch_timeout(1) == 1
    assert resolve_fetch_timeout(120) == 120
    assert resolve_fetch_timeout(600) == 600
    for bad in (0, -1, 601, 30.5, "30", True, False, [30]):
        with pytest.raises(ValueError) as ei:
            resolve_fetch_timeout(bad)
        assert "timeout_seconds" in str(ei.value)
        # The message is a fixed, field-naming string — hostile stored
        # values are never echoed back into it.
        assert str(ei.value) == (
            "source_connections.timeout_seconds must be an integer between 1 and 600"
        )

    # ------------------------------------------------------------------
    # AC-1/AC-5/AC-6: transport failures from fetch_bytes surface as a
    # typed EgressTransportError with the exact message form and no
    # sensitive material.  A resolvable basic credential for the target
    # origin is seeded so an auth header WOULD be attached — its secret
    # and principal must not leak into the message either.
    # ------------------------------------------------------------------
    monkeypatch.delenv("EGRESS_POLICY", raising=False)
    monkeypatch.delenv("EGRESS_ALLOWED_HOSTS", raising=False)
    monkeypatch.setenv(_SECRET_REF, _SENTINEL_SECRET)

    source_id = str(uuid4())
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO sources (id,name,created_at,updated_at) "
            "VALUES (%s,%s,NOW(),NOW())",
            (source_id, "issue657"),
        )
        cur.execute(
            "INSERT INTO source_connections (id,name,endpoint,source_id,"
            "created_at,updated_at) VALUES (%s,%s,%s,%s,NOW(),NOW())",
            (str(uuid4()), "issue657-conn", "http://127.0.0.1:9", source_id),
        )
        cur.execute(
            "INSERT INTO source_credentials (id,name,source_id,auth_scheme,"
            "principal,secret_ref,created_at,updated_at) "
            "VALUES (%s,%s,%s,'basic','issue657-principal',%s,NOW(),NOW())",
            (str(uuid4()), "issue657-cred", source_id, _SECRET_REF),
        )

    def _expect_transport_error(exc, timeout, expected_message):
        opener = _FakeOpener(exc)
        monkeypatch.setattr(
            egress_http.urllib.request, "build_opener", lambda *a, **k: opener
        )
        with pytest.raises(EgressTransportError) as ei:
            fetch_bytes(_TRANSPORT_URL, timeout=timeout)
        err = ei.value
        assert isinstance(err, EgressBaseError)
        assert str(err) == expected_message
        assert _SENTINEL_SECRET not in str(err)
        assert "issue657-principal" not in str(err)
        assert _RAW_TEXT not in str(err)
        assert "Authorization" not in str(err)
        # The original exception is chained for debugging but its text is
        # never copied into the exposed message.
        assert err.__cause__ is exc
        # The configured timeout was actually handed to the transport.
        assert opener.timeout == timeout

    # AC-1: TimeoutError — message names the class, the host, and the timeout.
    _expect_transport_error(
        TimeoutError(f"timed out ({_RAW_TEXT})"),
        120,
        "TimeoutError while contacting 127.0.0.1 after 120s",
    )
    # AC-5: socket.timeout (an alias of TimeoutError on py3.10+).
    _expect_transport_error(
        TimeoutError(_RAW_TEXT),
        45,
        f"{socket.timeout.__name__} while contacting 127.0.0.1 after 45s",
    )
    # AC-5: urllib.error.URLError (e.g. a wrapped connection-refused).
    _expect_transport_error(
        urllib.error.URLError(ConnectionRefusedError(111, _RAW_TEXT)),
        120,
        "URLError while contacting 127.0.0.1 after 120s",
    )
    # AC-5: a bare OSError (e.g. a mid-body connection reset).
    _expect_transport_error(
        OSError(_RAW_TEXT), 30, "OSError while contacting 127.0.0.1 after 30s"
    )

    # AC-1: a hostless URL renders as <unknown>; userinfo never leaks.
    err = _transport_error("not-a-url", 30, OSError(_RAW_TEXT))
    assert str(err) == "OSError while contacting <unknown> after 30s"
    err = _transport_error(
        "http://user:hunter2-secret@127.0.0.1:9/metadata", 5, TimeoutError("x")
    )
    assert str(err) == "TimeoutError while contacting 127.0.0.1 after 5s"
    assert "hunter2-secret" not in str(err)
    assert "user:" not in str(err)

    # ------------------------------------------------------------------
    # AC-2/AC-3: discovery passes timeout_seconds to the fetch (120), 30
    # on NULL, and 0 fails with an error naming timeout_seconds.
    # ------------------------------------------------------------------
    monkeypatch.setattr("app.api.discovery.ENABLE_INAPI_EGRESS", True)

    def _make_source(timeout_seconds):
        r = client.post(
            "/api/sources",
            json={"name": f"issue657-src-{uuid4().hex[:8]}", "type": "odata"},
            headers=admin_headers,
        )
        assert r.status_code == 201, r.text
        sid = r.json()["id"]
        conn_body = {
            "name": "issue657-conn",
            "endpoint": _ENDPOINT,
            "protocol_version": "V4",
            "source_id": sid,
        }
        if timeout_seconds is not None:
            conn_body["timeout_seconds"] = timeout_seconds
        r = client.post(
            "/api/source-connections", json=conn_body, headers=admin_headers
        )
        assert r.status_code == 201, r.text
        return sid

    def _recorded_fetch(monkeypatch, body):
        calls = []

        def fake_fetch(url, timeout=30):
            calls.append((url, timeout))
            return body

        monkeypatch.setattr("app.discovery.service.fetch_bytes", fake_fetch)
        return calls, fake_fetch

    def _discover(sid):
        return client.post(f"/api/sources/{sid}/discover", headers=admin_headers)

    sid = _make_source(120)
    calls, _ = _recorded_fetch(monkeypatch, _EDMX)
    r = _discover(sid)
    assert r.status_code == 200, r.text
    assert calls == [(_METADATA_URL, 120)]

    sid = _make_source(None)
    calls, _ = _recorded_fetch(monkeypatch, _EDMX)
    r = _discover(sid)
    assert r.status_code == 200, r.text
    assert calls == [(_METADATA_URL, 30)]

    sid = _make_source(0)
    calls, _ = _recorded_fetch(monkeypatch, _EDMX)
    r = _discover(sid)
    assert r.status_code == 422
    assert "timeout_seconds" in r.json()["detail"]
    assert calls == []

    # ------------------------------------------------------------------
    # AC-2/AC-3: same contract for ingest (run executor path).
    # ------------------------------------------------------------------
    def _seed_ingest_pipeline(timeout_seconds):
        now = datetime.now(timezone.utc)
        source_id, conn_id, dataset_id, pipeline_id, field_id = (
            str(uuid4()) for _ in range(5)
        )
        with get_cursor() as cur:
            cur.execute(
                "INSERT INTO sources (id,name,created_at,updated_at) "
                "VALUES (%s,%s,%s,%s)",
                (source_id, f"issue657-ing-{uuid4().hex[:8]}", now, now),
            )
            if timeout_seconds is None:
                cur.execute(
                    "INSERT INTO source_connections (id,name,endpoint,source_id,"
                    "created_at,updated_at) VALUES (%s,%s,%s,%s,%s,%s)",
                    (conn_id, "issue657-conn", _ENDPOINT, source_id, now, now),
                )
            else:
                cur.execute(
                    "INSERT INTO source_connections (id,name,endpoint,source_id,"
                    "timeout_seconds,created_at,updated_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (
                        conn_id,
                        "issue657-conn",
                        _ENDPOINT,
                        source_id,
                        timeout_seconds,
                        now,
                        now,
                    ),
                )
            cur.execute(
                "INSERT INTO datasets (id,name,source_id,created_at,updated_at) "
                "VALUES (%s,%s,%s,%s,%s)",
                (dataset_id, "products", source_id, now, now),
            )
            cur.execute(
                "INSERT INTO pipelines (id,name,dataset_id,created_at,updated_at) "
                "VALUES (%s,%s,%s,%s,%s)",
                (pipeline_id, f"issue657-pipe-{uuid4().hex[:8]}", dataset_id, now, now),
            )
            cur.execute(
                "INSERT INTO discovered_fields (id,dataset_id,name,data_type,"
                "is_key,field_position,created_at,updated_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (field_id, dataset_id, "ProductID", "Edm.Int32", True, 1, now, now),
            )
        return pipeline_id

    def _ingest_calls(monkeypatch):
        calls = []

        def fake_fetch(url, timeout=30):
            calls.append((url, timeout))
            return b'{"value": []}'

        # The run's own page fetch (bound name) and profiling's fetch
        # (module-attribute lookup) both resolve to the recorder.
        monkeypatch.setattr("app.egress.http.fetch_bytes", fake_fetch)
        monkeypatch.setattr("app.ingest.service.fetch_bytes", fake_fetch)
        return calls

    pipeline_id = _seed_ingest_pipeline(120)
    calls = _ingest_calls(monkeypatch)
    body = start_run(pipeline_id)
    assert body["status"] == "succeeded", body
    assert [t for u, t in calls if u == _PAGE_URL] == [120]
    assert all(t == 30 for u, t in calls if u != _PAGE_URL)

    pipeline_id = _seed_ingest_pipeline(None)
    calls = _ingest_calls(monkeypatch)
    body = start_run(pipeline_id)
    assert body["status"] == "succeeded", body
    assert (_PAGE_URL, 30) in calls

    pipeline_id = _seed_ingest_pipeline(0)
    with pytest.raises(IngestError) as ei:
        start_run(pipeline_id)
    assert "timeout_seconds" in str(ei.value)
    with get_cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM runs WHERE pipeline_id = %s", (pipeline_id,)
        )
        assert cur.fetchone()["n"] == 0

    # ------------------------------------------------------------------
    # AC-2/AC-3: same contract for the connection test run endpoint.
    # ------------------------------------------------------------------
    def _make_connection_test(timeout_seconds):
        sid = _make_source(timeout_seconds)
        r = client.post(
            "/api/connection-tests",
            json={"name": f"issue657-ct-{uuid4().hex[:8]}", "source_id": sid},
            headers=admin_headers,
        )
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def _ct_calls(monkeypatch):
        calls = []

        def fake_fetch(url, timeout=30):
            calls.append((url, timeout))
            return b"<edmx/>"

        monkeypatch.setattr("app.egress.http.fetch_bytes", fake_fetch)
        return calls

    def _run_ct(ct_id):
        return client.post(f"/api/connection-tests/{ct_id}/run", headers=admin_headers)

    ct_id = _make_connection_test(120)
    calls = _ct_calls(monkeypatch)
    r = _run_ct(ct_id)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ok"
    assert calls == [(_METADATA_URL, 120)]

    ct_id = _make_connection_test(None)
    calls = _ct_calls(monkeypatch)
    r = _run_ct(ct_id)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ok"
    assert calls == [(_METADATA_URL, 30)]

    ct_id = _make_connection_test(0)
    calls = _ct_calls(monkeypatch)
    r = _run_ct(ct_id)
    assert r.status_code == 422
    assert "timeout_seconds" in r.json()["detail"]
    assert calls == []
