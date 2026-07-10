"""Field-flow test — policy_id (FK -> retention_policies) round-trips through the retention_runs API."""


def test_retention_runs_policy_id_round_trips(client, admin_headers):
    parent = client.post(
        "/api/retention-policies", json={"name": "FK Parent"}, headers=admin_headers
    )
    assert parent.status_code == 201, parent.text
    parent_id = parent.json()["id"]
    body = {"name": "test"}
    body["policy_id"] = parent_id
    created = client.post("/api/retention-runs", json=body, headers=admin_headers)
    assert created.status_code == 201, created.text
    _id = created.json()["id"]
    listing = client.get("/api/retention-runs", headers=admin_headers)
    assert listing.status_code == 200, listing.text
    row = next((r for r in listing.json() if r.get("id") == _id), None)
    assert row is not None, "created record not found in list"
    assert row.get("policy_id") == parent_id
    bogus = {"name": "test"}
    bogus["policy_id"] = "no-such-parent-id"
    rejected = client.post("/api/retention-runs", json=bogus, headers=admin_headers)
    assert rejected.status_code >= 400, "FK constraint not enforced: " + rejected.text
