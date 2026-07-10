"""Field-flow test — is_enabled round-trips through the retention_policies API."""


def test_retention_policies_is_enabled_round_trips(client, admin_headers):
    body = {"name": "test"}
    body["is_enabled"] = True
    created = client.post("/api/retention-policies", json=body, headers=admin_headers)
    assert created.status_code == 201, created.text
    _id = created.json()["id"]
    listing = client.get("/api/retention-policies", headers=admin_headers)
    assert listing.status_code == 200, listing.text
    row = next((r for r in listing.json() if r.get("id") == _id), None)
    assert row is not None, "created record not found in list"
    assert row.get("is_enabled") is True
