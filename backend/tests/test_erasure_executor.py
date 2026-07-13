"""Erasure executor (RTBF #76) — OBSERVABLE OUTPUT STATE, per the design's reward-hack guard.

Every assertion is against what actually persisted: op-log rows gone (and only the subject's),
profile values NULL, suppression row present with the right hash, proof-of-erasure audit row
written (never carrying the raw key), request finalized with subject_key NULLed. Plus the
all-or-nothing rollback (a mid-transaction failure leaves EVERYTHING untouched) and the
retry path that the no-'failed'-state design promises."""

import uuid

import pytest

PEPPER = "executor-fixture-pepper"


def _seed_dataset(client, admin_headers):
    r = client.post(
        "/api/datasets",
        json={"name": f"rtbf-ds-{uuid.uuid4().hex[:8]}"},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _seed_world(client, admin_headers, subject="subject-1"):
    """A dataset with op-log rows for two subjects and one profiled field."""
    from app.db.connection import get_cursor

    ds = _seed_dataset(client, admin_headers)
    with get_cursor() as cur:
        # one row per subject: (dataset_id, business_key) is the op-log idempotency unique
        for key in (subject, "bystander-1"):
            cur.execute(
                "INSERT INTO ingested_records (id, name, dataset_id, business_key, op) "
                "VALUES (%s, %s, %s, %s, 'insert')",
                (uuid.uuid4().hex, f"rec:{key}", ds, key),
            )
        fid = uuid.uuid4().hex
        cur.execute(
            "INSERT INTO discovered_fields (id, name, dataset_id) VALUES (%s, %s, %s)",
            (fid, "email", ds),
        )
        cur.execute(
            "INSERT INTO field_profiles (id, name, discovered_field_id, min_value, "
            "max_value, most_common_value) VALUES (%s, %s, %s, %s, %s, %s)",
            (
                uuid.uuid4().hex,
                "email profile",
                fid,
                "a@x.io",
                "z@x.io",
                "subject-1@x.io",
            ),
        )
    return ds


def _seed_request(ds, subject="subject-1", status="verifying", verified_by="admin-a"):
    from app.db.connection import get_cursor

    rid = uuid.uuid4().hex
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO deletion_requests (id, name, subject_key, status, dataset_id, "
            "attempts, verified_by) VALUES (%s, %s, %s, %s, %s, 0, %s)",
            (rid, f"erase {subject}", subject, status, ds, verified_by),
        )
    return rid


def _row(table, rid):
    from app.db.connection import get_cursor

    with get_cursor() as cur:
        cur.execute(f"SELECT * FROM {table} WHERE id = %s", (rid,))  # noqa: S608
        return cur.fetchone()


def _count_oplog(ds, key):
    from app.db.connection import get_cursor

    with get_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS n FROM ingested_records "
            "WHERE dataset_id = %s AND business_key = %s",
            (ds, key),
        )
        return cur.fetchone()["n"]


def test_erasure_end_to_end(client, admin_headers, monkeypatch):
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", PEPPER)
    from app.db.connection import get_cursor
    from app.governance.executor import execute_deletion
    from app.governance.hashing import subject_key_hash

    ds = _seed_world(client, admin_headers)
    rid = _seed_request(ds)

    assert execute_deletion(rid) is True

    # the subject's rows are GONE; the bystander's row survives
    assert _count_oplog(ds, "subject-1") == 0
    assert _count_oplog(ds, "bystander-1") == 1

    # every profile value of the dataset is NULLed (counts stay elsewhere by design)
    with get_cursor() as cur:
        cur.execute(
            "SELECT fp.min_value, fp.max_value, fp.most_common_value FROM field_profiles fp "
            "JOIN discovered_fields df ON fp.discovered_field_id = df.id "
            "WHERE df.dataset_id = %s",
            (ds,),
        )
        prof = cur.fetchone()
    assert prof == {"min_value": None, "max_value": None, "most_common_value": None}

    # the suppression entry exists with exactly the module's hash
    expected_hash = subject_key_hash(ds, "subject-1")
    with get_cursor() as cur:
        cur.execute(
            "SELECT dataset_id, deletion_request_id FROM suppression_entries "
            "WHERE key_hash = %s",
            (expected_hash,),
        )
        sup = cur.fetchone()
    assert sup == {"dataset_id": ds, "deletion_request_id": rid}

    # proof-of-erasure audit row: actor = verifier, counts + hash, NEVER the raw key
    with get_cursor() as cur:
        cur.execute(
            "SELECT actor, action, detail FROM audit_logs "
            "WHERE entity_type = 'erasure' AND entity_id = %s",
            (rid,),
        )
        audit = cur.fetchone()
    assert audit["actor"] == "admin-a" and audit["action"] == "delete"
    assert "records_deleted=1" in audit["detail"]
    assert "profiles_cleared=1" in audit["detail"]
    assert expected_hash in audit["detail"]
    assert "subject-1" not in audit["detail"]

    # finalized: completed, counts, timestamp, and the identifier is GONE from the request
    req = _row("deletion_requests", rid)
    assert req["status"] == "completed"
    assert req["records_deleted"] == 1 and req["profiles_cleared"] == 1
    assert req["completed_at"] and req["subject_key"] is None


