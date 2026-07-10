"""Field-flow test — retention_period_days (CHECK > 0) round-trips and rejects out-of-range."""


def test_retention_policies_retention_period_days_round_trips(client, admin_headers):
    body = {"name": "test"}
    body["retention_period_days"] = 1
    created = client.post("/api/retention-policies", json=body, headers=admin_headers)
    assert created.status_code == 201, created.text
    _id = created.json()["id"]
    listing = client.get("/api/retention-policies", headers=admin_headers)
    assert listing.status_code == 200, listing.text
    row = next((r for r in listing.json() if r.get("id") == _id), None)
    assert row is not None, "created record not found in list"
    assert row.get("retention_period_days") == 1
    bad_body = {"name": "test"}
    bad_body["retention_period_days"] = 0
    rejected = client.post(
        "/api/retention-policies", json=bad_body, headers=admin_headers
    )
    assert rejected.status_code >= 400, "CHECK not enforced: " + rejected.text
    after = client.get("/api/retention-policies", headers=admin_headers)
    assert all(
        r.get("retention_period_days") != 0 for r in after.json()
    ), "out-of-range value persisted"
