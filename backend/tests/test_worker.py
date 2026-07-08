"""Connector/ingestion worker tests (real Postgres).

Proves the doc §1 API⊥worker split with observable output state: the SKIP LOCKED claim really
skips a locked row (probe R1, two live connections), the worker-mode endpoint enqueues WITHOUT
egress, run_once executes a claimed run through the same ingest logic (identical op-log/cursor/
run rows as the inline path), context drift after enqueue lands ON the run, and the reaper
finalizes stale running rows without touching live ones.
"""

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg2

from app.db.connection import get_connection_params, get_cursor
from app.worker.loop import claim_next, main_loop, reap_stale_running, run_once

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

_ROWS_JSON = json.dumps(
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


def _make_odata_source(client, admin_headers):
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
    return sid


def _discovered_pipeline(client, admin_headers, monkeypatch):
    monkeypatch.setattr("app.api.discovery.ENABLE_INAPI_EGRESS", True)
    monkeypatch.setattr("app.discovery.service._fetch_metadata", lambda url: _RICH_EDMX)
    sid = _make_odata_source(client, admin_headers)
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


def _arm_worker_mode(monkeypatch):
    """Worker-mode endpoint + mocked egress for the worker-side execution. ENABLE_INAPI_EGRESS
    stays FALSE — enqueueing must not need it (the API does no egress in worker mode).
    """
    monkeypatch.setattr("app.api.ingest.INGEST_EXECUTOR", "worker")
    monkeypatch.setattr("app.ingest.service._fetch_page", lambda url: _ROWS_JSON)
    monkeypatch.setattr("app.profiling.service._fetch_rows", lambda url: _ROWS_JSON)


def _drain_queue():
    """Claim away any pending runs left behind by other tests so claim order is deterministic."""
    while claim_next() is not None:
        pass


# --------------------------------------------------------------------------- claim (probe R1)


def test_skip_locked_claim_skips_locked_rows(client, admin_headers):
    """Two live connections: while one holds FOR UPDATE on the only pending run, claim_next()
    must skip it (SKIP LOCKED) and return None; after release it claims that exact row.
    """
    _drain_queue()
    rid = client.post(
        "/api/runs",
        json={"name": "claim-me", "status": "pending"},
        headers=admin_headers,
    ).json()["id"]

    blocker = psycopg2.connect(**get_connection_params())
    try:
        with blocker.cursor() as cur:
            cur.execute("SELECT id FROM runs WHERE id = %s FOR UPDATE", (rid,))
        assert (
            claim_next() is None
        )  # the only pending row is locked -> skipped, not blocked
    finally:
        blocker.rollback()
        blocker.close()

    assert claim_next() == rid
    run = client.get(f"/api/runs/{rid}", headers=admin_headers).json()
    assert run["status"] == "running" and run["started_at"] is not None
    # claimed exactly once — the queue is empty now
    assert claim_next() is None


def test_claim_order_is_oldest_first(client, admin_headers):
    _drain_queue()
    first = client.post(
        "/api/runs", json={"name": "older", "status": "pending"}, headers=admin_headers
    ).json()["id"]
    second = client.post(
        "/api/runs", json={"name": "newer", "status": "pending"}, headers=admin_headers
    ).json()["id"]
    assert claim_next() == first
    assert claim_next() == second


# --------------------------------------------------------------------------- worker execution


def test_worker_mode_enqueues_then_run_once_executes(
    client, admin_headers, monkeypatch
):
    pid, did = _discovered_pipeline(client, admin_headers, monkeypatch)
    _arm_worker_mode(monkeypatch)
    _drain_queue()

    r = client.post(f"/api/pipelines/{pid}/runs", headers=admin_headers)
    assert (
        r.status_code == 202
    )  # enqueued, not executed — and no egress flag was needed
    pending = r.json()
    assert pending["status"] == "pending" and pending["pipeline_id"] == pid
    assert pending["started_at"] is None

    body = run_once()
    assert body is not None and body["id"] == pending["id"]
    assert body["status"] == "succeeded"
    assert body["rows_read"] == 10 and body["inserts"] == 10

    # identical observable state to the inline path: op-log, cursor, run row, §6 pass
    oplog = [
        x
        for x in client.get("/api/ingested-records", headers=admin_headers).json()
        if x["dataset_id"] == did
    ]
    assert len(oplog) == 10 and all(x["op"] == "insert" for x in oplog)
    cursor = next(
        c
        for c in client.get("/api/delta-cursors", headers=admin_headers).json()
        if c["pipeline_id"] == pid
    )
    assert cursor["cursor_value"] == "1998-05-10T00:00:00Z"
    assert cursor["last_run_id"] == body["id"]
    run = client.get(f"/api/runs/{body['id']}", headers=admin_headers).json()
    assert run["status"] == "succeeded" and run["started_at"] is not None
    assert body["profile"]["fields_profiled"] == 5

    assert run_once() is None  # queue drained


def test_run_once_empty_queue_returns_none(client):
    _drain_queue()
    assert run_once() is None


def test_pipeline_deleted_after_enqueue_lands_on_run(
    client, admin_headers, monkeypatch
):
    """Context drift between enqueue and execute must finalize the run failed — never raise,
    never leave it pending/running."""
    pid, _did = _discovered_pipeline(client, admin_headers, monkeypatch)
    _arm_worker_mode(monkeypatch)
    _drain_queue()

    pending = client.post(f"/api/pipelines/{pid}/runs", headers=admin_headers).json()
    client.delete(f"/api/pipelines/{pid}", headers=admin_headers)  # FK SET NULL on runs

    body = run_once()
    assert body is not None and body["id"] == pending["id"]
    assert body["status"] == "failed"
    assert "pipeline" in body["error_detail"]
    run = client.get(f"/api/runs/{body['id']}", headers=admin_headers).json()
    assert run["status"] == "failed" and run["finished_at"] is not None


def test_main_loop_drains_with_max_iterations(client, admin_headers, monkeypatch):
    pid, did = _discovered_pipeline(client, admin_headers, monkeypatch)
    _arm_worker_mode(monkeypatch)
    _drain_queue()
    pending = client.post(f"/api/pipelines/{pid}/runs", headers=admin_headers).json()

    main_loop(poll_seconds=0, max_iterations=1)

    run = client.get(f"/api/runs/{pending['id']}", headers=admin_headers).json()
    assert run["status"] == "succeeded"


def test_load_context_crash_lands_on_run_not_raised(client, admin_headers, monkeypatch):
    """ANY post-claim failure — even an unexpected one inside context loading — must finalize
    the run failed, never escape and leave a committed 'running' row stuck."""
    pid, _did = _discovered_pipeline(client, admin_headers, monkeypatch)
    _arm_worker_mode(monkeypatch)
    _drain_queue()
    pending = client.post(f"/api/pipelines/{pid}/runs", headers=admin_headers).json()

    def boom(pipeline_id):
        raise RuntimeError("db blip while loading context")

    monkeypatch.setattr("app.ingest.service._load_context", boom)
    body = run_once()
    assert body is not None and body["id"] == pending["id"]
    assert body["status"] == "failed"
    assert "db blip" in body["error_detail"]


def test_externally_finalized_run_is_not_resurrected(
    client, admin_headers, monkeypatch
):
    """If the reaper (or an admin) finalizes a run while its executor is mid-flight, the
    terminal state wins: no 'succeeded' resurrection, no watermark advance from the zombie.
    """
    pid, _did = _discovered_pipeline(client, admin_headers, monkeypatch)
    _arm_worker_mode(monkeypatch)
    _drain_queue()
    pending = client.post(f"/api/pipelines/{pid}/runs", headers=admin_headers).json()

    def fetch_and_reap(url):
        # simulate the reaper firing mid-execution, between claim and finalize
        with get_cursor() as cur:
            cur.execute(
                "UPDATE runs SET status = 'failed', error_detail = 'reaped: test' "
                "WHERE id = %s",
                (pending["id"],),
            )
        return _ROWS_JSON

    monkeypatch.setattr("app.ingest.service._fetch_page", fetch_and_reap)
    body = run_once()
    assert body is not None and body["id"] == pending["id"]
    assert body["status"] == "failed"  # the terminal state won
    assert "reaped" in body["error_detail"]
    # the zombie's watermark advance was discarded along with its bookkeeping
    cursor = next(
        (
            c
            for c in client.get("/api/delta-cursors", headers=admin_headers).json()
            if c["pipeline_id"] == pid
        ),
        None,
    )
    assert cursor is not None and cursor["cursor_value"] is None
    assert cursor["last_run_id"] is None


# --------------------------------------------------------------------------- reaper


def _insert_running_run(name: str, updated_at) -> str:
    run_id = str(uuid4())
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO runs (id, name, status, started_at, created_at, updated_at) "
            "VALUES (%s, %s, 'running', %s, %s, %s)",
            (run_id, name, updated_at, updated_at, updated_at),
        )
    return run_id


