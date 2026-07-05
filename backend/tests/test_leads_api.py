"""Leads API CRUD tests.

Verifies:
    - Authenticated user can list/get leads
    - Admin create/update/delete works
    - Non-admin mutation is blocked (403)
    - Unauthenticated requests are blocked (401)
    - Invalid payload is rejected
"""


def test_leads_list_empty(client, user_headers):
    """Authenticated user can list leads."""
    response = client.get("/api/leads", headers=user_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_leads_list_unauthenticated_returns_401(client):
    """Unauthenticated request to leads list returns 401."""
    response = client.get("/api/leads")
    assert response.status_code == 401


def test_leads_create_admin(client, admin_headers):
    """Admin can create a lead."""
    payload = {"name": "Test Lead", "company": "TestCo", "email": "lead@test.com"}
    response = client.post("/api/leads", json=payload, headers=admin_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["name"] == "Test Lead"


def test_leads_create_requires_name(client, admin_headers):
    """Creating a lead without a name should fail validation."""
    response = client.post(
        "/api/leads",
        json={"company": "NoNameCo"},
        headers=admin_headers,
    )
    assert response.status_code in (400, 422)


def test_leads_read_by_id(client, admin_headers):
    """Authenticated user can get a lead by ID."""
    create_resp = client.post(
        "/api/leads",
        json={"name": "Read Me", "company": "TestCo"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    lid = create_resp.json()["id"]

    response = client.get(f"/api/leads/{lid}", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == lid


def test_leads_read_nonexistent(client, admin_headers):
    """Getting a nonexistent lead returns 404."""
    response = client.get("/api/leads/nonexistent-id", headers=admin_headers)
    assert response.status_code == 404


def test_leads_update_admin(client, admin_headers):
    """Admin can update an existing lead."""
    create_resp = client.post(
        "/api/leads",
        json={"name": "Original", "company": "OldCo"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    lid = create_resp.json()["id"]

    response = client.put(
        f"/api/leads/{lid}",
        json={"name": "Updated", "stage": "qualified"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated"


def test_leads_delete_admin(client, admin_headers):
    """Admin can delete a lead."""
    create_resp = client.post(
        "/api/leads",
        json={"name": "Delete Me"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    lid = create_resp.json()["id"]

    response = client.delete(f"/api/leads/{lid}", headers=admin_headers)
    assert response.status_code == 204

    # Verify it's gone
    response = client.get(f"/api/leads/{lid}", headers=admin_headers)
    assert response.status_code == 404


def test_leads_delete_nonexistent(client, admin_headers):
    """Deleting a nonexistent lead returns 404."""
    response = client.delete("/api/leads/nonexistent-id", headers=admin_headers)
    assert response.status_code == 404


def test_leads_stage_defaults_to_new(client, admin_headers):
    """Lead stage defaults to 'new' when not specified."""
    response = client.post(
        "/api/leads",
        json={"name": "Default Stage"},
        headers=admin_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data.get("stage") == "new"


def test_leads_create_non_admin_returns_403(client, user_headers):
    """Non-admin user cannot create leads."""
    response = client.post(
        "/api/leads",
        json={"name": "Blocked"},
        headers=user_headers,
    )
    assert response.status_code == 403


def test_leads_update_non_admin_returns_403(client, user_headers, admin_headers):
    """Non-admin user cannot update leads."""
    create_resp = client.post(
        "/api/leads",
        json={"name": "Original"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    lid = create_resp.json()["id"]

    response = client.put(
        f"/api/leads/{lid}",
        json={"name": "Hacked"},
        headers=user_headers,
    )
    assert response.status_code == 403


def test_leads_delete_non_admin_returns_403(client, user_headers, admin_headers):
    """Non-admin user cannot delete leads."""
    create_resp = client.post(
        "/api/leads",
        json={"name": "Protected"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    lid = create_resp.json()["id"]

    response = client.delete(f"/api/leads/{lid}", headers=user_headers)
    assert response.status_code == 403


def test_leads_with_value(client, admin_headers):
    """Admin can create a lead with a monetary value."""
    response = client.post(
        "/api/leads",
        json={"name": "Valued Lead", "company": "BigCo", "value": 15000.00},
        headers=admin_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert float(data["value"]) == 15000.00
