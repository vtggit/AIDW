"""Field-flow test — supports_delta round-trips through the odata_service_configs API."""


def test_odata_service_configs_supports_delta_round_trips(client, admin_headers):
    body = {"name": "test"}
    body["supports_delta"] = True
    created = client.post(
        "/api/odata-service-configs", json=body, headers=admin_headers
    )
    assert created.status_code == 201, created.text
    _id = created.json()["id"]
    listing = client.get("/api/odata-service-configs", headers=admin_headers)
    assert listing.status_code == 200, listing.text
    row = next((r for r in listing.json() if r.get("id") == _id), None)
    assert row is not None, "created record not found in list"
    assert row.get("supports_delta") is True
