"""SequenceFlow API CRUD tests (real Postgres)."""


def test_sequence_flow_list_unauthenticated_returns_401(client):
    assert client.get("/api/sequence-flows").status_code == 401


def test_sequence_flow_create_requires_name(client, admin_headers):
    r = client.post("/api/sequence-flows", json={}, headers=admin_headers)
    assert r.status_code in (400, 422)


def test_sequence_flow_create_non_admin_returns_403(client, user_headers):
    assert (
        client.post(
            "/api/sequence-flows", json={"name": "x"}, headers=user_headers
        ).status_code
        == 403
    )


def test_sequence_flow_update_non_admin_returns_403(client, user_headers):
    assert (
        client.put(
            "/api/sequence-flows/nope", json={"name": "x"}, headers=user_headers
        ).status_code
        == 403
    )


def test_sequence_flow_delete_non_admin_returns_403(client, user_headers):
    assert (
        client.delete("/api/sequence-flows/nope", headers=user_headers).status_code
        == 403
    )


def test_sequence_flows_crud(client, admin_headers, user_headers):
    """Full create -> read -> update(PUT) -> list -> delete round-trip; every field persists."""
    r = client.post(
        "/api/sequence-flows",
        json={
            "name": "v1",
            "flow_key": "v1",
            "source_step": "v1",
            "target_step": "v1",
            "condition_expression": "v1",
            "is_default": True,
        },
        headers=admin_headers,
    )
    assert r.status_code == 201
    created = r.json()
    entity_id = created["id"]
    assert created["name"] == "v1"
    assert created["flow_key"] == "v1"
    assert created["source_step"] == "v1"
    assert created["target_step"] == "v1"
    assert created["condition_expression"] == "v1"
    assert created["is_default"] is True
    got = client.get(f"/api/sequence-flows/{entity_id}", headers=user_headers)
    assert got.status_code == 200 and got.json()["id"] == entity_id
    upd = client.put(
        f"/api/sequence-flows/{entity_id}",
        json={"name": "n2", "flow_key": "v2"},
        headers=admin_headers,
    )
    assert upd.status_code == 200
    updated = upd.json()
    assert updated["name"] == "n2" and updated["flow_key"] == "v2"
    listing = client.get("/api/sequence-flows", headers=user_headers)
    assert any(x["id"] == entity_id for x in listing.json())
    dele = client.delete(f"/api/sequence-flows/{entity_id}", headers=admin_headers)
    assert dele.status_code == 204
    assert (
        client.get(
            f"/api/sequence-flows/{entity_id}", headers=admin_headers
        ).status_code
        == 404
    )
