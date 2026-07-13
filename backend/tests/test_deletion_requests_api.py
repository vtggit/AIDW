"""DeletionRequest API CRUD tests (real Postgres)."""


def test_deletion_request_list_unauthenticated_returns_401(client):
    assert client.get("/api/deletion-requests").status_code == 401


def test_deletion_request_create_requires_name(client, admin_headers):
    r = client.post("/api/deletion-requests", json={}, headers=admin_headers)
    assert r.status_code in (400, 422)


def test_deletion_request_create_non_admin_returns_403(client, user_headers):
    assert (
        client.post(
            "/api/deletion-requests", json={"name": "x"}, headers=user_headers
        ).status_code
        == 403
    )


def test_deletion_request_update_non_admin_returns_403(client, user_headers):
    assert (
        client.put(
            "/api/deletion-requests/nope", json={"name": "x"}, headers=user_headers
        ).status_code
        == 403
    )


def test_deletion_request_delete_non_admin_returns_403(client, user_headers):
    assert (
        client.delete("/api/deletion-requests/nope", headers=user_headers).status_code
        == 403
    )


def test_deletion_requests_crud(client, admin_headers, user_headers):
    """Full create -> read -> update(PUT) -> list -> delete round-trip; every field persists."""
    r = client.post(
        "/api/deletion-requests",
        json={
            "name": "v1",
            "subject_key": "v1",
            "subject_key_hash": "v1",
            "status": "received",
            "reason": "v1",
            "error_detail": "v1",
            "attempts": 7,
            "records_deleted": 7,
            "profiles_cleared": 7,
            "verified_by": "v1",
            "verified_at": "v1",
            "completed_at": "v1",
        },
        headers=admin_headers,
    )
    assert r.status_code == 201
    created = r.json()
    entity_id = created["id"]
    assert created["name"] == "v1"
    assert created["subject_key"] == "v1"
    assert created["subject_key_hash"] == "v1"
    assert created["status"] == "received"
    assert created["reason"] == "v1"
    assert created["error_detail"] == "v1"
    assert created["attempts"] == 7
    assert created["records_deleted"] == 7
    assert created["profiles_cleared"] == 7
    assert created["verified_by"] == "v1"
    assert created["verified_at"] == "v1"
    assert created["completed_at"] == "v1"
    # reads are ADMIN-ONLY since the lifecycle slice: subject_key is PII (#76)
    denied = client.get(f"/api/deletion-requests/{entity_id}", headers=user_headers)
    assert denied.status_code == 403
    got = client.get(f"/api/deletion-requests/{entity_id}", headers=admin_headers)
    assert got.status_code == 200 and got.json()["id"] == entity_id
    upd = client.put(
        f"/api/deletion-requests/{entity_id}",
        json={"name": "n2", "subject_key": "v2"},
        headers=admin_headers,
    )
    assert upd.status_code == 200
    updated = upd.json()
    assert updated["name"] == "n2" and updated["subject_key"] == "v2"
    assert client.get("/api/deletion-requests", headers=user_headers).status_code == 403
    listing = client.get("/api/deletion-requests", headers=admin_headers)
    assert any(x["id"] == entity_id for x in listing.json())
    dele = client.delete(f"/api/deletion-requests/{entity_id}", headers=admin_headers)
    assert dele.status_code == 204
    assert (
        client.get(
            f"/api/deletion-requests/{entity_id}", headers=admin_headers
        ).status_code
        == 404
    )


def test_deletion_request_out_of_enum_status_rejected(client, admin_headers):
    """status is CHECK-constrained — an out-of-enum value must not persist."""
    r = client.post(
        "/api/deletion-requests",
        json={"name": "bad-enum", "status": "invalid-value"},
        headers=admin_headers,
    )
    assert r.status_code >= 400
    listing = client.get("/api/deletion-requests", headers=admin_headers)
    assert all(x.get("status") != "invalid-value" for x in listing.json())
