"""Proving test for issue #483: GET /api/load-sequences/due declares response model."""


def test_issue483_surgical(app, client, admin_headers, clean_database):
    # 1. OpenAPI document must contain a response schema for GET /api/load-sequences/due
    openapi = app.openapi()
    due_path = openapi["paths"]["/api/load-sequences/due"]
    get_op = due_path["get"]
    resp_200 = get_op["responses"]["200"]
    schema = resp_200["content"]["application/json"]["schema"]
    assert schema["type"] == "array"
    assert "DueLoadSequenceResponse" in schema["items"]["$ref"]

    # Verify the component schema has exactly the five expected fields
    components = openapi["components"]["schemas"]
    assert "DueLoadSequenceResponse" in components
    props = components["DueLoadSequenceResponse"]["properties"]
    assert set(props.keys()) == {
        "id",
        "name",
        "schedule_cadence",
        "schedule_enabled",
        "last_fired_at",
    }

    # 2. Authenticated call still returns 200 with a JSON list
    resp = client.get(
        "/api/load-sequences/due",
        params={"not_fired_since": "2026-01-01T00:00:00Z"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    for entry in data:
        assert set(entry.keys()) == {
            "id",
            "name",
            "schedule_cadence",
            "schedule_enabled",
            "last_fired_at",
        }
