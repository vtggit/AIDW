"""RetentionPolicy API CRUD tests (real Postgres)."""


def test_retention_policy_list_unauthenticated_returns_401(client):
    assert client.get("/api/retention-policies").status_code == 401


def test_retention_policy_create_requires_name(client, admin_headers):
    r = client.post("/api/retention-policies", json={}, headers=admin_headers)
    assert r.status_code in (400, 422)


def test_retention_policy_create_non_admin_returns_403(client, user_headers):
    assert (
        client.post(
            "/api/retention-policies", json={"name": "x"}, headers=user_headers
        ).status_code
        == 403
    )


def test_retention_policy_update_non_admin_returns_403(client, user_headers):
    assert (
        client.put(
            "/api/retention-policies/nope", json={"name": "x"}, headers=user_headers
        ).status_code
        == 403
    )


def test_retention_policy_delete_non_admin_returns_403(client, user_headers):
    assert (
        client.delete("/api/retention-policies/nope", headers=user_headers).status_code
        == 403
    )


def test_retention_policies_crud(client, admin_headers, user_headers):
    """Full create -> read -> update(PUT) -> list -> delete round-trip; every field persists."""
    r = client.post(
        "/api/retention-policies",
        json={
            "name": "v1",
            "table_class": "connection_tests",
            "action": "purge",
            "scope": "class",
        },
        headers=admin_headers,
    )
    assert r.status_code == 201
    created = r.json()
    entity_id = created["id"]
    assert created["name"] == "v1"
    assert created["table_class"] == "connection_tests"
    assert created["action"] == "purge"
    assert created["scope"] == "class"
    got = client.get(f"/api/retention-policies/{entity_id}", headers=user_headers)
    assert got.status_code == 200 and got.json()["id"] == entity_id
    upd = client.put(
        f"/api/retention-policies/{entity_id}",
        json={"name": "n2", "table_class": "runs"},
        headers=admin_headers,
    )
    assert upd.status_code == 200
    updated = upd.json()
    assert updated["name"] == "n2" and updated["table_class"] == "runs"
    listing = client.get("/api/retention-policies", headers=user_headers)
    assert any(x["id"] == entity_id for x in listing.json())
    dele = client.delete(f"/api/retention-policies/{entity_id}", headers=admin_headers)
    assert dele.status_code == 204
    assert (
        client.get(
            f"/api/retention-policies/{entity_id}", headers=admin_headers
        ).status_code
        == 404
    )


def test_retention_policy_out_of_enum_table_class_rejected(client, admin_headers):
    """table_class is CHECK-constrained — an out-of-enum value must not persist."""
    r = client.post(
        "/api/retention-policies",
        json={"name": "bad-enum", "table_class": "invalid-value"},
        headers=admin_headers,
    )
    assert r.status_code >= 400
    listing = client.get("/api/retention-policies", headers=admin_headers)
    assert all(x.get("table_class") != "invalid-value" for x in listing.json())


def test_retention_policy_out_of_enum_action_rejected(client, admin_headers):
    """action is CHECK-constrained — an out-of-enum value must not persist."""
    r = client.post(
        "/api/retention-policies",
        json={"name": "bad-enum", "action": "invalid-value"},
        headers=admin_headers,
    )
    assert r.status_code >= 400
    listing = client.get("/api/retention-policies", headers=admin_headers)
    assert all(x.get("action") != "invalid-value" for x in listing.json())


def test_retention_policy_out_of_enum_scope_rejected(client, admin_headers):
    """scope is CHECK-constrained — an out-of-enum value must not persist."""
    r = client.post(
        "/api/retention-policies",
        json={"name": "bad-enum", "scope": "invalid-value"},
        headers=admin_headers,
    )
    assert r.status_code >= 400
    listing = client.get("/api/retention-policies", headers=admin_headers)
    assert all(x.get("scope") != "invalid-value" for x in listing.json())
