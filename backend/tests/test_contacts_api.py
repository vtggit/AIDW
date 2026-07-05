"""Contacts API CRUD tests.

Verifies:
    - Admin list/create/update/delete works
    - Non-admin mutation is blocked (403)
    - Unauthenticated requests are blocked (401)
    - Invalid payload is rejected
    - API response shapes match actual backend behavior
"""

import uuid


def _cid():
    return str(uuid.uuid4())


def test_contacts_list_empty(client, admin_headers):
    """Admin can list contacts; response is a raw array."""
    response = client.get("/api/contacts", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_contacts_list_unauthenticated_returns_401(client):
    """Unauthenticated request to contacts list returns 401."""
    response = client.get("/api/contacts")
    assert response.status_code == 401


def test_contacts_create_admin(client, admin_headers):
    """Admin can create a contact."""
    payload = {"name": "Test Contact", "email": "test@example.com"}
    response = client.post("/api/contacts", json=payload, headers=admin_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["name"] == "Test Contact"


def test_contacts_create_requires_name(client, admin_headers):
    """Creating a contact without a name should fail validation."""
    response = client.post(
        "/api/contacts",
        json={"email": "no-name@example.com"},
        headers=admin_headers,
    )
    assert response.status_code in (400, 422)


def test_contacts_update_admin(client, admin_headers):
    """Admin can update an existing contact."""
    # Create first
    create_resp = client.post(
        "/api/contacts",
        json={"name": "Original"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    cid = create_resp.json()["id"]

    response = client.put(
        f"/api/contacts/{cid}",
        json={"name": "Updated Name"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"


def test_contacts_update_nonexistent(client, admin_headers):
    """Updating a nonexistent contact returns 404."""
    response = client.put(
        f"/api/contacts/{_cid()}",
        json={"name": "Ghost"},
        headers=admin_headers,
    )
    assert response.status_code == 404


def test_contacts_delete_admin(client, admin_headers):
    """Admin can delete a contact."""
    # Create first
    create_resp = client.post(
        "/api/contacts",
        json={"name": "Delete Me"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    cid = create_resp.json()["id"]

    response = client.delete(f"/api/contacts/{cid}", headers=admin_headers)
    assert response.status_code == 204

    # Verify it's gone from the list
    response = client.get("/api/contacts", headers=admin_headers)
    assert response.status_code == 200
    items = response.json()
    assert not any(c.get("id") == cid for c in items)


def test_contacts_delete_nonexistent(client, admin_headers):
    """Deleting a nonexistent contact returns 404."""
    response = client.delete(f"/api/contacts/{_cid()}", headers=admin_headers)
    assert response.status_code == 404


def test_contacts_create_multiple(client, admin_headers):
    """Admin can create multiple contacts and list them all."""
    for _ in range(3):
        resp = client.post(
            "/api/contacts",
            json={"name": "Multi Contact"},
            headers=admin_headers,
        )
        assert resp.status_code == 201
    response = client.get("/api/contacts", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3


def test_contacts_create_non_admin_returns_403(client, user_headers):
    """Non-admin user cannot create contacts."""
    response = client.post(
        "/api/contacts",
        json={"name": "Blocked"},
        headers=user_headers,
    )
    assert response.status_code == 403


def test_contacts_update_non_admin_returns_403(client, user_headers, admin_headers):
    """Non-admin user cannot update contacts."""
    create_resp = client.post(
        "/api/contacts",
        json={"name": "Original"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    cid = create_resp.json()["id"]

    response = client.put(
        f"/api/contacts/{cid}",
        json={"name": "Hacked"},
        headers=user_headers,
    )
    assert response.status_code == 403


def test_contacts_delete_non_admin_returns_403(client, user_headers, admin_headers):
    """Non-admin user cannot delete contacts."""
    create_resp = client.post(
        "/api/contacts",
        json={"name": "Protected"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    cid = create_resp.json()["id"]

    response = client.delete(f"/api/contacts/{cid}", headers=user_headers)
    assert response.status_code == 403
