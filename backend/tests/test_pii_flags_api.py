"""PiiFlag API CRUD tests (real Postgres)."""


def test_pii_flag_list_unauthenticated_returns_401(client):
    assert client.get("/api/pii-flags").status_code == 401


def test_pii_flag_create_requires_name(client, admin_headers):
    r = client.post("/api/pii-flags", json={}, headers=admin_headers)
    assert r.status_code in (400, 422)


def test_pii_flag_create_non_admin_returns_403(client, user_headers):
    assert (
        client.post(
            "/api/pii-flags", json={"name": "x"}, headers=user_headers
        ).status_code
        == 403
    )


def test_pii_flag_update_non_admin_returns_403(client, user_headers):
    assert (
        client.put(
            "/api/pii-flags/nope", json={"name": "x"}, headers=user_headers
        ).status_code
        == 403
    )


def test_pii_flag_delete_non_admin_returns_403(client, user_headers):
    assert client.delete("/api/pii-flags/nope", headers=user_headers).status_code == 403


def test_pii_flags_crud(client, admin_headers, user_headers):
    """Full create -> read -> update(PUT) -> list -> delete round-trip; every field persists."""
    r = client.post(
        "/api/pii-flags",
        json={
            "name": "v1",
            "category": "direct_identifier",
            "detection_tier": "schema",
            "status": "flagged",
            "confidence": 9.5,
            "rationale": "v1",
            "fingerprint": "v1",
        },
        headers=admin_headers,
    )
    assert r.status_code == 201
    created = r.json()
    entity_id = created["id"]
    assert created["name"] == "v1"
    assert created["category"] == "direct_identifier"
    assert created["detection_tier"] == "schema"
    assert created["status"] == "flagged"
    assert created["confidence"] == 9.5
    assert created["rationale"] == "v1"
    assert created["fingerprint"] == "v1"
    got = client.get(f"/api/pii-flags/{entity_id}", headers=user_headers)
    assert got.status_code == 200 and got.json()["id"] == entity_id
    upd = client.put(
        f"/api/pii-flags/{entity_id}",
        json={"name": "n2", "category": "contact"},
        headers=admin_headers,
    )
    assert upd.status_code == 200
    updated = upd.json()
    assert updated["name"] == "n2" and updated["category"] == "contact"
    listing = client.get("/api/pii-flags", headers=user_headers)
    assert any(x["id"] == entity_id for x in listing.json())
    dele = client.delete(f"/api/pii-flags/{entity_id}", headers=admin_headers)
    assert dele.status_code == 204
    assert (
        client.get(f"/api/pii-flags/{entity_id}", headers=admin_headers).status_code
        == 404
    )


def test_pii_flag_out_of_enum_category_rejected(client, admin_headers):
    """category is CHECK-constrained — an out-of-enum value must not persist."""
    r = client.post(
        "/api/pii-flags",
        json={"name": "bad-enum", "category": "invalid-value"},
        headers=admin_headers,
    )
    assert r.status_code >= 400
    listing = client.get("/api/pii-flags", headers=admin_headers)
    assert all(x.get("category") != "invalid-value" for x in listing.json())


def test_pii_flag_out_of_enum_detection_tier_rejected(client, admin_headers):
    """detection_tier is CHECK-constrained — an out-of-enum value must not persist."""
    r = client.post(
        "/api/pii-flags",
        json={"name": "bad-enum", "detection_tier": "invalid-value"},
        headers=admin_headers,
    )
    assert r.status_code >= 400
    listing = client.get("/api/pii-flags", headers=admin_headers)
    assert all(x.get("detection_tier") != "invalid-value" for x in listing.json())


def test_pii_flag_out_of_enum_status_rejected(client, admin_headers):
    """status is CHECK-constrained — an out-of-enum value must not persist."""
    r = client.post(
        "/api/pii-flags",
        json={"name": "bad-enum", "status": "invalid-value"},
        headers=admin_headers,
    )
    assert r.status_code >= 400
    listing = client.get("/api/pii-flags", headers=admin_headers)
    assert all(x.get("status") != "invalid-value" for x in listing.json())
