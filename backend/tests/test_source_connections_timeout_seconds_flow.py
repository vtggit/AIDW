"""Field-flow test — timeout_seconds round-trips through the source_connections API."""


def test_source_connections_timeout_seconds_round_trips(client, admin_headers):
    body = {"name": "test"}
    body["timeout_seconds"] = 7
    created = client.post("/api/source-connections", json=body, headers=admin_headers)
    assert created.status_code == 201, created.text
    _id = created.json()["id"]
    listing = client.get("/api/source-connections", headers=admin_headers)
    assert listing.status_code == 200, listing.text
    row = next((r for r in listing.json() if r.get("id") == _id), None)
    assert row is not None, "created record not found in list"
    assert row.get("timeout_seconds") == 7
