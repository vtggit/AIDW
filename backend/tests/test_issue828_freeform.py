"""Proving test for issue #828 — a failed run's ``error_detail`` never carries a foreign
exception's message.

Proves every acceptance criterion against the test database:

* a run made to fail by the test with a real ``psycopg2`` integrity error whose
  message (DETAIL line) names ``jane.ingest@example.test``: the run is ``failed``,
  and its ``error_detail`` read back through ``GET /api/runs`` as a non-admin user
  names the exception class and the SQLSTATE code, and contains none of the
  value, "DETAIL", or "Key (";
* a run failing with ``IngestError("dataset has no key fields to derive business
  keys from")``: that exact text is stored;
* a run failing with ``EgressError("HTTP 503 — Service Unavailable")``: that exact
  text is stored;
* a run failing with ``ValueError("jane.ingest@example.test")``: the detail is
  "ValueError" — without the value;
* a successful run whose post-ingest profiling raises a ``ValueError`` carrying
  the value: ``profile_error`` without the value, and the run still ``succeeded``;
* logs unchanged: the full exception is still written to the server log.
"""

import json
import logging
import uuid

import psycopg2

from app.db.connection import get_cursor
from app.egress import EgressError
from app.governance.safe_error import safe_error_detail
from app.ingest.service import create_pending_run, execute_run

PII_VALUE = "jane.ingest@example.test"

