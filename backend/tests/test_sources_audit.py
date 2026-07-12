"""Audit-hook test — sources mutations write the audit trail (same transaction)."""

import uuid


def test_sources_mutations_are_audited(client, admin_headers):
    created = client.post(
        "/api/sources",
        json={"name": f"audited-{uuid.uuid4().hex[:8]}"},
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    eid = created.json()["id"]
    upd = client.put(
        f"/api/sources/{eid}",
        json={"name": f"renamed-{uuid.uuid4().hex[:8]}"},
        headers=admin_headers,
    )
    assert upd.status_code == 200, upd.text
    dele = client.delete(f"/api/sources/{eid}", headers=admin_headers)
    assert dele.status_code == 204, dele.text
    listing = client.get("/api/audit-logs", headers=admin_headers)
    rows = [r for r in listing.json() if r["entity_id"] == eid]
    assert sorted(r["action"] for r in rows) == ["create", "delete", "update"]
    assert all(r["entity_type"] == "sources" and r["actor"] for r in rows)
