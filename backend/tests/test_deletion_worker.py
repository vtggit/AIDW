"""Worker second claim spine + reaper for deletion requests (RTBF #76).

The SKIP LOCKED exclusivity proof runs on two live connections, exactly like the runs spine's;
the reaper proof shows a dead executor's row is RETRIED (verifying, attempts+1), never
corrupted or terminally failed — erasure is idempotent, so retry-not-fail is safe."""

import uuid

import psycopg2

from app.db.connection import get_connection_params, get_cursor
from app.worker.loop import (
    DELETION_MAX_ATTEMPTS,
    claim_next_deletion,
    deletions_once,
    reap_stale_executing,
)

PEPPER = "worker-fixture-pepper"


def _drain_deletions():
    while claim_next_deletion() is not None:
        pass  # park everything pre-existing in 'executing' so it cannot interfere


def _mk_dataset(client, admin_headers):
    r = client.post(
        "/api/datasets",
        json={"name": f"rtbf-w-{uuid.uuid4().hex[:8]}"},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _mk_verified_request(ds, subject, attempts=0):
    rid = uuid.uuid4().hex
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO deletion_requests (id, name, subject_key, status, dataset_id, "
            "attempts, verified_by) VALUES (%s, %s, %s, 'verifying', %s, %s, 'admin-w')",
            (rid, f"erase {subject}", subject, ds, attempts),
        )
    return rid


def _status(rid):
    with get_cursor() as cur:
        cur.execute(
            "SELECT status, attempts, error_detail FROM deletion_requests WHERE id = %s",
            (rid,),
        )
        return cur.fetchone()


def test_skip_locked_deletion_claim_skips_locked_rows(client, admin_headers):
    _drain_deletions()
    ds = _mk_dataset(client, admin_headers)
    rid = _mk_verified_request(ds, "locked-subj")

    blocker = psycopg2.connect(**get_connection_params())
    try:
        with blocker.cursor() as cur:
            cur.execute(
                "SELECT id FROM deletion_requests WHERE id = %s FOR UPDATE", (rid,)
            )
        assert claim_next_deletion() is None  # locked -> skipped, not blocked
    finally:
        blocker.rollback()
        blocker.close()

    claimed = claim_next_deletion()
    assert claimed == (rid, 0)  # id AND the generation the fence needs
    assert _status(rid)["status"] == "executing"
    assert claim_next_deletion() is None  # claimed exactly once


def test_attempts_cap_leaves_requests_for_triage(client, admin_headers):
    _drain_deletions()
    ds = _mk_dataset(client, admin_headers)
    _mk_verified_request(ds, "tired-subj", attempts=DELETION_MAX_ATTEMPTS)
    assert claim_next_deletion() is None  # at the cap: operator triage owns it


def test_deletions_once_executes_end_to_end(client, admin_headers, monkeypatch):
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", PEPPER)
    _drain_deletions()
    ds = _mk_dataset(client, admin_headers)
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO ingested_records (id, name, dataset_id, business_key, op) "
            "VALUES (%s, %s, %s, %s, 'insert')",
            (uuid.uuid4().hex, "rec:w-subj", ds, "w-subj"),
        )
    with get_cursor() as cur:
        # the landing store (#258) carries the payload — erasure must purge it too
        cur.execute(
            "INSERT INTO ingested_payloads (id, name, dataset_id, business_key, payload, "
            "ingested_at) VALUES (%s, %s, %s, %s, %s, NOW())",
            (uuid.uuid4().hex, "pay:w-subj", ds, "w-subj", "{}"),
        )
    rid = _mk_verified_request(ds, "w-subj")

    assert deletions_once() is True
    row = _status(rid)
    assert row["status"] == "completed"
    with get_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS n FROM ingested_records "
            "WHERE dataset_id = %s AND business_key = 'w-subj'",
            (ds,),
        )
        assert cur.fetchone()["n"] == 0  # the worker path really erases
        cur.execute(
            "SELECT COUNT(*) AS n FROM ingested_payloads "
            "WHERE dataset_id = %s AND business_key = %s",
            (ds, "w-subj"),
        )
        assert cur.fetchone()["n"] == 0  # the landed payload is purged too
    assert deletions_once() is False  # queue drained


def test_reaper_retries_not_fails(client, admin_headers):
    _drain_deletions()
    ds = _mk_dataset(client, admin_headers)
    rid = _mk_verified_request(ds, "stale-subj")
    claimed = claim_next_deletion()
    assert claimed is not None and claimed[0] == rid  # a worker died holding this claim

    # count is >=1, not ==1: the drain helper parks strays in 'executing' and a zero cutoff
    # reaps those too — the assertions that matter are row-scoped
    assert reap_stale_executing(max_age_seconds=0) >= 1
    row = _status(rid)
    assert row["status"] == "verifying"  # RETRIED, not terminally failed
    assert row["attempts"] == 1
    assert "reaped" in row["error_detail"]
    # and it is claimable again, at the bumped generation (reaped strays may come first)
    claimed = []
    while (c := claim_next_deletion()) is not None:
        claimed.append(c)
        if c[0] == rid:
            break
    assert (rid, 1) in claimed


def test_reaper_leaves_fresh_claims_alone(client, admin_headers):
    _drain_deletions()
    ds = _mk_dataset(client, admin_headers)
    rid = _mk_verified_request(ds, "fresh-subj")
    assert claim_next_deletion() is not None
    assert reap_stale_executing(max_age_seconds=3600) == 0  # fresh: untouched
    assert _status(rid)["status"] == "executing"
