"""Field-flow test — deletion_request_id (FK -> deletion_requests) round-trips through the suppression_entries API."""


def test_suppression_entries_deletion_request_id_round_trips(client, admin_headers):
    parent = client.post(
        "/api/deletion-requests", json={"name": "FK Parent"}, headers=admin_headers
    )
    assert parent.status_code == 201, parent.text
    parent_id = parent.json()["id"]
    body = {"name": "test"}
    body["deletion_request_id"] = parent_id
    created = client.post("/api/suppression-entries", json=body, headers=admin_headers)
    assert created.status_code == 201, created.text
    _id = created.json()["id"]
    listing = client.get("/api/suppression-entries", headers=admin_headers)
    assert listing.status_code == 200, listing.text
    row = next((r for r in listing.json() if r.get("id") == _id), None)
    assert row is not None, "created record not found in list"
    assert row.get("deletion_request_id") == parent_id
    bogus = {"name": "test"}
    bogus["deletion_request_id"] = "no-such-parent-id"
    rejected = client.post(
        "/api/suppression-entries", json=bogus, headers=admin_headers
    )
    assert rejected.status_code >= 400, "FK constraint not enforced: " + rejected.text