def test_failure_rolls_back_everything_and_requeues(client, admin_headers, monkeypatch):
    # no pepper -> the hash step fails INSIDE the erasure transaction: nothing may persist
    monkeypatch.delenv("AIDW_SUPPRESSION_PEPPER", raising=False)
    from app.governance.executor import execute_deletion

    ds = _seed_world(client, admin_headers)
    rid = _seed_request(ds)

    assert execute_deletion(rid) is False

    # all-or-nothing: the op-log row is UNTOUCHED
    assert _count_oplog(ds, "subject-1") == 1
    # retry-not-fail: back to the claimable state with the cause recorded
    req = _row("deletion_requests", rid)
    assert req["status"] == "verifying"
    assert req["attempts"] == 1
    assert "AIDW_SUPPRESSION_PEPPER" in req["error_detail"]
    assert req["subject_key"] == "subject-1"  # identifier retained until success

    # the retry path: provide the pepper, run again, it completes
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", PEPPER)
    assert execute_deletion(rid) is True
    assert _count_oplog(ds, "subject-1") == 0
    assert _row("deletion_requests", rid)["status"] == "completed"


def test_only_verifying_requests_are_claimable(client, admin_headers, monkeypatch):
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", PEPPER)
    from app.governance.executor import execute_deletion

    ds = _seed_world(client, admin_headers)
    for state in ("received", "completed", "rejected"):
        rid = _seed_request(ds, status=state)
        assert execute_deletion(rid) is False
        assert _row("deletion_requests", rid)["status"] == state  # untouched


def test_completed_request_is_not_reexecutable(client, admin_headers, monkeypatch):
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", PEPPER)
    from app.governance.executor import execute_deletion

    ds = _seed_world(client, admin_headers)
    rid = _seed_request(ds)
    assert execute_deletion(rid) is True
    # the identifier is gone; a re-claim must fail closed rather than hash NULL
    assert execute_deletion(rid) is False
    assert _row("deletion_requests", rid)["status"] == "completed"


def test_late_failure_rolls_back_all_earlier_steps(client, admin_headers, monkeypatch):
    # the all-or-nothing proof at the LATEST possible point: DELETE, profile NULLing, and
    # the suppression insert have all executed when the audit write blows up — every one of
    # them must vanish with the rollback (this is also the same-cursor audit property: an
    # audit row on its own transaction would NOT drag the erasure down with it)
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", PEPPER)
    import app.governance.executor as executor_mod
    from app.db.connection import get_cursor
    from app.governance.executor import execute_deletion
    from app.governance.hashing import subject_key_hash

    ds = _seed_world(client, admin_headers)
    rid = _seed_request(ds)

    def _boom(*a, **k):
        raise RuntimeError("audit backend down")

    monkeypatch.setattr(executor_mod, "record_audit", _boom)
    assert execute_deletion(rid) is False

    assert _count_oplog(ds, "subject-1") == 1  # DELETE rolled back
    with get_cursor() as cur:
        cur.execute(
            "SELECT fp.most_common_value FROM field_profiles fp "
            "JOIN discovered_fields df ON fp.discovered_field_id = df.id "
            "WHERE df.dataset_id = %s",
            (ds,),
        )
        assert (
            cur.fetchone()["most_common_value"] == "subject-1@x.io"
        )  # NULLing rolled back
        cur.execute(
            "SELECT COUNT(*) AS n FROM suppression_entries WHERE key_hash = %s",
            (subject_key_hash(ds, "subject-1"),),
        )
        assert cur.fetchone()["n"] == 0  # suppression insert rolled back
        cur.execute("SELECT COUNT(*) AS n FROM audit_logs WHERE entity_id = %s", (rid,))
        assert cur.fetchone()["n"] == 0  # and no audit row either
    req = _row("deletion_requests", rid)
    assert req["status"] == "verifying" and req["attempts"] == 1

    monkeypatch.undo()  # restores record_audit AND the env; re-set the pepper for the retry
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", PEPPER)
    assert (
        execute_deletion(rid) is True
    )  # retry completes once the audit backend is back


