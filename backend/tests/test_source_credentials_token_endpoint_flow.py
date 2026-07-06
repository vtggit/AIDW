"""Field-flow test — token_endpoint round-trips through the source_credentials API."""


def test_source_credentials_token_endpoint_round_trips(client, admin_headers):
    body = {"name": "test"}
    body["token_endpoint"] = "high"
    created = client.post("/api/source-credentials", json=body, headers=admin_headers)
    assert created.status_code == 201, created.text
    _id = created.json()["id"]
    listing = client.get("/api/source-credentials", headers=admin_headers)
    assert listing.status_code == 200, listing.text
    row = next((r for r in listing.json() if r.get("id") == _id), None)
    assert row is not None, "created record not found in list"
    assert row.get("token_endpoint") == "high"
