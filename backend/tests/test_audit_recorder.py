"""Audit recorder (governance #79) — same-transaction semantics are the whole point.

The commit case, the ROLLBACK case (an audit row must never survive a failed write), and the
fail-closed action guard (rejected BEFORE any write reaches the cursor)."""

import uuid

import pytest


def _count(entity_id):
    from app.db.connection import get_cursor

    with get_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS n FROM audit_logs WHERE entity_id = %s", (entity_id,)
        )
        return cur.fetchone()["n"]


def test_record_audit_commits_with_the_callers_transaction(client, admin_headers):
    from app.audit.recorder import record_audit
    from app.db.connection import get_cursor

    eid = f"ent-{uuid.uuid4().hex[:8]}"
    with get_cursor() as cur:
        audit_id = record_audit(
            cur, "tester", "create", "widget", eid, detail="made it"
        )
    assert _count(eid) == 1
    # visible through the audit_log API too (the lane-built CRUD)
    listing = client.get("/api/audit-logs", headers=admin_headers)
    row = next(r for r in listing.json() if r["id"] == audit_id)
    assert row["actor"] == "tester" and row["action"] == "create"
    assert row["entity_type"] == "widget" and row["entity_id"] == eid
    assert row["name"] == "create widget"


def test_record_audit_rolls_back_with_a_failed_write(client, admin_headers):
    from app.audit.recorder import record_audit
    from app.db.connection import get_cursor

    eid = f"ent-{uuid.uuid4().hex[:8]}"
    with pytest.raises(RuntimeError):
        with get_cursor() as cur:
            record_audit(cur, "tester", "delete", "widget", eid)
            raise RuntimeError("the audited write failed after the audit insert")
    # same transaction: the audit row must NOT have survived the rollback
    assert _count(eid) == 0


def test_record_audit_rejects_unknown_action_before_any_write(client, admin_headers):
    from app.audit.recorder import record_audit
    from app.db.connection import get_cursor

    eid = f"ent-{uuid.uuid4().hex[:8]}"
    with get_cursor() as cur:
        with pytest.raises(ValueError):
            record_audit(cur, "tester", "purge", "widget", eid)
    assert _count(eid) == 0
