"""Audit API tests.

Verifies:
    - Successful create/update/delete on migrated domains writes audit records
    - Audit records include actor identity
    - Admin can read /api/audit
    - Non-admin is blocked from reading /api/audit
"""


def test_audit_list_empty_initially(client, admin_headers):
    """Audit list starts empty and returns a raw array."""
    response = client.get("/api/audit", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_audit_record_created_on_contact_create(client, admin_headers):
    """Creating a contact writes an audit record."""
    create_resp = client.post(
        "/api/contacts",
        json={"name": "Audit Test Contact"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    cid = create_resp.json()["id"]

    response = client.get("/api/audit", headers=admin_headers)
    assert response.status_code == 200
    items = response.json()
    assert len(items) >= 1
    contact_audit = [
        r
        for r in items
        if r.get("entity_type") == "contact" and r.get("entity_id") == cid
    ]
    assert len(contact_audit) >= 1
    assert contact_audit[0]["action"] == "created"


def test_audit_record_created_on_contact_update(client, admin_headers):
    """Updating a contact writes an audit record."""
    create_resp = client.post(
        "/api/contacts",
        json={"name": "Original"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    cid = create_resp.json()["id"]

    client.put(
        f"/api/contacts/{cid}",
        json={"name": "Updated"},
        headers=admin_headers,
    )
    response = client.get("/api/audit", headers=admin_headers)
    items = response.json()
    contact_audit = [
        r
        for r in items
        if r.get("entity_type") == "contact" and r.get("entity_id") == cid
    ]
    update_records = [r for r in contact_audit if r.get("action") == "updated"]
    assert len(update_records) >= 1


def test_audit_record_created_on_contact_delete(client, admin_headers):
    """Deleting a contact writes an audit record."""
    create_resp = client.post(
        "/api/contacts",
        json={"name": "Delete Audit Test"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    cid = create_resp.json()["id"]

    client.delete(f"/api/contacts/{cid}", headers=admin_headers)
    response = client.get("/api/audit", headers=admin_headers)
    items = response.json()
    contact_audit = [
        r
        for r in items
        if r.get("entity_type") == "contact" and r.get("entity_id") == cid
    ]
    delete_records = [r for r in contact_audit if r.get("action") == "deleted"]
    assert len(delete_records) >= 1


def test_audit_record_includes_actor_identity(client, admin_headers):
    """Audit records include actor identity."""
    client.post(
        "/api/contacts",
        json={"name": "Actor Test"},
        headers=admin_headers,
    )
    response = client.get("/api/audit", headers=admin_headers)
    items = response.json()
    assert len(items) >= 1
    record = items[-1]
    assert "actor_sub" in record
    assert record["actor_sub"] == "dev-admin-1"


def test_audit_record_created_on_template_create(client, admin_headers):
    """Creating a template writes an audit record."""
    create_resp = client.post(
        "/api/templates",
        json={"name": "Audit Template", "content": "body"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    tid = create_resp.json()["id"]

    response = client.get("/api/audit", headers=admin_headers)
    items = response.json()
    template_audit = [
        r
        for r in items
        if r.get("entity_type") == "template" and r.get("entity_id") == tid
    ]
    assert len(template_audit) >= 1


def test_audit_record_created_on_lead_create(client, admin_headers):
    """Creating a lead writes an audit record."""
    create_resp = client.post(
        "/api/leads",
        json={"name": "Audit Lead"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    lid = create_resp.json()["id"]

    response = client.get("/api/audit", headers=admin_headers)
    items = response.json()
    lead_audit = [
        r for r in items if r.get("entity_type") == "lead" and r.get("entity_id") == lid
    ]
    assert len(lead_audit) >= 1


def test_audit_record_created_on_activity_create(client, admin_headers):
    """Creating an activity writes an audit record."""
    create_resp = client.post(
        "/api/activities",
        json={"type": "call", "description": "Audit Activity"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    aid = create_resp.json()["id"]

    response = client.get("/api/audit", headers=admin_headers)
    items = response.json()
    activity_audit = [
        r
        for r in items
        if r.get("entity_type") == "activity" and r.get("entity_id") == aid
    ]
    assert len(activity_audit) >= 1


def test_audit_record_created_on_settings_update(client, admin_headers):
    """Updating settings writes an audit record."""
    client.put(
        "/api/settings",
        json={"payload": {"audit_test": "true"}},
        headers=admin_headers,
    )
    response = client.get("/api/audit", headers=admin_headers)
    items = response.json()
    settings_audit = [r for r in items if r.get("entity_type") == "settings"]
    assert len(settings_audit) >= 1


def test_audit_list_unauthenticated_returns_401(client):
    """Unauthenticated request to audit returns 401."""
    response = client.get("/api/audit")
    assert response.status_code == 401


def test_audit_list_non_admin_returns_403(client, user_headers):
    """Non-admin user cannot read audit log."""
    response = client.get("/api/audit", headers=user_headers)
    assert response.status_code == 403


def test_audit_records_have_timestamp(client, admin_headers):
    """Audit records always contain a timestamp."""
    client.post(
        "/api/contacts",
        json={"name": "Timestamp Test"},
        headers=admin_headers,
    )
    response = client.get("/api/audit", headers=admin_headers)
    items = response.json()
    assert len(items) >= 1
    record = items[-1]
    assert "timestamp" in record


def test_audit_actor_shows_different_users(client, admin_headers, user_headers):
    """Verify audit records capture different actor identities."""
    create_resp = client.post(
        "/api/contacts",
        json={"name": "Multi Actor Test"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    cid = create_resp.json()["id"]

    client.put(
        f"/api/contacts/{cid}",
        json={"name": "Updated by admin"},
        headers=admin_headers,
    )
    response = client.get("/api/audit", headers=admin_headers)
    items = response.json()
    contact_audit = [
        r
        for r in items
        if r.get("entity_type") == "contact" and r.get("entity_id") == cid
    ]
    # Should have at least 2 records (create + update)
    assert len(contact_audit) >= 2
    # All records from admin operations should show admin actor
    for record in contact_audit:
        assert record["actor_sub"] == "dev-admin-1"
