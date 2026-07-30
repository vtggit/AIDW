"""Field-flow test — order_index (CHECK >= 0) round-trips and rejects out-of-range."""


def test_order_index_round_trips(client, admin_headers):
    body = {"name": "test"}
    body["order_index"] = 0
    created = client.post("/api/sequence-steps", json=body, headers=admin_headers)
    assert created.status_code == 201, created.text
    _id = created.json()["id"]
    listing = client.get("/api/sequence-steps", headers=admin_headers)
    assert listing.status_code == 200, listing.text
    row = next((r for r in listing.json() if r.get("id") == _id), None)
    assert row is not None, "created record not found in list"
    assert row.get("order_index") == 0
    bad_body = {"name": "test"}
    bad_body["order_index"] = -1
    rejected = client.post("/api/sequence-steps", json=bad_body, headers=admin_headers)
    assert rejected.status_code >= 400, "CHECK not enforced: " + rejected.text
    after = client.get("/api/sequence-steps", headers=admin_headers)
    assert all(
        r.get("order_index") != -1 for r in after.json()
    ), "out-of-range value persisted"
