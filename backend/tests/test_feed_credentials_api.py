"""FeedCredential API CRUD tests (real Postgres)."""


def test_feed_credential_list_unauthenticated_returns_401(client):
    assert client.get("/api/feed-credentials").status_code == 401


def test_feed_credential_create_requires_name(client, admin_headers):
    r = client.post("/api/feed-credentials", json={}, headers=admin_headers)
    assert r.status_code in (400, 422)


def test_feed_credential_create_non_admin_returns_403(client, user_headers):
    assert (
        client.post(
            "/api/feed-credentials", json={"name": "x"}, headers=user_headers
        ).status_code
        == 403
    )


def test_feed_credential_update_non_admin_returns_403(client, user_headers):
    assert (
        client.put(
            "/api/feed-credentials/nope", json={"name": "x"}, headers=user_headers
        ).status_code
        == 403
    )


def test_feed_credential_delete_non_admin_returns_403(client, user_headers):
    assert (
        client.delete("/api/feed-credentials/nope", headers=user_headers).status_code
        == 403
    )


def test_feed_credentials_crud(client, admin_headers, user_headers):
    """Full create -> read -> update(PUT) -> list -> delete round-trip; every field persists."""
    r = client.post(
        "/api/feed-credentials",
        json={
            "name": "v1",
            "principal": "v1",
            "key_hash": "v1",
            "key_prefix": "v1",
            "revoked": True,
        },
        headers=admin_headers,
    )
    assert r.status_code == 201
    created = r.json()
    entity_id = created["id"]
    assert created["name"] == "v1"
    assert created["principal"] == "v1"
    assert created["key_hash"] == "v1"
    assert created["key_prefix"] == "v1"
    assert created["revoked"] is True
    got = client.get(f"/api/feed-credentials/{entity_id}", headers=user_headers)
    assert got.status_code == 200 and got.json()["id"] == entity_id
    upd = client.put(
        f"/api/feed-credentials/{entity_id}",
        json={"name": "n2", "principal": "v2"},
        headers=admin_headers,
    )
    assert upd.status_code == 200
    updated = upd.json()
    assert updated["name"] == "n2" and updated["principal"] == "v2"
    listing = client.get("/api/feed-credentials", headers=user_headers)
    assert any(x["id"] == entity_id for x in listing.json())
    dele = client.delete(f"/api/feed-credentials/{entity_id}", headers=admin_headers)
    assert dele.status_code == 204
    assert (
        client.get(
            f"/api/feed-credentials/{entity_id}", headers=admin_headers
        ).status_code
        == 404
    )
