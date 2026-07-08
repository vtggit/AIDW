"""DeltaCursor API CRUD tests (real Postgres)."""


def test_delta_cursor_list_unauthenticated_returns_401(client):
    assert client.get("/api/delta-cursors").status_code == 401


def test_delta_cursor_create_requires_name(client, admin_headers):
    r = client.post("/api/delta-cursors", json={}, headers=admin_headers)
    assert r.status_code in (400, 422)


def test_delta_cursor_create_non_admin_returns_403(client, user_headers):
    assert (
        client.post(
            "/api/delta-cursors", json={"name": "x"}, headers=user_headers
        ).status_code
        == 403
    )


def test_delta_cursor_bad_pipeline_fk_returns_422(client, admin_headers):
    r = client.post(
        "/api/delta-cursors",
        json={"name": "c", "pipeline_id": "no-such-pipeline"},
        headers=admin_headers,
    )
    assert r.status_code == 422


def test_delta_cursor_out_of_enum_kind_returns_422(client, admin_headers):
    r = client.post(
        "/api/delta-cursors",
        json={"name": "c", "cursor_kind": "vibes"},
        headers=admin_headers,
    )
    assert r.status_code == 422


def test_delta_cursor_duplicate_pipeline_returns_409(client, admin_headers):
    """UNIQUE(pipeline_id) — one live cursor per pipeline."""
    pid = client.post(
        "/api/pipelines", json={"name": "p-dup"}, headers=admin_headers
    ).json()["id"]
    first = client.post(
        "/api/delta-cursors",
        json={"name": "c1", "pipeline_id": pid},
        headers=admin_headers,
    )
    assert first.status_code == 201
    second = client.post(
        "/api/delta-cursors",
        json={"name": "c2", "pipeline_id": pid},
        headers=admin_headers,
    )
    assert second.status_code == 409


def test_delta_cursors_crud(client, admin_headers, user_headers):
    """Full create -> read -> update(PUT) -> list -> delete round-trip; every field persists."""
    r = client.post(
        "/api/delta-cursors",
        json={"name": "orders-cursor", "cursor_kind": "timestamp"},
        headers=admin_headers,
    )
    assert r.status_code == 201
    created = r.json()
    entity_id = created["id"]
    assert created["cursor_kind"] == "timestamp"
    assert created["cursor_value"] is None
    got = client.get(f"/api/delta-cursors/{entity_id}", headers=user_headers)
    assert got.status_code == 200 and got.json()["id"] == entity_id
    upd = client.put(
        f"/api/delta-cursors/{entity_id}",
        json={"cursor_value": "2026-01-01T00:00:00Z", "cursor_kind": "string"},
        headers=admin_headers,
    )
    assert upd.status_code == 200
    updated = upd.json()
    assert updated["cursor_value"] == "2026-01-01T00:00:00Z"
    assert updated["cursor_kind"] == "string"
    listing = client.get("/api/delta-cursors", headers=user_headers)
    assert any(x["id"] == entity_id for x in listing.json())
    dele = client.delete(f"/api/delta-cursors/{entity_id}", headers=admin_headers)
    assert dele.status_code == 204
    assert (
        client.get(f"/api/delta-cursors/{entity_id}", headers=admin_headers).status_code
        == 404
    )
