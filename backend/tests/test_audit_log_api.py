"""AuditLog API CRUD tests (real Postgres)."""


def test_audit_log_list_unauthenticated_returns_401(client):
    assert client.get("/api/audit-logs").status_code == 401


def test_audit_log_create_requires_name(client, admin_headers):
    r = client.post("/api/audit-logs", json={}, headers=admin_headers)
    assert r.status_code in (400, 422)


def test_audit_log_create_non_admin_returns_403(client, user_headers):
    assert (
        client.post(
            "/api/audit-logs", json={"name": "x"}, headers=user_headers
        ).status_code
        == 403
    )


def test_audit_log_update_non_admin_returns_403(client, user_headers):
    assert (
        client.put(
            "/api/audit-logs/nope", json={"name": "x"}, headers=user_headers
        ).status_code
        == 403
    )


def test_audit_log_delete_non_admin_returns_403(client, user_headers):
    assert (
        client.delete("/api/audit-logs/nope", headers=user_headers).status_code == 403
    )


def test_audit_log_crud(client, admin_headers, user_headers):
    """Full create -> read -> update(PUT) -> list -> delete round-trip; every field persists."""
    r = client.post(
        "/api/audit-logs",
        json={
            "name": "v1",
            "actor": "v1",
            "entity_type": "v1",
            "entity_id": "v1",
            "detail": "v1",
            "action": "create",
        },
        headers=admin_headers,
    )
    assert r.status_code == 201
    created = r.json()
    entity_id = created["id"]
    assert created["name"] == "v1"
    assert created["actor"] == "v1"
    assert created["entity_type"] == "v1"
    assert created["entity_id"] == "v1"
    assert created["detail"] == "v1"
    assert created["action"] == "create"
    got = client.get(f"/api/audit-logs/{entity_id}", headers=user_headers)
    assert got.status_code == 200 and got.json()["id"] == entity_id
    upd = client.put(
        f"/api/audit-logs/{entity_id}",
        json={"name": "n2", "actor": "v2"},
        headers=admin_headers,
    )
    assert upd.status_code == 200
    updated = upd.json()
    assert updated["name"] == "n2" and updated["actor"] == "v2"
    listing = client.get("/api/audit-logs", headers=user_headers)
    assert any(x["id"] == entity_id for x in listing.json())
    dele = client.delete(f"/api/audit-logs/{entity_id}", headers=admin_headers)
    assert dele.status_code == 204
    assert (
        client.get(f"/api/audit-logs/{entity_id}", headers=admin_headers).status_code
        == 404
    )


def test_audit_log_out_of_enum_action_rejected(client, admin_headers):
    """action is CHECK-constrained — an out-of-enum value must not persist."""
    r = client.post(
        "/api/audit-logs",
        json={"name": "bad-enum", "action": "invalid-value"},
        headers=admin_headers,
    )
    assert r.status_code >= 400
    listing = client.get("/api/audit-logs", headers=admin_headers)
    assert all(x.get("action") != "invalid-value" for x in listing.json())
