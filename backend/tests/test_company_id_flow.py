"""Field-flow test — company_id (FK -> companies) round-trips through the contacts API."""


def test_company_id_round_trips(client, admin_headers):
    parent = client.post(
        "/api/companies", json={"name": "FK Parent"}, headers=admin_headers
    )
    assert parent.status_code == 201, parent.text
    parent_id = parent.json()["id"]
    body = {"name": "test"}
    body["company_id"] = parent_id
    created = client.post("/api/contacts", json=body, headers=admin_headers)
    assert created.status_code == 201, created.text
    _id = created.json()["id"]
    listing = client.get("/api/contacts", headers=admin_headers)
    assert listing.status_code == 200, listing.text
    row = next((r for r in listing.json() if r.get("id") == _id), None)
    assert row is not None, "created record not found in list"
    assert row.get("company_id") == parent_id
    bogus = {"name": "test"}
    bogus["company_id"] = "no-such-parent-id"
    rejected = client.post("/api/contacts", json=bogus, headers=admin_headers)
    assert rejected.status_code >= 400, "FK constraint not enforced: " + rejected.text
