"""Field-flow test — discovered_field_id (FK -> discovered_fields) round-trips through the pii_flags API."""


def test_pii_flags_discovered_field_id_round_trips(client, admin_headers):
    parent = client.post(
        "/api/discovered-fields", json={"name": "FK Parent"}, headers=admin_headers
    )
    assert parent.status_code == 201, parent.text
    parent_id = parent.json()["id"]
    body = {"name": "test"}
    body["discovered_field_id"] = parent_id
    created = client.post("/api/pii-flags", json=body, headers=admin_headers)
    assert created.status_code == 201, created.text
    _id = created.json()["id"]
    listing = client.get("/api/pii-flags", headers=admin_headers)
    assert listing.status_code == 200, listing.text
    row = next((r for r in listing.json() if r.get("id") == _id), None)
    assert row is not None, "created record not found in list"
    assert row.get("discovered_field_id") == parent_id
    bogus = {"name": "test"}
    bogus["discovered_field_id"] = "no-such-parent-id"
    rejected = client.post("/api/pii-flags", json=bogus, headers=admin_headers)
    assert rejected.status_code >= 400, "FK constraint not enforced: " + rejected.text
