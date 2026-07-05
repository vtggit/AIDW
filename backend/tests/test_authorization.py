"""Authorization tests.

Verifies that:
    - Unauthenticated requests to protected routes return 401
    - Authenticated non-admin requests to mutation routes return 403
    - Authenticated admin requests to mutation routes succeed
    - Read-only routes have appropriate access levels
"""

# ---------------------------------------------------------------------------
# Contacts authorization (all routes require admin)
# ---------------------------------------------------------------------------


def test_contacts_list_unauthenticated_returns_401(client):
    response = client.get("/api/contacts")
    assert response.status_code == 401


def test_contacts_list_non_admin_returns_403(client, user_headers):
    """Contacts list requires admin role."""
    response = client.get("/api/contacts", headers=user_headers)
    assert response.status_code == 403


def test_contacts_list_admin_succeeds(client, admin_headers):
    response = client.get("/api/contacts", headers=admin_headers)
    assert response.status_code == 200


def test_contacts_create_non_admin_returns_403(client, user_headers):
    response = client.post(
        "/api/contacts",
        json={"name": "Auth Test", "email": "auth@test.com"},
        headers=user_headers,
    )
    assert response.status_code == 403


def test_contacts_create_admin_succeeds(client, admin_headers):
    response = client.post(
        "/api/contacts",
        json={"name": "Admin Contact", "email": "admin@test.com"},
        headers=admin_headers,
    )
    assert response.status_code == 201


def test_contacts_update_non_admin_returns_403(client, user_headers, admin_headers):
    create_resp = client.post(
        "/api/contacts",
        json={"name": "Update Test"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    cid = create_resp.json()["id"]
    response = client.put(
        f"/api/contacts/{cid}",
        json={"name": "Updated"},
        headers=user_headers,
    )
    assert response.status_code == 403


def test_contacts_delete_non_admin_returns_403(client, user_headers, admin_headers):
    create_resp = client.post(
        "/api/contacts",
        json={"name": "Delete Test"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    cid = create_resp.json()["id"]
    response = client.delete(f"/api/contacts/{cid}", headers=user_headers)
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Templates authorization (list: authenticated, mutations: admin)
# ---------------------------------------------------------------------------


def test_templates_list_unauthenticated_returns_401(client):
    response = client.get("/api/templates")
    assert response.status_code == 401


def test_templates_list_authenticated_user_succeeds(client, user_headers):
    response = client.get("/api/templates", headers=user_headers)
    assert response.status_code == 200


def test_templates_create_non_admin_returns_403(client, user_headers):
    response = client.post(
        "/api/templates",
        json={"name": "Auth Template", "content": "test"},
        headers=user_headers,
    )
    assert response.status_code == 403


def test_templates_create_admin_succeeds(client, admin_headers):
    response = client.post(
        "/api/templates",
        json={"name": "Admin Template", "content": "test"},
        headers=admin_headers,
    )
    assert response.status_code == 201


# ---------------------------------------------------------------------------
# Leads authorization (list/get: authenticated, mutations: admin)
# ---------------------------------------------------------------------------


def test_leads_list_unauthenticated_returns_401(client):
    response = client.get("/api/leads")
    assert response.status_code == 401


def test_leads_list_authenticated_user_succeeds(client, user_headers):
    response = client.get("/api/leads", headers=user_headers)
    assert response.status_code == 200


def test_leads_create_non_admin_returns_403(client, user_headers):
    response = client.post(
        "/api/leads",
        json={"name": "Auth Lead", "company": "TestCo"},
        headers=user_headers,
    )
    assert response.status_code == 403


def test_leads_create_admin_succeeds(client, admin_headers):
    response = client.post(
        "/api/leads",
        json={"name": "Admin Lead", "company": "TestCo"},
        headers=admin_headers,
    )
    assert response.status_code == 201


# ---------------------------------------------------------------------------
# Activities authorization (list/get: authenticated, mutations: admin)
# ---------------------------------------------------------------------------


def test_activities_list_unauthenticated_returns_401(client):
    response = client.get("/api/activities")
    assert response.status_code == 401


def test_activities_list_authenticated_user_succeeds(client, user_headers):
    response = client.get("/api/activities", headers=user_headers)
    assert response.status_code == 200


def test_activities_create_non_admin_returns_403(client, user_headers):
    response = client.post(
        "/api/activities",
        json={"type": "call", "description": "Auth test"},
        headers=user_headers,
    )
    assert response.status_code == 403


def test_activities_create_admin_succeeds(client, admin_headers):
    response = client.post(
        "/api/activities",
        json={"type": "call", "description": "Admin test"},
        headers=admin_headers,
    )
    assert response.status_code == 201


# ---------------------------------------------------------------------------
# Settings authorization (read: authenticated, update: admin)
# ---------------------------------------------------------------------------


def test_settings_read_unauthenticated_returns_401(client):
    response = client.get("/api/settings")
    assert response.status_code == 401


def test_settings_read_authenticated_user_succeeds(client, user_headers):
    response = client.get("/api/settings", headers=user_headers)
    assert response.status_code == 200


def test_settings_update_non_admin_returns_403(client, user_headers):
    response = client.put(
        "/api/settings",
        json={"payload": {"theme": "dark"}},
        headers=user_headers,
    )
    assert response.status_code == 403


def test_settings_update_admin_succeeds(client, admin_headers):
    response = client.put(
        "/api/settings",
        json={"payload": {"theme": "dark"}},
        headers=admin_headers,
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Audit authorization (admin only)
# ---------------------------------------------------------------------------


def test_audit_list_unauthenticated_returns_401(client):
    response = client.get("/api/audit")
    assert response.status_code == 401


def test_audit_list_non_admin_returns_403(client, user_headers):
    response = client.get("/api/audit", headers=user_headers)
    assert response.status_code == 403


def test_audit_list_admin_succeeds(client, admin_headers):
    response = client.get("/api/audit", headers=admin_headers)
    assert response.status_code == 200
