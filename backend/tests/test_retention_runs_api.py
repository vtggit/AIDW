"""RetentionRun API CRUD tests (real Postgres)."""


def test_retention_run_list_unauthenticated_returns_401(client):
    assert client.get("/api/retention-runs").status_code == 401


def test_retention_run_create_requires_name(client, admin_headers):
    r = client.post("/api/retention-runs", json={}, headers=admin_headers)
    assert r.status_code in (400, 422)


def test_retention_run_create_non_admin_returns_403(client, user_headers):
    assert (
        client.post(
            "/api/retention-runs", json={"name": "x"}, headers=user_headers
        ).status_code
        == 403
    )


def test_retention_run_update_non_admin_returns_403(client, user_headers):
    assert (
        client.put(
            "/api/retention-runs/nope", json={"name": "x"}, headers=user_headers
        ).status_code
        == 403
    )


def test_retention_run_delete_non_admin_returns_403(client, user_headers):
    assert (
        client.delete("/api/retention-runs/nope", headers=user_headers).status_code
        == 403
    )


def test_retention_runs_crud(client, admin_headers, user_headers):
    """Full create -> read -> update(PUT) -> list -> delete round-trip; every field persists."""
    r = client.post(
        "/api/retention-runs",
        json={"name": "v1", "status": "pending", "trigger": "manual"},
        headers=admin_headers,
    )
    assert r.status_code == 201
    created = r.json()
    entity_id = created["id"]
    assert created["name"] == "v1"
    assert created["status"] == "pending"
    assert created["trigger"] == "manual"
    got = client.get(f"/api/retention-runs/{entity_id}", headers=user_headers)
    assert got.status_code == 200 and got.json()["id"] == entity_id
    upd = client.put(
        f"/api/retention-runs/{entity_id}",
        json={"name": "n2", "status": "running"},
        headers=admin_headers,
    )
    assert upd.status_code == 200
    updated = upd.json()
    assert updated["name"] == "n2" and updated["status"] == "running"
    listing = client.get("/api/retention-runs", headers=user_headers)
    assert any(x["id"] == entity_id for x in listing.json())
    dele = client.delete(f"/api/retention-runs/{entity_id}", headers=admin_headers)
    assert dele.status_code == 204
    assert (
        client.get(
            f"/api/retention-runs/{entity_id}", headers=admin_headers
        ).status_code
        == 404
    )


def test_retention_run_out_of_enum_status_rejected(client, admin_headers):
    """status is CHECK-constrained — an out-of-enum value must not persist."""
    r = client.post(
        "/api/retention-runs",
        json={"name": "bad-enum", "status": "invalid-value"},
        headers=admin_headers,
    )
    assert r.status_code >= 400
    listing = client.get("/api/retention-runs", headers=admin_headers)
    assert all(x.get("status") != "invalid-value" for x in listing.json())


def test_retention_run_out_of_enum_trigger_rejected(client, admin_headers):
    """trigger is CHECK-constrained — an out-of-enum value must not persist."""
    r = client.post(
        "/api/retention-runs",
        json={"name": "bad-enum", "trigger": "invalid-value"},
        headers=admin_headers,
    )
    assert r.status_code >= 400
    listing = client.get("/api/retention-runs", headers=admin_headers)
    assert all(x.get("trigger") != "invalid-value" for x in listing.json())
