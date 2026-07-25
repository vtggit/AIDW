"""Proving test for Issue #333 — scoped-write identity protection.

Verifies that injecting a conflicting user_id in the request body is ignored
or rejected and does not override the authenticated caller's identity across
create/update operations on dashboard item layouts.
"""


def test_issue333_freeform(client, admin_headers, user_headers):
    """Negative integration test: payload user_id cannot hijack ownership."""

    # 1. Viewer creates a layout while supplying a mismatched user_id in the payload.
    # The service must ignore it and bind the row to the caller's token subject.
    viewer_create = client.post(
        "/api/dashboard-item-layouts",
        json={"name": "viewer scoped layout", "user_id": "malicious-other-user"},
        headers=user_headers,
    )
    assert viewer_create.status_code == 201
    viewer_layout = viewer_create.json()
    viewer_layout_id = viewer_layout["id"]

    # The stored user_id must be the caller's token subject, never the payload value.
    assert viewer_layout["user_id"] != "malicious-other-user"
    assert viewer_layout["user_id"] is not None

    # 2. Admin creates their own layout (also with a fake user_id in payload).
    admin_create = client.post(
        "/api/dashboard-item-layouts",
        json={"name": "admin scoped layout", "user_id": "another-malicious-user"},
        headers=admin_headers,
    )
    assert admin_create.status_code == 201
    admin_layout = admin_create.json()
    admin_layout_id = admin_layout["id"]

    # Admin and viewer have distinct user_ids derived from their tokens.
    assert viewer_layout["user_id"] != admin_layout["user_id"]

    # 3. Listing returns only the caller's own rows; foreign payload user_id did not leak.
    viewer_list = client.get("/api/dashboard-item-layouts", headers=user_headers)
    viewer_list_ids = [record["id"] for record in viewer_list.json()]
    assert admin_layout_id not in viewer_list_ids

    admin_list = client.get("/api/dashboard-item-layouts", headers=admin_headers)
    admin_list_ids = [record["id"] for record in admin_list.json()]
    assert viewer_layout_id not in admin_list_ids

    # 4. Updating an existing layout with a body carrying a foreign user_id must leave
    # the row owned by its original owner and still invisible to the other person.
    update_resp = client.put(
        f"/api/dashboard-item-layouts/{admin_layout_id}",
        json={"name": "updated admin layout", "user_id": viewer_layout["user_id"]},
        headers=admin_headers,
    )
    assert update_resp.status_code == 200
    updated_admin = update_resp.json()

    # Ownership must remain bound to the admin's token subject.
    assert updated_admin["user_id"] == admin_layout["user_id"]
    assert updated_admin["name"] == "updated admin layout"

    # 5. Verify it is still invisible to the other person after the update attempt.
    cross_get_after_update = client.get(
        f"/api/dashboard-item-layouts/{admin_layout_id}", headers=user_headers
    )
    assert cross_get_after_update.status_code == 404

    # Cleanup: delete own rows to keep DB clean for subsequent tests
    client.delete(
        f"/api/dashboard-item-layouts/{viewer_layout_id}", headers=user_headers
    )
    client.delete(
        f"/api/dashboard-item-layouts/{admin_layout_id}", headers=admin_headers
    )
