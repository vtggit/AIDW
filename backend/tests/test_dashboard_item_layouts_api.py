"""DashboardItemLayout API CRUD tests (real Postgres).

Updated for scoped-write model: every operation is gated on the authenticated
caller's own rows.  user_id is derived from the token subject, never from the
request payload.
"""


def test_dashboard_item_layout_list_unauthenticated_returns_401(client):
    assert client.get("/api/dashboard-item-layouts").status_code == 401


def test_dashboard_item_layout_create_requires_name(client, user_headers):
    r = client.post("/api/dashboard-item-layouts", json={}, headers=user_headers)
    assert r.status_code in (400, 422)


def test_dashboard_item_layout_create_authenticated_succeeds(client, user_headers):
    """Any authenticated user can create their own layout."""
    r = client.post(
        "/api/dashboard-item-layouts",
        json={"name": "my layout"},
        headers=user_headers,
    )
    assert r.status_code == 201


def test_dashboard_item_layout_update_non_owner_returns_404(client, user_headers):
    """Updating a row not owned by the caller is refused."""
    assert (
        client.put(
            "/api/dashboard-item-layouts/nope", json={"name": "x"}, headers=user_headers
        ).status_code
        == 404
    )


def test_dashboard_item_layout_delete_non_owner_returns_404(client, user_headers):
    """Deleting a row not owned by the caller is refused."""
    assert (
        client.delete(
            "/api/dashboard-item-layouts/nope", headers=user_headers
        ).status_code
        == 404
    )


def test_dashboard_item_layouts_crud(client, admin_headers, user_headers):
    """Full create -> read -> update(PUT) -> list -> delete round-trip; every field persists.

    user_id is derived from the token subject — it must not be supplied in the
    request body and cannot be changed by the caller.
    """
    # Create as admin — user_id comes from token, not payload
    r = client.post(
        "/api/dashboard-item-layouts",
        json={"name": "v1", "dashboard_item_id": "v1"},
        headers=admin_headers,
    )
    assert r.status_code == 201
    created = r.json()
    entity_id = created["id"]
    assert created["name"] == "v1"
    # user_id is populated from the token subject
    assert created["user_id"] is not None
    assert created["dashboard_item_id"] == "v1"

    # Admin can read their own layout
    got = client.get(f"/api/dashboard-item-layouts/{entity_id}", headers=admin_headers)
    assert got.status_code == 200 and got.json()["id"] == entity_id

    # A different user cannot see the admin's layout (scoped to caller)
    cross_got = client.get(
        f"/api/dashboard-item-layouts/{entity_id}", headers=user_headers
    )
    assert cross_got.status_code == 404

    # Admin can update their own layout
    upd = client.put(
        f"/api/dashboard-item-layouts/{entity_id}",
        json={"name": "n2"},
        headers=admin_headers,
    )
    assert upd.status_code == 200
    updated = upd.json()
    assert updated["name"] == "n2"

    # Listing returns only the caller's rows
    admin_listing = client.get("/api/dashboard-item-layouts", headers=admin_headers)
    assert any(item_record["id"] == entity_id for item_record in admin_listing.json())

    user_listing = client.get("/api/dashboard-item-layouts", headers=user_headers)
    assert not any(
        item_record["id"] == entity_id for item_record in user_listing.json()
    )

    # Admin can delete their own layout
    dele = client.delete(
        f"/api/dashboard-item-layouts/{entity_id}", headers=admin_headers
    )
    assert dele.status_code == 204

    # Verify deleted
    assert (
        client.get(
            f"/api/dashboard-item-layouts/{entity_id}", headers=admin_headers
        ).status_code
        == 404
    )
