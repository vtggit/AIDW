"""Ingest suppression filter (RTBF #76): re-ingest must not resurrect an erased subject.

Unit level: apply_rows skips suppressed keys (never stored), still advances the watermark
past them, counts them, needs the pepper ONLY when suppression entries exist, and fails
loudly (never resurrects silently) when entries exist but the pepper is missing.
End to end: ingest -> erase -> re-ingest the same page; the subject stays gone and the run
reports rows_suppressed."""

import uuid

import pytest

from tests.test_worker import (
    _arm_worker_mode,
    _discovered_pipeline,
    _drain_queue,
)

PEPPER = "ingest-fixture-pepper"


def _seed_run_row():
    from app.db.connection import get_cursor

    rid = uuid.uuid4().hex
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO runs (id, name, status) VALUES (%s, 'suppr-run', 'running')",
            (rid,),
        )
    return rid


def _mk_dataset(client, admin_headers):
    r = client.post(
        "/api/datasets",
        json={"name": f"suppr-{uuid.uuid4().hex[:8]}"},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _suppress(ds, key):
    from app.db.connection import get_cursor
    from app.governance.hashing import subject_key_hash

    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO suppression_entries (id, name, key_hash, dataset_id) "
            "VALUES (%s, 'suppr', %s, %s) ON CONFLICT (key_hash) DO NOTHING",
            (uuid.uuid4().hex, subject_key_hash(ds, key), ds),
        )


def _oplog_keys(ds):
    from app.db.connection import get_cursor

    with get_cursor() as cur:
        cur.execute(
            "SELECT business_key FROM ingested_records WHERE dataset_id = %s", (ds,)
        )
        return {r["business_key"] for r in cur.fetchall()}


def test_apply_rows_skips_suppressed_but_advances_watermark(
    client, admin_headers, monkeypatch
):
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", PEPPER)
    from app.db.connection import get_cursor
    from app.ingest.cursor import apply_rows

    ds = _mk_dataset(client, admin_headers)
    run = _seed_run_row()
    _suppress(ds, "gone")
    rows = [
        {"K": "kept", "TS": "2026-01-01T00:00:00Z"},
        {"K": "gone", "TS": "2026-01-03T00:00:00Z"},  # suppressed AND the latest cursor
    ]
    with get_cursor() as cur:
        result = apply_rows(cur, run, ds, rows, ["K"], "TS", None, "timestamp")

    assert result["rows_suppressed"] == 1
    assert result["rows_written"] == 1
    assert _oplog_keys(ds) == {"kept"}  # the suppressed key was never stored
    # the suppressed row still advanced the watermark — a tail suppression cannot
    # stall the cursor into refetching the same page forever
    assert result["new_watermark"] == "2026-01-03T00:00:00Z"


def test_no_pepper_needed_when_nothing_is_suppressed(
    client, admin_headers, monkeypatch
):
    monkeypatch.delenv("AIDW_SUPPRESSION_PEPPER", raising=False)
    from app.db.connection import get_cursor
    from app.ingest.cursor import apply_rows

    ds = _mk_dataset(client, admin_headers)
    run = _seed_run_row()
    with get_cursor() as cur:
        result = apply_rows(cur, run, ds, [{"K": "plain"}], ["K"])
    assert result["rows_written"] == 1 and result["rows_suppressed"] == 0


def test_missing_pepper_with_suppressions_fails_loudly(
    client, admin_headers, monkeypatch
):
    # entries exist but the pepper is gone: the run must FAIL, never silently resurrect
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", PEPPER)
    ds = _mk_dataset(client, admin_headers)
    _suppress(ds, "gone")
    monkeypatch.delenv("AIDW_SUPPRESSION_PEPPER")

    from app.db.connection import get_cursor
    from app.ingest.cursor import apply_rows

    run = _seed_run_row()
    with (
        pytest.raises(RuntimeError, match="AIDW_SUPPRESSION_PEPPER"),
        get_cursor() as cur,
    ):
        apply_rows(cur, run, ds, [{"K": "gone"}], ["K"])
    assert _oplog_keys(ds) == set()


def test_erase_then_reingest_does_not_resurrect(client, admin_headers, monkeypatch):
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", PEPPER)
    monkeypatch.setattr("app.config.INGEST_EXECUTOR", "worker")
    from app.worker.loop import deletions_once, run_once

    pid, did = _discovered_pipeline(client, admin_headers, monkeypatch)
    _arm_worker_mode(monkeypatch)
    _drain_queue()

    # ingest run 1: all ten mock orders land (business_key = OrderID)
    client.post(f"/api/pipelines/{pid}/runs", headers=admin_headers)
    assert run_once() is not None
    assert "3" in _oplog_keys(did)

    # erase OrderID 3 through the real pipeline: request -> verify -> worker executes
    rid = client.post(
        "/api/deletion-requests",
        json={
            "name": "erase order 3",
            "subject_key": "3",
            "dataset_id": did,
            "status": "received",
        },
        headers=admin_headers,
    ).json()["id"]
    assert (
        client.post(
            f"/api/deletion-requests/{rid}/verify", headers=admin_headers
        ).status_code
        == 200
    )
    assert deletions_once() is True
    assert "3" not in _oplog_keys(did)

    # ingest run 2, the SAME fixture page: the subject must NOT reappear
    run2 = client.post(f"/api/pipelines/{pid}/runs", headers=admin_headers).json()["id"]
    assert run_once() is not None
    assert "3" not in _oplog_keys(did)  # suppression held
    body = client.get(f"/api/runs/{run2}", headers=admin_headers).json()
    assert body["rows_suppressed"] == 1  # observable on the run
    assert body["status"] == "succeeded"
