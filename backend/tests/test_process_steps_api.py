"""ProcessStep API CRUD tests (real Postgres)."""


def test_process_step_list_unauthenticated_returns_401(client):
    assert client.get("/api/process-steps").status_code == 401


def test_process_step_create_requires_name(client, admin_headers):
    r = client.post("/api/process-steps", json={}, headers=admin_headers)
    assert r.status_code in (400, 422)


def test_process_step_create_non_admin_returns_403(client, user_headers):
    assert (
        client.post(
            "/api/process-steps", json={"name": "x"}, headers=user_headers
        ).status_code
        == 403
    )


def test_process_step_update_non_admin_returns_403(client, user_headers):
    assert (
        client.put(
            "/api/process-steps/nope", json={"name": "x"}, headers=user_headers
        ).status_code
        == 403
    )


def test_process_step_delete_non_admin_returns_403(client, user_headers):
    assert (
        client.delete("/api/process-steps/nope", headers=user_headers).status_code
        == 403
    )


def test_process_steps_crud(client, admin_headers, user_headers):
    """Full create -> read -> update(PUT) -> list -> delete round-trip; every field persists."""
    r = client.post(
        "/api/process-steps",
        json={
            "name": "v1",
            "step_key": "v1",
            "ordinal": 7,
            "step_type": "v1",
            "service_impl": "v1",
            "candidate_groups": "v1",
            "form_key": "v1",
            "timer_duration": 7,
        },
        headers=admin_headers,
    )
    assert r.status_code == 201
    created = r.json()
    entity_id = created["id"]
    assert created["name"] == "v1"
    assert created["step_key"] == "v1"
    assert created["ordinal"] == 7
    assert created["step_type"] == "v1"
    assert created["service_impl"] == "v1"
    assert created["candidate_groups"] == "v1"
    assert created["form_key"] == "v1"
    assert created["timer_duration"] == 7
    got = client.get(f"/api/process-steps/{entity_id}", headers=user_headers)
    assert got.status_code == 200 and got.json()["id"] == entity_id
    upd = client.put(
        f"/api/process-steps/{entity_id}",
        json={"name": "n2", "step_key": "v2"},
        headers=admin_headers,
    )
    assert upd.status_code == 200
    updated = upd.json()
    assert updated["name"] == "n2" and updated["step_key"] == "v2"
    listing = client.get("/api/process-steps", headers=user_headers)
    assert any(x["id"] == entity_id for x in listing.json())
    dele = client.delete(f"/api/process-steps/{entity_id}", headers=admin_headers)
    assert dele.status_code == 204
    assert (
        client.get(f"/api/process-steps/{entity_id}", headers=admin_headers).status_code
        == 404
    )
