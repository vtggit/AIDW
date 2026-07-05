"""Activities API CRUD tests.

Verifies:
    - Authenticated user can list/get activities
    - Admin create/update/delete works
    - Non-admin mutation is blocked (403)
    - Unauthenticated requests are blocked (401)
    - Invalid payload is rejected
"""


def test_activities_list_empty(client, user_headers):
    """Authenticated user can list activities."""
    response = client.get("/api/activities", headers=user_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_activities_list_unauthenticated_returns_401(client):
    """Unauthenticated request to activities list returns 401."""
    response = client.get("/api/activities")
    assert response.status_code == 401


def test_activities_create_admin(client, admin_headers):
    """Admin can create an activity."""
    payload = {"type": "call", "description": "Follow-up call"}
    response = client.post("/api/activities", json=payload, headers=admin_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["type"] == "call"


def test_activities_create_requires_type(client, admin_headers):
    """Creating an activity without a type should fail validation."""
    response = client.post(
        "/api/activities",
        json={"description": "No type"},
        headers=admin_headers,
    )
    assert response.status_code in (400, 422)


def test_activities_create_requires_description(client, admin_headers):
    """Creating an activity without a description should fail validation."""
    response = client.post(
        "/api/activities",
        json={"type": "call"},
        headers=admin_headers,
    )
    assert response.status_code in (400, 422)


def test_activities_read_by_id(client, admin_headers):
    """Authenticated user can get an activity by ID."""
    create_resp = client.post(
        "/api/activities",
        json={"type": "meeting", "description": "Quarterly review"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    aid = create_resp.json()["id"]

    response = client.get(f"/api/activities/{aid}", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == aid


def test_activities_read_nonexistent(client, admin_headers):
    """Getting a nonexistent activity returns 404."""
    response = client.get("/api/activities/nonexistent-id", headers=admin_headers)
    assert response.status_code == 404


def test_activities_update_admin(client, admin_headers):
    """Admin can update an existing activity."""
    create_resp = client.post(
        "/api/activities",
        json={"type": "call", "description": "Original"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    aid = create_resp.json()["id"]

    response = client.put(
        f"/api/activities/{aid}",
        json={"status": "completed"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"


def test_activities_delete_admin(client, admin_headers):
    """Admin can delete an activity."""
    create_resp = client.post(
        "/api/activities",
        json={"type": "call", "description": "Delete Me"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    aid = create_resp.json()["id"]

    response = client.delete(f"/api/activities/{aid}", headers=admin_headers)
    assert response.status_code == 204

    # Verify it's gone
    response = client.get(f"/api/activities/{aid}", headers=admin_headers)
    assert response.status_code == 404


def test_activities_delete_nonexistent(client, admin_headers):
    """Deleting a nonexistent activity returns 404."""
    response = client.delete("/api/activities/nonexistent-id", headers=admin_headers)
    assert response.status_code == 404


def test_activities_status_defaults_to_pending(client, admin_headers):
    """Activity status defaults to 'pending' when not specified."""
    response = client.post(
        "/api/activities",
        json={"type": "call", "description": "Default Status"},
        headers=admin_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data.get("status") == "pending"


def test_activities_create_non_admin_returns_403(client, user_headers):
    """Non-admin user cannot create activities."""
    response = client.post(
        "/api/activities",
        json={"type": "call", "description": "Blocked"},
        headers=user_headers,
    )
    assert response.status_code == 403


def test_activities_update_non_admin_returns_403(client, user_headers, admin_headers):
    """Non-admin user cannot update activities."""
    create_resp = client.post(
        "/api/activities",
        json={"type": "call", "description": "Original"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    aid = create_resp.json()["id"]

    response = client.put(
        f"/api/activities/{aid}",
        json={"status": "completed"},
        headers=user_headers,
    )
    assert response.status_code == 403


def test_activities_delete_non_admin_returns_403(client, user_headers, admin_headers):
    """Non-admin user cannot delete activities."""
    create_resp = client.post(
        "/api/activities",
        json={"type": "call", "description": "Protected"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    aid = create_resp.json()["id"]

    response = client.delete(f"/api/activities/{aid}", headers=user_headers)
    assert response.status_code == 403


def test_activities_with_contact_name(client, admin_headers):
    """Admin can create an activity with a contact name."""
    response = client.post(
        "/api/activities",
        json={
            "type": "meeting",
            "description": "Sales call",
            "contact_name": "John Doe",
        },
        headers=admin_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["contact_name"] == "John Doe"