def test_reaper_finalizes_stale_running_only(client, admin_headers):
    now = datetime.now(timezone.utc)
    stale = _insert_running_run("stale-run", now - timedelta(hours=2))
    live = _insert_running_run("live-run", now)

    assert reap_stale_running(max_age_seconds=3600) >= 1

    stale_row = client.get(f"/api/runs/{stale}", headers=admin_headers).json()
    assert stale_row["status"] == "failed"
    assert "reaped" in stale_row["error_detail"]
    assert stale_row["finished_at"] is not None
    live_row = client.get(f"/api/runs/{live}", headers=admin_headers).json()
    assert live_row["status"] == "running"  # a live executor's run is untouched

    # cleanup so later claim/drain assertions in this module stay deterministic
    client.delete(f"/api/runs/{live}", headers=admin_headers)


# --------------------------------------------------------------------------- endpoint modes


def test_worker_mode_unknown_pipeline_404(client, admin_headers, monkeypatch):
    monkeypatch.setattr("app.api.ingest.INGEST_EXECUTOR", "worker")
    assert (
        client.post("/api/pipelines/no-such/runs", headers=admin_headers).status_code
        == 404
    )


def test_worker_mode_bad_preconditions_422_creates_no_run(
    client, admin_headers, monkeypatch
):
    monkeypatch.setattr("app.api.ingest.INGEST_EXECUTOR", "worker")
    pid = client.post(
        "/api/pipelines", json={"name": "no-dataset"}, headers=admin_headers
    ).json()["id"]
    r = client.post(f"/api/pipelines/{pid}/runs", headers=admin_headers)
    assert r.status_code == 422
    runs = [
        x
        for x in client.get("/api/runs", headers=admin_headers).json()
        if x["pipeline_id"] == pid
    ]
    assert runs == []  # validation failed BEFORE any run row exists