_RICH_EDMX = b"""<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">
  <edmx:DataServices>
    <Schema Namespace="NW" xmlns="http://docs.oasis-open.org/odata/ns/edm">
      <EntityType Name="Order">
        <Key><PropertyRef Name="OrderID"/></Key>
        <Property Name="OrderID" Type="Edm.Int32" Nullable="false"/>
        <Property Name="OrderDate" Type="Edm.DateTimeOffset"/>
        <Property Name="Freight" Type="Edm.Decimal"/>
        <Property Name="ShipCountry" Type="Edm.String"/>
        <Property Name="CustomerID" Type="Edm.Int32"/>
      </EntityType>
      <EntityContainer Name="C">
        <EntitySet Name="Orders" EntityType="NW.Order"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""

_PAGE_1 = json.dumps(
    {
        "value": [
            {
                "OrderID": i,
                "OrderDate": f"1998-05-{i + 1:02d}T00:00:00Z",
                "Freight": 10.0 + i,
                "ShipCountry": ["USA", "UK", "France"][i % 3],
                "CustomerID": 100 + i,
            }
            for i in range(10)
        ]
    }
).encode()


def _make_pipeline(client, admin_headers, monkeypatch):
    """A discovered OData source (with a key field on its dataset) and a cursor pipeline."""
    monkeypatch.setattr("app.api.discovery.ENABLE_INAPI_EGRESS", True)
    monkeypatch.setattr("app.api.ingest.ENABLE_INAPI_EGRESS", True)
    monkeypatch.setattr("app.discovery.service._fetch_metadata", lambda url: _RICH_EDMX)
    sid = client.post(
        "/api/sources", json={"name": "nw", "type": "odata"}, headers=admin_headers
    ).json()["id"]
    client.post(
        "/api/source-connections",
        json={
            "name": "conn",
            "endpoint": "https://svc.example/odata",
            "protocol_version": "V4",
            "source_id": sid,
        },
        headers=admin_headers,
    )
    client.post(f"/api/sources/{sid}/discover", headers=admin_headers)
    did = next(
        d["id"]
        for d in client.get("/api/datasets", headers=admin_headers).json()
        if d["source_id"] == sid
    )
    pid = client.post(
        "/api/pipelines",
        json={"name": "orders-pipe", "dataset_id": did, "cdc_pattern": "cursor"},
        headers=admin_headers,
    ).json()["id"]
    return pid, did


def _real_integrity_error() -> psycopg2.IntegrityError:
    """Trigger a REAL psycopg2 integrity error in the test database and return it.

    The probe is an ``ingested_records`` insert whose ``dataset_id`` is
    ``PII_VALUE``: the value fits the FK column but matches no dataset, so the
    database itself raises the foreign-key violation (SQLSTATE 23503) whose
    DETAIL line names the value. The insert rolls back — nothing persists.
    """
    with get_cursor() as cur:
        try:
            cur.execute(
                "INSERT INTO ingested_records "
                "(id, name, dataset_id, business_key, op) "
                "VALUES (%s, %s, %s, %s, 'insert')",
                (uuid.uuid4().hex, "fk probe", PII_VALUE, "probe-key"),
            )
        except psycopg2.IntegrityError as exc:
            return exc
    raise AssertionError("expected an integrity error from the dangling FK insert")


def _run_row(client, user_headers, run_id: str) -> dict:
    """The run read back through GET /api/runs as a NON-ADMIN (role 'user') user."""
    runs = client.get("/api/runs", headers=user_headers).json()
    return next(x for x in runs if x["id"] == run_id)


def _service_error_log(caplog) -> str:
    """Every ERROR-level record the ingest service logged, fully rendered."""
    records = [
        record
        for record in caplog.records
        if record.name == "app.ingest.service" and record.levelno >= logging.ERROR
    ]
    return "\n".join(logging.Formatter().format(record) for record in records)


def test_issue828_freeform(client, admin_headers, user_headers, monkeypatch, caplog):
    pid, did = _make_pipeline(client, admin_headers, monkeypatch)

    # the read-backs below are a real NON-ADMIN: it may read runs, it may not start them
    assert (
        client.post(f"/api/pipelines/{pid}/runs", headers=user_headers).status_code
        == 403
    )

    # ------------------------------------------------------------------
    # 1. A run made to fail with a REAL psycopg2 integrity error whose
    #    message names PII_VALUE: failed, and the error_detail read back
    #    through GET /api/runs as a non-admin user names the class and the
    #    SQLSTATE — never the value, "DETAIL", or "Key (".
    # ------------------------------------------------------------------
    exc = _real_integrity_error()
    assert isinstance(exc, psycopg2.IntegrityError)
    assert exc.pgcode == "23503"
    assert PII_VALUE in str(exc)  # sanity: the message really carries the value

    def _db_boom(url, timeout=None):
        raise exc

    monkeypatch.setattr("app.ingest.service._fetch_page", _db_boom)
    r = client.post(f"/api/pipelines/{pid}/runs", headers=admin_headers)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "failed"
    expected = safe_error_detail(exc)
    assert expected == f"{type(exc).__name__} (SQLSTATE {exc.pgcode})"
    assert type(exc).__name__ in expected  # the class is named
    assert f"SQLSTATE {exc.pgcode}" in expected  # ...and so is the SQLSTATE code
    assert body["error_detail"] == expected
    assert PII_VALUE not in body["error_detail"]
    assert "DETAIL" not in body["error_detail"]
    assert "Key (" not in body["error_detail"]

    row = _run_row(client, user_headers, body["id"])
    assert row["status"] == "failed"
    assert row["error_detail"] == expected
    assert PII_VALUE not in row["error_detail"]
    assert "DETAIL" not in row["error_detail"]
    assert "Key (" not in row["error_detail"]

    # logs unchanged: the full exception (message, DETAIL line, traceback)
    # still reaches the server log
    rendered = _service_error_log(caplog)
    assert rendered, "the run failure path must log the full exception"
    assert PII_VALUE in rendered
    assert "Traceback" in rendered
    caplog.clear()

    # ------------------------------------------------------------------
    # 2. A run failing with an OWN egress error: EgressError keeps its
    #    exact message.
    # ------------------------------------------------------------------
    def _http_boom(url, timeout=None):
        raise EgressError("HTTP 503 — Service Unavailable")

    monkeypatch.setattr("app.ingest.service._fetch_page", _http_boom)
    body = client.post(f"/api/pipelines/{pid}/runs", headers=admin_headers).json()
    assert body["status"] == "failed"
    assert body["error_detail"] == "HTTP 503 — Service Unavailable"
    row = _run_row(client, user_headers, body["id"])
    assert row["error_detail"] == "HTTP 503 — Service Unavailable"

    # ------------------------------------------------------------------
    # 3. A run failing with a FOREIGN ValueError carrying the value: the
    #    detail is the class name alone — without the value.
    # ------------------------------------------------------------------
    def _value_boom(url, timeout=None):
        raise ValueError(PII_VALUE)

    monkeypatch.setattr("app.ingest.service._fetch_page", _value_boom)
    body = client.post(f"/api/pipelines/{pid}/runs", headers=admin_headers).json()
    assert body["status"] == "failed"
    assert body["error_detail"] == "ValueError"
    assert PII_VALUE not in body["error_detail"]
    row = _run_row(client, user_headers, body["id"])
    assert row["error_detail"] == "ValueError"
    assert PII_VALUE not in row["error_detail"]

    # ------------------------------------------------------------------
    # 4. A successful run whose post-ingest profiling raises a ValueError
    #    carrying the value: profile_error without the value, the run still
    #    succeeded.
    # ------------------------------------------------------------------
    monkeypatch.setattr(
        "app.ingest.service._fetch_page", lambda url, timeout=None: _PAGE_1
    )

    def _profile_boom(source_id):
        raise ValueError(PII_VALUE)

    monkeypatch.setattr("app.ingest.service.profile_source", _profile_boom)
    r = client.post(f"/api/pipelines/{pid}/runs", headers=admin_headers)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "succeeded"  # a profiling failure never fails the run
    assert body["rows_read"] == 10 and body["rows_written"] == 10
    assert "profile" not in body
    assert body["profile_error"] == "ValueError"
    assert PII_VALUE not in body["profile_error"]
    row = _run_row(client, user_headers, body["id"])
    assert row["status"] == "succeeded"

    # the profiling failure is logged in full, too
    rendered = _service_error_log(caplog)
    assert PII_VALUE in rendered
    assert "Traceback" in rendered
    caplog.clear()

    # ------------------------------------------------------------------
    # 5. A run failing with the OWN IngestError precondition (context drift:
    #    the key fields vanish between enqueue and execute): that exact text
    #    is stored.
    # ------------------------------------------------------------------
    pending = create_pending_run(pid)
    field_ids = [
        f["id"]
        for f in client.get("/api/discovered-fields", headers=admin_headers).json()
        if f["dataset_id"] == did
    ]
    assert field_ids  # the pipeline really had (key) fields at enqueue time
    for field_id in field_ids:
        assert client.delete(
            f"/api/discovered-fields/{field_id}", headers=admin_headers
        ).status_code in (200, 204)
    body = execute_run(pending["id"])
    assert body is not None
    assert body["status"] == "failed"
    assert (
        body["error_detail"] == "dataset has no key fields to derive business keys from"
    )
    row = _run_row(client, user_headers, pending["id"])
    assert row["status"] == "failed"
    assert (
        row["error_detail"] == "dataset has no key fields to derive business keys from"
    )
