"""Field-flow test — grid_row_span (CHECK between 1 and 6) round-trips and rejects out-of-range."""


def test_dashboard_items_grid_row_span_round_trips(client, admin_headers):
    body = {"name": "test"}
    body["grid_row_span"] = 1
    created = client.post("/api/dashboard-items", json=body, headers=admin_headers)
    assert created.status_code == 201, created.text
    _id = created.json()["id"]
    listing = client.get("/api/dashboard-items", headers=admin_headers)
    assert listing.status_code == 200, listing.text
    row = next((r for r in listing.json() if r.get("id") == _id), None)
    assert row is not None, "created record not found in list"
    assert row.get("grid_row_span") == 1
    bad_body = {"name": "test"}
    bad_body["grid_row_span"] = 0
    rejected = client.post("/api/dashboard-items", json=bad_body, headers=admin_headers)
    assert rejected.status_code >= 400, "CHECK not enforced: " + rejected.text
    after = client.get("/api/dashboard-items", headers=admin_headers)
    assert all(
        r.get("grid_row_span") != 0 for r in after.json()
    ), "out-of-range value persisted"
