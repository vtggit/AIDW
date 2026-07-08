"""IngestedRecord API CRUD tests (real Postgres)."""


def test_ingested_record_list_unauthenticated_returns_401(client):
    assert client.get("/api/ingested-records").status_code == 401


def test_ingested_record_create_requires_name(client, admin_headers):
    r = client.post("/api/ingested-records", json={}, headers=admin_headers)
    assert r.status_code in (400, 422)


def test_ingested_record_create_non_admin_returns_403(client, user_headers):
    assert (
        client.post(
            "/api/ingested-records", json={"name": "x"}, headers=user_headers
        ).status_code
        == 403
    )


def test_ingested_record_bad_run_fk_returns_422(client, admin_headers):
    r = client.post(
        "/api/ingested-records",
        json={"name": "r", "run_id": "no-such-run"},
        headers=admin_headers,
    )
    assert r.status_code == 422


def test_ingested_record_out_of_enum_op_returns_422(client, admin_headers):
    r = client.post(
        "/api/ingested-records",
        json={"name": "r", "op": "teleport"},
        headers=admin_headers,
    )
    assert r.status_code == 422


def test_ingested_record_duplicate_key_returns_409(client, admin_headers):
    """UNIQUE(dataset_id, business_key) — the idempotent-replay guarantee."""
    did = client.post(
        "/api/datasets", json={"name": "ds-dup"}, headers=admin_headers
    ).json()["id"]
    first = client.post(
        "/api/ingested-records",
        json={"name": "r1", "dataset_id": did, "business_key": "42", "op": "insert"},
        headers=admin_headers,
    )
    assert first.status_code == 201
    second = client.post(
        "/api/ingested-records",
        json={"name": "r2", "dataset_id": did, "business_key": "42", "op": "insert"},
        headers=admin_headers,
    )
    assert second.status_code == 409


def test_ingested_records_crud(client, admin_headers, user_headers):
    """Full create -> read -> update(PUT) -> list -> delete round-trip; every field persists."""
    r = client.post(
        "/api/ingested-records",
        json={
            "name": "rec:7",
            "business_key": "7",
            "op": "insert",
            "ingested_at": "2026-07-07T00:00:00+00:00",
        },
        headers=admin_headers,
    )
    assert r.status_code == 201
    created = r.json()
    entity_id = created["id"]
    assert created["business_key"] == "7" and created["op"] == "insert"
    assert created["ingested_at"].startswith("2026-07-07T00:00:00")
    got = client.get(f"/api/ingested-records/{entity_id}", headers=user_headers)
    assert got.status_code == 200 and got.json()["id"] == entity_id
    upd = client.put(
        f"/api/ingested-records/{entity_id}",
        json={"op": "delete"},
        headers=admin_headers,
    )
    assert upd.status_code == 200 and upd.json()["op"] == "delete"
    listing = client.get("/api/ingested-records", headers=user_headers)
    assert any(x["id"] == entity_id for x in listing.json())
    dele = client.delete(f"/api/ingested-records/{entity_id}", headers=admin_headers)
    assert dele.status_code == 204
    assert (
        client.get(
            f"/api/ingested-records/{entity_id}", headers=admin_headers
        ).status_code
        == 404
    )
