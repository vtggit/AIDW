"""Field-flow test — process_definition_id (FK -> process_definitions) round-trips through the sequence_flows API."""


def test_sequence_flows_process_definition_id_round_trips(client, admin_headers):
    parent = client.post(
        "/api/process-definitions", json={"name": "FK Parent"}, headers=admin_headers
    )
    assert parent.status_code == 201, parent.text
    parent_id = parent.json()["id"]
    body = {"name": "test"}
    body["process_definition_id"] = parent_id
    created = client.post("/api/sequence-flows", json=body, headers=admin_headers)
    assert created.status_code == 201, created.text
    _id = created.json()["id"]
    listing = client.get("/api/sequence-flows", headers=admin_headers)
    assert listing.status_code == 200, listing.text
    row = next((r for r in listing.json() if r.get("id") == _id), None)
    assert row is not None, "created record not found in list"
    assert row.get("process_definition_id") == parent_id
    bogus = {"name": "test"}
    bogus["process_definition_id"] = "no-such-parent-id"
    rejected = client.post("/api/sequence-flows", json=bogus, headers=admin_headers)
    assert rejected.status_code >= 400, "FK constraint not enforced: " + rejected.text
