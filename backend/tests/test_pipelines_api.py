"""Pipeline API CRUD tests (real Postgres)."""


def test_pipeline_list_unauthenticated_returns_401(client):
    assert client.get("/api/pipelines").status_code == 401


def test_pipeline_create_requires_name(client, admin_headers):
    r = client.post("/api/pipelines", json={}, headers=admin_headers)
    assert r.status_code in (400, 422)


def test_pipeline_create_non_admin_returns_403(client, user_headers):
    assert (
        client.post(
            "/api/pipelines", json={"name": "x"}, headers=user_headers
        ).status_code
        == 403
    )


def test_pipeline_bad_dataset_fk_returns_422(client, admin_headers):
    r = client.post(
        "/api/pipelines",
        json={"name": "p", "dataset_id": "no-such-dataset"},
        headers=admin_headers,
    )
    assert r.status_code == 422


def test_pipeline_out_of_enum_cdc_pattern_returns_422(client, admin_headers):
    r = client.post(
        "/api/pipelines",
        json={"name": "p", "cdc_pattern": "carrier-pigeon"},
        headers=admin_headers,
    )
    assert r.status_code == 422


def test_pipelines_crud(client, admin_headers, user_headers):
    """Full create -> read -> update(PUT) -> list -> delete round-trip; every field persists.
    cdc_pattern omitted on create proves the NULL-passing CHECK convention."""
    r = client.post(
        "/api/pipelines",
        json={"name": "orders", "schedule": "0 * * * *", "is_enabled": True},
        headers=admin_headers,
    )
    assert r.status_code == 201
    created = r.json()
    entity_id = created["id"]
    assert created["name"] == "orders"
    assert created["schedule"] == "0 * * * *"
    assert created["is_enabled"] is True
    got = client.get(f"/api/pipelines/{entity_id}", headers=user_headers)
    assert got.status_code == 200 and got.json()["id"] == entity_id
    upd = client.put(
        f"/api/pipelines/{entity_id}",
        json={"name": "orders2", "cdc_pattern": "cursor", "is_enabled": False},
        headers=admin_headers,
    )
    assert upd.status_code == 200
    updated = upd.json()
    assert updated["name"] == "orders2"
    assert updated["cdc_pattern"] == "cursor"
    assert updated["is_enabled"] is False
    listing = client.get("/api/pipelines", headers=user_headers)
    assert any(x["id"] == entity_id for x in listing.json())
    dele = client.delete(f"/api/pipelines/{entity_id}", headers=admin_headers)
    assert dele.status_code == 204
    assert (
        client.get(f"/api/pipelines/{entity_id}", headers=admin_headers).status_code
        == 404
    )
