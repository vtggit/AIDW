"""Settings API tests.

Verifies:
    - Authenticated read works
    - Admin update works
    - Non-admin update is blocked
"""


def test_settings_read_returns_200(client, admin_headers):
    response = client.get("/api/settings", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert "payload" in data


def test_settings_read_authenticated_user_succeeds(client, user_headers):
    response = client.get("/api/settings", headers=user_headers)
    assert response.status_code == 200


def test_settings_update_admin(client, admin_headers):
    response = client.put(
        "/api/settings",
        json={"payload": {"theme": "dark", "language": "en"}},
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["payload"]["theme"] == "dark"
    assert data["payload"]["language"] == "en"


def test_settings_update_non_admin_returns_403(client, user_headers):
    response = client.put(
        "/api/settings",
        json={"payload": {"theme": "hacked"}},
        headers=user_headers,
    )
    assert response.status_code == 403


def test_settings_update_persists(client, admin_headers):
    """Settings update should be readable back."""
    client.put(
        "/api/settings",
        json={"payload": {"test_key": "test_value"}},
        headers=admin_headers,
    )
    response = client.get("/api/settings", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["payload"]["test_key"] == "test_value"


def test_settings_update_merges_payload(client, admin_headers):
    """Settings update should merge with existing payload."""
    client.put(
        "/api/settings",
        json={"payload": {"key_a": "value_a"}},
        headers=admin_headers,
    )
    client.put(
        "/api/settings",
        json={"payload": {"key_b": "value_b"}},
        headers=admin_headers,
    )
    response = client.get("/api/settings", headers=admin_headers)
    data = response.json()
    assert data["payload"]["key_a"] == "value_a"
    assert data["payload"]["key_b"] == "value_b"
