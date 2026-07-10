"""Field-flow test — records_purged (CHECK >= 0) round-trips and rejects out-of-range."""


def test_retention_runs_records_purged_round_trips(client, admin_headers):
    body = {"name": "test"}
    body["records_purged"] = 0
    created = client.post("/api/retention-runs", json=body, headers=admin_headers)
    assert created.status_code == 201, created.text
    _id = created.json()["id"]
    listing = client.get("/api/retention-runs", headers=admin_headers)
    assert listing.status_code == 200, listing.text
    row = next((r for r in listing.json() if r.get("id") == _id), None)
    assert row is not None, "created record not found in list"
    assert row.get("records_purged") == 0
    bad_body = {"name": "test"}
    bad_body["records_purged"] = -1
    rejected = client.post("/api/retention-runs", json=bad_body, headers=admin_headers)
    assert rejected.status_code >= 400, "CHECK not enforced: " + rejected.text
    after = client.get("/api/retention-runs", headers=admin_headers)
    assert all(
        r.get("records_purged") != -1 for r in after.json()
    ), "out-of-range value persisted"
