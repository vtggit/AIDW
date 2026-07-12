"""Field-flow test — rows_suppressed round-trips through the runs API."""


def test_runs_rows_suppressed_round_trips(client, admin_headers):
    body = {"name": "test"}
    body["rows_suppressed"] = 7
    created = client.post("/api/runs", json=body, headers=admin_headers)
    assert created.status_code == 201, created.text
    _id = created.json()["id"]
    listing = client.get("/api/runs", headers=admin_headers)
    assert listing.status_code == 200, listing.text
    row = next((r for r in listing.json() if r.get("id") == _id), None)
    assert row is not None, "created record not found in list"
    assert row.get("rows_suppressed") == 7
