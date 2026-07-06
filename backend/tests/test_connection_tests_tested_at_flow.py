"""Field-flow test — tested_at round-trips through the connection_tests API."""


def test_connection_tests_tested_at_round_trips(client, admin_headers):
    body = {"name": "test"}
    body["tested_at"] = "high"
    created = client.post("/api/connection-tests", json=body, headers=admin_headers)
    assert created.status_code == 201, created.text
    _id = created.json()["id"]
    listing = client.get("/api/connection-tests", headers=admin_headers)
    assert listing.status_code == 200, listing.text
    row = next((r for r in listing.json() if r.get("id") == _id), None)
    assert row is not None, "created record not found in list"
    assert row.get("tested_at") == "high"
