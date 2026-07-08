"""Field-flow test — first_seen_run_id (FK -> discovery_runs) round-trips through the discovered_fields API."""


def test_discovered_fields_first_seen_run_id_round_trips(client, admin_headers):
    parent = client.post(
        "/api/discovery-runs", json={"name": "FK Parent"}, headers=admin_headers
    )
    assert parent.status_code == 201, parent.text
    parent_id = parent.json()["id"]
    body = {"name": "test"}
    body["first_seen_run_id"] = parent_id
    created = client.post("/api/discovered-fields", json=body, headers=admin_headers)
    assert created.status_code == 201, created.text
    _id = created.json()["id"]
    listing = client.get("/api/discovered-fields", headers=admin_headers)
    assert listing.status_code == 200, listing.text
    row = next((r for r in listing.json() if r.get("id") == _id), None)
    assert row is not None, "created record not found in list"
    assert row.get("first_seen_run_id") == parent_id
    bogus = {"name": "test"}
    bogus["first_seen_run_id"] = "no-such-parent-id"
    rejected = client.post("/api/discovered-fields", json=bogus, headers=admin_headers)
    assert rejected.status_code >= 400, "FK constraint not enforced: " + rejected.text
