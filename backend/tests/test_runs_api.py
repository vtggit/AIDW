"""Run API CRUD tests (real Postgres)."""


def test_run_list_unauthenticated_returns_401(client):
    assert client.get("/api/runs").status_code == 401


def test_run_create_requires_name(client, admin_headers):
    r = client.post("/api/runs", json={}, headers=admin_headers)
    assert r.status_code in (400, 422)


def test_run_create_non_admin_returns_403(client, user_headers):
    assert (
        client.post("/api/runs", json={"name": "x"}, headers=user_headers).status_code
        == 403
    )


def test_run_bad_pipeline_fk_returns_422(client, admin_headers):
    r = client.post(
        "/api/runs",
        json={"name": "r", "pipeline_id": "no-such-pipeline"},
        headers=admin_headers,
    )
    assert r.status_code == 422


def test_run_out_of_enum_status_returns_422(client, admin_headers):
    r = client.post(
        "/api/runs", json={"name": "r", "status": "exploded"}, headers=admin_headers
    )
    assert r.status_code == 422


def test_run_out_of_enum_trigger_returns_422(client, admin_headers):
    r = client.post(
        "/api/runs", json={"name": "r", "trigger": "cosmic-ray"}, headers=admin_headers
    )
    assert r.status_code == 422


def test_runs_crud(client, admin_headers, user_headers):
    """Full create -> read -> update(PUT) -> list -> delete round-trip; timestamps and counts
    persist and read back as ISO strings."""
    r = client.post(
        "/api/runs",
        json={
            "name": "nightly",
            "status": "pending",
            "trigger": "scheduled",
            "started_at": "2026-07-07T00:00:00+00:00",
            "rows_read": 10,
            "rows_written": 9,
        },
        headers=admin_headers,
    )
    assert r.status_code == 201
    created = r.json()
    entity_id = created["id"]
    assert created["status"] == "pending" and created["trigger"] == "scheduled"
    assert created["rows_read"] == 10 and created["rows_written"] == 9
    assert created["started_at"].startswith("2026-07-07T00:00:00")
    got = client.get(f"/api/runs/{entity_id}", headers=user_headers)
    assert got.status_code == 200 and got.json()["id"] == entity_id
    upd = client.put(
        f"/api/runs/{entity_id}",
        json={
            "status": "succeeded",
            "finished_at": "2026-07-07T00:05:00+00:00",
            "error_detail": None,
        },
        headers=admin_headers,
    )
    assert upd.status_code == 200
    updated = upd.json()
    assert updated["status"] == "succeeded"
    assert updated["finished_at"].startswith("2026-07-07T00:05:00")
    listing = client.get("/api/runs", headers=user_headers)
    assert any(x["id"] == entity_id for x in listing.json())
    dele = client.delete(f"/api/runs/{entity_id}", headers=admin_headers)
    assert dele.status_code == 204
    assert (
        client.get(f"/api/runs/{entity_id}", headers=admin_headers).status_code == 404
    )
