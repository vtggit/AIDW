"""OdataServiceConfig API CRUD tests (real Postgres)."""


def test_odata_service_config_list_unauthenticated_returns_401(client):
    assert client.get("/api/odata-service-configs").status_code == 401


def test_odata_service_config_create_requires_name(client, admin_headers):
    r = client.post("/api/odata-service-configs", json={}, headers=admin_headers)
    assert r.status_code in (400, 422)


def test_odata_service_config_create_non_admin_returns_403(client, user_headers):
    assert (
        client.post(
            "/api/odata-service-configs", json={"name": "x"}, headers=user_headers
        ).status_code
        == 403
    )


def test_odata_service_config_update_non_admin_returns_403(client, user_headers):
    assert (
        client.put(
            "/api/odata-service-configs/nope", json={"name": "x"}, headers=user_headers
        ).status_code
        == 403
    )


def test_odata_service_config_delete_non_admin_returns_403(client, user_headers):
    assert (
        client.delete(
            "/api/odata-service-configs/nope", headers=user_headers
        ).status_code
        == 403
    )


def test_odata_service_configs_crud(client, admin_headers, user_headers):
    """Full create -> read -> update(PUT) -> list -> delete round-trip; every field persists."""
    r = client.post(
        "/api/odata-service-configs",
        json={"name": "v1", "metadata_path": "v1", "default_entity_set": "v1"},
        headers=admin_headers,
    )
    assert r.status_code == 201
    created = r.json()
    entity_id = created["id"]
    assert created["name"] == "v1"
    assert created["metadata_path"] == "v1"
    assert created["default_entity_set"] == "v1"
    got = client.get(f"/api/odata-service-configs/{entity_id}", headers=user_headers)
    assert got.status_code == 200 and got.json()["id"] == entity_id
    upd = client.put(
        f"/api/odata-service-configs/{entity_id}",
        json={"name": "n2", "metadata_path": "v2"},
        headers=admin_headers,
    )
    assert upd.status_code == 200
    updated = upd.json()
    assert updated["name"] == "n2" and updated["metadata_path"] == "v2"
    listing = client.get("/api/odata-service-configs", headers=user_headers)
    assert any(x["id"] == entity_id for x in listing.json())
    dele = client.delete(
        f"/api/odata-service-configs/{entity_id}", headers=admin_headers
    )
    assert dele.status_code == 204
    assert (
        client.get(
            f"/api/odata-service-configs/{entity_id}", headers=admin_headers
        ).status_code
        == 404
    )
