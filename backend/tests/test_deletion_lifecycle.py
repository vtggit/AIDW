"""Deletion-request lifecycle (RTBF #76): verify/reject transitions, admin-only reads,
inline synchronous execution.

Observable state throughout: statuses, verified_by/verified_at/subject_key_hash columns,
audit rows, and — for the inline path — the op-log actually emptied."""

import uuid

import pytest

PEPPER = "lifecycle-fixture-pepper"


def _mk_dataset(client, admin_headers):
    r = client.post(
        "/api/datasets",
        json={"name": f"rtbf-lc-{uuid.uuid4().hex[:8]}"},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _mk_request(client, admin_headers, ds, subject="subject-lc", **extra):
    r = client.post(
        "/api/deletion-requests",
        json={
            "name": f"erase {subject}",
            "subject_key": subject,
            "dataset_id": ds,
            "status": "received",
            **extra,
        },
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _audit_rows(rid):
    from app.db.connection import get_cursor

    with get_cursor() as cur:
        cur.execute(
            "SELECT actor, action, detail FROM audit_logs "
            "WHERE entity_type = 'deletion_requests' AND entity_id = %s",
            (rid,),
        )
        return cur.fetchall()


def test_verify_transitions_records_and_audits(client, admin_headers, monkeypatch):
    monkeypatch.setattr("app.config.INGEST_EXECUTOR", "worker")  # pure transition
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", PEPPER)
    from app.governance.hashing import subject_key_hash

    ds = _mk_dataset(client, admin_headers)
    rid = _mk_request(client, admin_headers, ds)

    resp = client.post(f"/api/deletion-requests/{rid}/verify", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "verifying"  # verified-and-queued: THE claimable state
    assert body["verified_by"] and body["verified_at"]
    assert body["subject_key_hash"] == subject_key_hash(ds, "subject-lc")

    audits = _audit_rows(rid)
    assert [a["detail"] for a in audits] == ["verify: received -> verifying"]
    assert audits[0]["action"] == "update" and audits[0]["actor"]


def test_verify_is_status_guarded(client, admin_headers, monkeypatch):
    monkeypatch.setattr("app.config.INGEST_EXECUTOR", "worker")
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", PEPPER)

    ds = _mk_dataset(client, admin_headers)
    rid = _mk_request(client, admin_headers, ds)
    assert (
        client.post(
            f"/api/deletion-requests/{rid}/verify", headers=admin_headers
        ).status_code
        == 200
    )
    # verifying is not 'received' — the second verify 409s
    second = client.post(f"/api/deletion-requests/{rid}/verify", headers=admin_headers)
    assert second.status_code == 409, second.text
    # unknown id 404s
    missing = client.post(
        "/api/deletion-requests/no-such-id/verify", headers=admin_headers
    )
    assert missing.status_code == 404


def test_verify_requires_dataset_and_subject(client, admin_headers, monkeypatch):
    monkeypatch.setattr("app.config.INGEST_EXECUTOR", "worker")
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", PEPPER)

    r = client.post(
        "/api/deletion-requests",
        json={"name": "no dataset", "subject_key": "x", "status": "received"},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    resp = client.post(f"/api/deletion-requests/{rid}/verify", headers=admin_headers)
    assert resp.status_code == 409
    assert "dataset_id" in resp.json()["detail"]


def test_reject_paths_and_terminal_states_win(client, admin_headers, monkeypatch):
    monkeypatch.setattr("app.config.INGEST_EXECUTOR", "worker")
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", PEPPER)

    ds = _mk_dataset(client, admin_headers)
    # reject straight from received
    r1 = _mk_request(client, admin_headers, ds, subject="rej-a")
    resp = client.post(f"/api/deletion-requests/{r1}/reject", headers=admin_headers)
    assert resp.status_code == 200 and resp.json()["status"] == "rejected"
    assert any("reject: received" in a["detail"] for a in _audit_rows(r1))

    # reject from verifying (verified, then withdrawn)
    r2 = _mk_request(client, admin_headers, ds, subject="rej-b")
    client.post(f"/api/deletion-requests/{r2}/verify", headers=admin_headers)
    resp = client.post(f"/api/deletion-requests/{r2}/reject", headers=admin_headers)
    assert resp.status_code == 200 and resp.json()["status"] == "rejected"

    # terminal states win: rejecting a rejected request 409s
    resp = client.post(f"/api/deletion-requests/{r1}/reject", headers=admin_headers)
    assert resp.status_code == 409


def test_reads_are_admin_only(client, admin_headers, user_headers):
    # subject_key is PII: the read-only user role gets 403 on list AND detail
    ds = _mk_dataset(client, admin_headers)
    rid = _mk_request(client, admin_headers, ds, subject="pii-read")
    assert client.get("/api/deletion-requests", headers=user_headers).status_code == 403
    assert (
        client.get(f"/api/deletion-requests/{rid}", headers=user_headers).status_code
        == 403
    )
    # admin still reads
    assert (
        client.get("/api/deletion-requests", headers=admin_headers).status_code == 200
    )


def test_inline_verify_executes_synchronously(client, admin_headers, monkeypatch):
    monkeypatch.setattr("app.config.INGEST_EXECUTOR", "inline")
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", PEPPER)
    from app.db.connection import get_cursor

    ds = _mk_dataset(client, admin_headers)
    with get_cursor() as cur:  # one op-log row for the subject
        cur.execute(
            "INSERT INTO ingested_records (id, name, dataset_id, business_key, op) "
            "VALUES (%s, %s, %s, %s, 'insert')",
            (uuid.uuid4().hex, "rec:inline-subj", ds, "inline-subj"),
        )
    rid = _mk_request(client, admin_headers, ds, subject="inline-subj")

    resp = client.post(f"/api/deletion-requests/{rid}/verify", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # the whole pipeline ran inside the request: verified AND erased
    assert body["status"] == "completed"
    assert body["records_deleted"] == 1
    assert body["subject_key"] is None  # the identifier is gone
    with get_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS n FROM ingested_records "
            "WHERE dataset_id = %s AND business_key = 'inline-subj'",
            (ds,),
        )
        assert cur.fetchone()["n"] == 0
