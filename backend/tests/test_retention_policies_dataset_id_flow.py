"""Field-flow test — dataset_id (FK -> datasets) round-trips through the retention_policies API."""


def test_retention_policies_dataset_id_round_trips(client, admin_headers):
    parent = client.post(
        "/api/datasets", json={"name": "FK Parent"}, headers=admin_headers
    )
    assert parent.status_code == 201, parent.text
    parent_id = parent.json()["id"]
    body = {"name": "test"}
    body["dataset_id"] = parent_id
    created = client.post("/api/retention-policies", json=body, headers=admin_headers)
    assert created.status_code == 201, created.text
    _id = created.json()["id"]
    listing = client.get("/api/retention-policies", headers=admin_headers)
    assert listing.status_code == 200, listing.text
    row = next((r for r in listing.json() if r.get("id") == _id), None)
    assert row is not None, "created record not found in list"
    assert row.get("dataset_id") == parent_id
    bogus = {"name": "test"}
    bogus["dataset_id"] = "no-such-parent-id"
    rejected = client.post("/api/retention-policies", json=bogus, headers=admin_headers)
    assert rejected.status_code >= 400, "FK constraint not enforced: " + rejected.text
