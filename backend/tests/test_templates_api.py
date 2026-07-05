"""Templates API CRUD tests.

Verifies:
    - Authenticated user can list templates
    - Admin create/update/delete works
    - Non-admin mutation is blocked (403)
    - Unauthenticated requests are blocked (401)
    - Invalid payload is rejected
"""


def test_templates_list_empty(client, user_headers):
    """Authenticated user can list templates."""
    response = client.get("/api/templates", headers=user_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_templates_list_unauthenticated_returns_401(client):
    """Unauthenticated request to templates list returns 401."""
    response = client.get("/api/templates")
    assert response.status_code == 401


def test_templates_create_admin(client, admin_headers):
    """Admin can create a template."""
    payload = {
        "name": "Test Template",
        "category": "introduction",
        "content": "Hello {{name}}",
    }
    response = client.post("/api/templates", json=payload, headers=admin_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["name"] == "Test Template"


def test_templates_create_requires_name(client, admin_headers):
    """Creating a template without a name should fail validation."""
    response = client.post(
        "/api/templates",
        json={"content": "no name"},
        headers=admin_headers,
    )
    assert response.status_code in (400, 422)


def test_templates_create_invalid_category(client, admin_headers):
    """Creating a template with invalid category should fail validation."""
    response = client.post(
        "/api/templates",
        json={"name": "Bad Cat", "category": "invalid", "content": "body"},
        headers=admin_headers,
    )
    assert response.status_code in (400, 422)


def test_templates_update_admin(client, admin_headers):
    """Admin can update an existing template."""
    create_resp = client.post(
        "/api/templates",
        json={"name": "Original", "content": "old"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    tid = create_resp.json()["id"]

    response = client.put(
        f"/api/templates/{tid}",
        json={"name": "Updated", "content": "new content"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated"


def test_templates_update_nonexistent(client, admin_headers):
    """Updating a nonexistent template returns 404."""
    response = client.put(
        "/api/templates/nonexistent-id",
        json={"name": "Ghost"},
        headers=admin_headers,
    )
    assert response.status_code == 404


def test_templates_delete_admin(client, admin_headers):
    """Admin can delete a template."""
    create_resp = client.post(
        "/api/templates",
        json={"name": "Delete Me", "content": "body"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    tid = create_resp.json()["id"]

    response = client.delete(f"/api/templates/{tid}", headers=admin_headers)
    assert response.status_code == 204


def test_templates_delete_nonexistent(client, admin_headers):
    """Deleting a nonexistent template returns 404."""
    response = client.delete("/api/templates/nonexistent-id", headers=admin_headers)
    assert response.status_code == 404


def test_templates_category_defaults_to_other(client, admin_headers):
    """Template category defaults to 'other' when not specified."""
    response = client.post(
        "/api/templates",
        json={"name": "Default Cat", "content": "body"},
        headers=admin_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data.get("category") == "other"


def test_templates_create_non_admin_returns_403(client, user_headers):
    """Non-admin user cannot create templates."""
    response = client.post(
        "/api/templates",
        json={"name": "Blocked", "content": "body"},
        headers=user_headers,
    )
    assert response.status_code == 403


def test_templates_update_non_admin_returns_403(client, user_headers, admin_headers):
    """Non-admin user cannot update templates."""
    create_resp = client.post(
        "/api/templates",
        json={"name": "Original", "content": "old"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    tid = create_resp.json()["id"]

    response = client.put(
        f"/api/templates/{tid}",
        json={"name": "Hacked"},
        headers=user_headers,
    )
    assert response.status_code == 403
