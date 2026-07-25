"""Field-flow test — grid_columns (CHECK between 1 and 12) round-trips and rejects out-of-range."""


def test_dashboards_grid_columns_round_trips(client, admin_headers):
    body = {"name": "test"}
    body["grid_columns"] = 1
    created = client.post("/api/dashboards", json=body, headers=admin_headers)
    assert created.status_code == 201, created.text
    _id = created.json()["id"]
    listing = client.get("/api/dashboards", headers=admin_headers)
    assert listing.status_code == 200, listing.text
    row = next((r for r in listing.json() if r.get("id") == _id), None)
    assert row is not None, "created record not found in list"
    assert row.get("grid_columns") == 1
    bad_body = {"name": "test"}
    bad_body["grid_columns"] = 0
    rejected = client.post("/api/dashboards", json=bad_body, headers=admin_headers)
    assert rejected.status_code >= 400, "CHECK not enforced: " + rejected.text
    after = client.get("/api/dashboards", headers=admin_headers)
    assert all(
        r.get("grid_columns") != 0 for r in after.json()
    ), "out-of-range value persisted"