def test_delete_and_profiles_are_scoped_to_the_dataset(
    client, admin_headers, monkeypatch
):
    # a bystander DATASET with the same business_key and its own profile must be untouched
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", PEPPER)
    from app.db.connection import get_cursor
    from app.governance.executor import execute_deletion

    ds = _seed_world(client, admin_headers)
    other = _seed_world(client, admin_headers)  # same subject key, different dataset
    rid = _seed_request(ds)

    assert execute_deletion(rid) is True
    assert _count_oplog(ds, "subject-1") == 0
    assert _count_oplog(other, "subject-1") == 1  # same key, other dataset: SURVIVES
    with get_cursor() as cur:
        cur.execute(
            "SELECT fp.most_common_value FROM field_profiles fp "
            "JOIN discovered_fields df ON fp.discovered_field_id = df.id "
            "WHERE df.dataset_id = %s",
            (other,),
        )
        assert cur.fetchone()["most_common_value"] == "subject-1@x.io"  # SURVIVES


def test_suppression_conflict_keeps_the_first_owner(client, admin_headers, monkeypatch):
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", PEPPER)
    import uuid as _uuid

    from app.db.connection import get_cursor
    from app.governance.executor import execute_deletion
    from app.governance.hashing import subject_key_hash

    ds = _seed_world(client, admin_headers)
    rid = _seed_request(ds)
    earlier = _seed_request(ds, status="completed")  # a real earlier request row (FK)
    key_hash = subject_key_hash(ds, "subject-1")
    with get_cursor() as cur:  # the earlier request already suppressed this key
        cur.execute(
            "INSERT INTO suppression_entries (id, name, key_hash, deletion_request_id) "
            "VALUES (%s, %s, %s, %s)",
            (_uuid.uuid4().hex, "pre-existing", key_hash, earlier),
        )

    assert execute_deletion(rid) is True  # ON CONFLICT DO NOTHING — still completes
    with get_cursor() as cur:
        cur.execute(
            "SELECT deletion_request_id FROM suppression_entries WHERE key_hash = %s",
            (key_hash,),
        )
        rows = cur.fetchall()
    assert len(rows) == 1  # exactly one entry per hash
    assert rows[0]["deletion_request_id"] == earlier  # first owner kept


def test_worker_claimed_path(client, admin_headers, monkeypatch):
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", PEPPER)
    from app.governance.executor import claim_for_execution, execute_deletion

    ds = _seed_world(client, admin_headers)
    rid = _seed_request(ds)
    generation = claim_for_execution(rid)  # the worker's claim
    assert generation == 0
    assert claim_for_execution(rid) is None  # second claim loses
    assert execute_deletion(rid, claimed=True, generation=generation) is True
    assert _row("deletion_requests", rid)["status"] == "completed"


def test_stale_generation_cannot_touch_a_reclaimed_row(
    client, admin_headers, monkeypatch
):
    # the BEHAVIORAL-ARCHITECTURE fence: a zombie claimant whose row was reaped and
    # re-claimed must be unable to erase, finalize, or reset the newer claim
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", PEPPER)
    from app.db.connection import get_cursor
    from app.governance.executor import claim_for_execution, execute_deletion

    ds = _seed_world(client, admin_headers)
    rid = _seed_request(ds)

    zombie_gen = claim_for_execution(rid)  # worker A claims at generation 0
    with get_cursor() as cur:  # the reaper rescues the stalled row
        cur.execute(
            "UPDATE deletion_requests SET status = 'verifying', attempts = attempts + 1 "
            "WHERE id = %s",
            (rid,),
        )
    live_gen = claim_for_execution(rid)  # worker B re-claims at generation 1
    assert live_gen == 1

    # the zombie wakes: its generation no longer matches — nothing happens
    assert execute_deletion(rid, claimed=True, generation=zombie_gen) is False
    req = _row("deletion_requests", rid)
    assert req["status"] == "executing" and req["attempts"] == 1  # B's claim INTACT
    assert _count_oplog(ds, "subject-1") == 1  # and nothing was erased

    # B finishes normally on its own generation
    assert execute_deletion(rid, claimed=True, generation=live_gen) is True
    assert _row("deletion_requests", rid)["status"] == "completed"
