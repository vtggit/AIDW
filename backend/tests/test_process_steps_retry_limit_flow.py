"""Field-flow test — retry_limit (CHECK > 0) round-trips and rejects out-of-range."""


def test_process_steps_retry_limit_round_trips(client, admin_headers):
    body = {"name": "test"}
    body["retry_limit"] = 1
    created = client.post("/api/process-steps", json=body, headers=admin_headers)
    assert created.status_code == 201, created.text
    _id = created.json()["id"]
    listing = client.get("/api/process-steps", headers=admin_headers)
    assert listing.status_code == 200, listing.text
    row = next((r for r in listing.json() if r.get("id") == _id), None)
    assert row is not None, "created record not found in list"
    assert row.get("retry_limit") == 1
    bad_body = {"name": "test"}
    bad_body["retry_limit"] = 0
    rejected = client.post("/api/process-steps", json=bad_body, headers=admin_headers)
    assert rejected.status_code >= 400, "CHECK not enforced: " + rejected.text
    after = client.get("/api/process-steps", headers=admin_headers)
    assert all(
        r.get("retry_limit") != 0 for r in after.json()
    ), "out-of-range value persisted"
