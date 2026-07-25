"""Field-flow test — grid_col_span (CHECK between 1 and 12) round-trips and rejects out-of-range."""


def test_dashboard_item_layouts_grid_col_span_round_trips(client, admin_headers):
    body = {"name": "test"}
    body["grid_col_span"] = 1
    created = client.post(
        "/api/dashboard-item-layouts", json=body, headers=admin_headers
    )
    assert created.status_code == 201, created.text
    _id = created.json()["id"]
    listing = client.get("/api/dashboard-item-layouts", headers=admin_headers)
    assert listing.status_code == 200, listing.text
    row = next((r for r in listing.json() if r.get("id") == _id), None)
    assert row is not None, "created record not found in list"
    assert row.get("grid_col_span") == 1
    bad_body = {"name": "test"}
    bad_body["grid_col_span"] = 0
    rejected = client.post(
        "/api/dashboard-item-layouts", json=bad_body, headers=admin_headers
    )
    assert rejected.status_code >= 400, "CHECK not enforced: " + rejected.text
    after = client.get("/api/dashboard-item-layouts", headers=admin_headers)
    assert all(
        r.get("grid_col_span") != 0 for r in after.json()
    ), "out-of-range value persisted"
