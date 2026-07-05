"""Dataset API CRUD tests (real Postgres)."""


def test_dataset_list_unauthenticated_returns_401(client):
    assert client.get("/api/datasets").status_code == 401


def test_dataset_create_requires_name(client, admin_headers):
    r = client.post("/api/datasets", json={}, headers=admin_headers)
    assert r.status_code in (400, 422)


def test_dataset_create_non_admin_returns_403(client, user_headers):
    assert (
        client.post(
            "/api/datasets", json={"name": "x"}, headers=user_headers
        ).status_code
        == 403
    )


def test_dataset_update_non_admin_returns_403(client, user_headers):
    assert (
        client.put(
            "/api/datasets/nope", json={"name": "x"}, headers=user_headers
        ).status_code
        == 403
    )


def test_dataset_delete_non_admin_returns_403(client, user_headers):
    assert client.delete("/api/datasets/nope", headers=user_headers).status_code == 403


def test_datasets_crud(client, admin_headers, user_headers):
    """Full create -> read -> update(PUT) -> list -> delete round-trip; every field persists."""
    r = client.post(
        "/api/datasets", json={"name": "v1", "object_type": "v1"}, headers=admin_headers
    )
    assert r.status_code == 201
    created = r.json()
    entity_id = created["id"]
    assert created["name"] == "v1"
    assert created["object_type"] == "v1"
    got = client.get(f"/api/datasets/{entity_id}", headers=user_headers)
    assert got.status_code == 200 and got.json()["id"] == entity_id
    upd = client.put(
        f"/api/datasets/{entity_id}",
        json={"name": "n2", "object_type": "v2"},
        headers=admin_headers,
    )
    assert upd.status_code == 200
    updated = upd.json()
    assert updated["name"] == "n2" and updated["object_type"] == "v2"
    listing = client.get("/api/datasets", headers=user_headers)
    assert any(x["id"] == entity_id for x in listing.json())
    dele = client.delete(f"/api/datasets/{entity_id}", headers=admin_headers)
    assert dele.status_code == 204
    assert (
        client.get(f"/api/datasets/{entity_id}", headers=admin_headers).status_code
        == 404
    )
