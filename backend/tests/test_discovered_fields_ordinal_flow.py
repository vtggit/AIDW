"""Field-flow test — field_position round-trips through the discovered_fields API."""


def test_discovered_fields_ordinal_round_trips(client, admin_headers):
    body = {"name": "test"}
    body["field_position"] = 7
    created = client.post("/api/discovered-fields", json=body, headers=admin_headers)
    assert created.status_code == 201, created.text
    _id = created.json()["id"]
    listing = client.get("/api/discovered-fields", headers=admin_headers)
    assert listing.status_code == 200, listing.text
    row = next((r for r in listing.json() if r.get("id") == _id), None)
    assert row is not None, "created record not found in list"
    assert row.get("field_position") == 7
