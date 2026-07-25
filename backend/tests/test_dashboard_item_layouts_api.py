"""DashboardItemLayout API CRUD tests (real Postgres)."""


def test_dashboard_item_layout_list_unauthenticated_returns_401(client):
    assert client.get("/api/dashboard-item-layouts").status_code == 401


def test_dashboard_item_layout_create_requires_name(client, admin_headers):
    r = client.post("/api/dashboard-item-layouts", json={}, headers=admin_headers)
    assert r.status_code in (400, 422)


def test_dashboard_item_layout_create_non_admin_returns_403(client, user_headers):
    assert (
        client.post(
            "/api/dashboard-item-layouts", json={"name": "x"}, headers=user_headers
        ).status_code
        == 403
    )


def test_dashboard_item_layout_update_non_admin_returns_403(client, user_headers):
    assert (
        client.put(
            "/api/dashboard-item-layouts/nope", json={"name": "x"}, headers=user_headers
        ).status_code
        == 403
    )


def test_dashboard_item_layout_delete_non_admin_returns_403(client, user_headers):
    assert (
        client.delete(
            "/api/dashboard-item-layouts/nope", headers=user_headers
        ).status_code
        == 403
    )


def test_dashboard_item_layouts_crud(client, admin_headers, user_headers):
    """Full create -> read -> update(PUT) -> list -> delete round-trip; every field persists."""
    r = client.post(
        "/api/dashboard-item-layouts",
        json={"name": "v1", "user_id": "v1", "dashboard_item_id": "v1"},
        headers=admin_headers,
    )
    assert r.status_code == 201
    created = r.json()
    entity_id = created["id"]
    assert created["name"] == "v1"
    assert created["user_id"] == "v1"
    assert created["dashboard_item_id"] == "v1"
    got = client.get(f"/api/dashboard-item-layouts/{entity_id}", headers=user_headers)
    assert got.status_code == 200 and got.json()["id"] == entity_id
    upd = client.put(
        f"/api/dashboard-item-layouts/{entity_id}",
        json={"name": "n2", "user_id": "v2"},
        headers=admin_headers,
    )
    assert upd.status_code == 200
    updated = upd.json()
    assert updated["name"] == "n2" and updated["user_id"] == "v2"
    listing = client.get("/api/dashboard-item-layouts", headers=user_headers)
    assert any(x["id"] == entity_id for x in listing.json())
    dele = client.delete(
        f"/api/dashboard-item-layouts/{entity_id}", headers=admin_headers
    )
    assert dele.status_code == 204
    assert (
        client.get(
            f"/api/dashboard-item-layouts/{entity_id}", headers=admin_headers
        ).status_code
        == 404
    )
