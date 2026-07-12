"""Audit hooks on retention_policies mutations (governance #79, hook #1).

Every mutating endpoint writes an audit_logs row on the SAME transaction as the write itself —
including the negative proof: a create that the DB rejects (the PR#109 partial-unique) leaves NO
audit row behind."""

import uuid


def _audit_rows(client, admin_headers, entity_id):
    listing = client.get("/api/audit-logs", headers=admin_headers)
    return [r for r in listing.json() if r["entity_id"] == entity_id]


def test_policy_mutations_are_audited(client, admin_headers):
    body = {
        "name": f"audited-{uuid.uuid4().hex[:8]}",
        "table_class": "field_profiles",
        "action": "purge",
        "scope": "class",
        "retention_period_days": 7,
        "is_enabled": False,
    }
    created = client.post("/api/retention-policies", json=body, headers=admin_headers)
    assert created.status_code == 201, created.text
    pid = created.json()["id"]

    rows = _audit_rows(client, admin_headers, pid)
    assert [r["action"] for r in rows] == ["create"]
    assert rows[0]["entity_type"] == "retention_policies"
    assert rows[0]["actor"]  # the authenticated principal, never empty

    upd = client.put(
        f"/api/retention-policies/{pid}",
        json={"retention_period_days": 14},
        headers=admin_headers,
    )
    assert upd.status_code == 200, upd.text
    rows = _audit_rows(client, admin_headers, pid)
    assert sorted(r["action"] for r in rows) == ["create", "update"]
    update_row = next(r for r in rows if r["action"] == "update")
    assert "retention_period_days" in (update_row["detail"] or "")

    dele = client.delete(f"/api/retention-policies/{pid}", headers=admin_headers)
    assert dele.status_code == 204
    rows = _audit_rows(client, admin_headers, pid)
    assert sorted(r["action"] for r in rows) == ["create", "delete", "update"]


def test_rejected_create_leaves_no_audit_row(client, admin_headers):
    # two class-wide policies on the same table_class: the second 409s on the PR#109
    # partial-unique — the SAME-transaction hook means its audit row must vanish with it
    body = {
        "name": f"dup-a-{uuid.uuid4().hex[:8]}",
        "table_class": "field_profiles",
        "action": "purge",
        "scope": "class",
        "retention_period_days": 7,
        "is_enabled": False,
    }
    first = client.post("/api/retention-policies", json=body, headers=admin_headers)
    assert first.status_code == 201, first.text
    pid = first.json()["id"]
    before = len(client.get("/api/audit-logs", headers=admin_headers).json())

    dup = dict(body, name=f"dup-b-{uuid.uuid4().hex[:8]}")
    rejected = client.post("/api/retention-policies", json=dup, headers=admin_headers)
    assert rejected.status_code == 409, rejected.text

    after = len(client.get("/api/audit-logs", headers=admin_headers).json())
    assert after == before  # rolled back WITH the rejected insert
    client.delete(f"/api/retention-policies/{pid}", headers=admin_headers)


def test_dataset_and_pipeline_mutations_are_audited(client, admin_headers):
    # hooks #2 and #3 — the SAME three-layer shape applied to two more entities (the
    # audit-hook recipe's repetition evidence)
    for entity, route in (
        ("datasets", "/api/datasets"),
        ("pipelines", "/api/pipelines"),
    ):
        created = client.post(
            route,
            json={"name": f"audited-{uuid.uuid4().hex[:8]}"},
            headers=admin_headers,
        )
        assert created.status_code == 201, created.text
        eid = created.json()["id"]
        upd = client.put(
            f"{route}/{eid}",
            json={"name": f"renamed-{uuid.uuid4().hex[:8]}"},
            headers=admin_headers,
        )
        assert upd.status_code == 200, upd.text
        dele = client.delete(f"{route}/{eid}", headers=admin_headers)
        assert dele.status_code == 204
        rows = _audit_rows(client, admin_headers, eid)
        assert sorted(r["action"] for r in rows) == ["create", "delete", "update"]
        assert all(r["entity_type"] == entity and r["actor"] for r in rows)


def test_unaudited_paths_write_nothing(client, admin_headers):
    # reads are not audited; a delete of a nonexistent id (no write happened) is not audited
    before = len(client.get("/api/audit-logs", headers=admin_headers).json())
    client.get("/api/retention-policies", headers=admin_headers)
    miss = client.delete("/api/retention-policies/no-such-id", headers=admin_headers)
    assert miss.status_code == 404
    after = len(client.get("/api/audit-logs", headers=admin_headers).json())
    assert after == before
