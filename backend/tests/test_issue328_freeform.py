"""Proving test for Issue #328 — scoped dashboard-item-layout operations.

Verifies that every dashboard-item-layout operation is scoped to the
authenticated caller: a viewer can save their own tile arrangement without
an administrator and without seeing or altering anyone else's rows.
"""


def test_issue328_freeform(client, admin_headers, user_headers):
    """End-to-end proof of scoped-write behaviour for dashboard-item-layouts."""

    # 1. A non-admin (viewer) can create their own layout — no admin role needed
    viewer_create = client.post(
        "/api/dashboard-item-layouts",
        json={"name": "viewer layout"},
        headers=user_headers,
    )
    assert viewer_create.status_code == 201
    viewer_layout = viewer_create.json()
    viewer_layout_id = viewer_layout["id"]

    # 2. The stored user_id is derived from the token subject, never from payload
    assert viewer_layout["user_id"] is not None

    # 3. Admin creates their own layout (different caller → different user_id)
    admin_create = client.post(
        "/api/dashboard-item-layouts",
        json={"name": "admin layout"},
        headers=admin_headers,
    )
    assert admin_create.status_code == 201
    admin_layout = admin_create.json()
    admin_layout_id = admin_layout["id"]

    # Admin and viewer have distinct user_ids (different token subjects)
    assert viewer_layout["user_id"] != admin_layout["user_id"]

    # 4. Listing returns only the caller's own rows
    viewer_list = client.get("/api/dashboard-item-layouts", headers=user_headers)
    viewer_list_ids = [layout_record["id"] for layout_record in viewer_list.json()]
    assert viewer_layout_id in viewer_list_ids
    assert admin_layout_id not in viewer_list_ids

    admin_list = client.get("/api/dashboard-item-layouts", headers=admin_headers)
    admin_list_ids = [layout_record["id"] for layout_record in admin_list.json()]
    assert admin_layout_id in admin_list_ids
    assert viewer_layout_id not in admin_list_ids

    # 5. Fetching another user's row is refused (404 — scoped to caller)
    cross_get = client.get(
        f"/api/dashboard-item-layouts/{admin_layout_id}", headers=user_headers
    )
    assert cross_get.status_code == 404

    # 6. Updating another user's row is refused
    cross_update = client.put(
        f"/api/dashboard-item-layouts/{admin_layout_id}",
        json={"name": "hijacked"},
        headers=user_headers,
    )
    assert cross_update.status_code == 404

    # 7. Deleting another user's row is refused
    cross_delete = client.delete(
        f"/api/dashboard-item-layouts/{admin_layout_id}", headers=user_headers
    )
    assert cross_delete.status_code == 404

    # 8. Viewer can update their own layout
    viewer_update = client.put(
        f"/api/dashboard-item-layouts/{viewer_layout_id}",
        json={"name": "updated viewer layout"},
        headers=user_headers,
    )
    assert viewer_update.status_code == 200
    assert viewer_update.json()["name"] == "updated viewer layout"

    # 9. Viewer can delete their own layout
    viewer_delete = client.delete(
        f"/api/dashboard-item-layouts/{viewer_layout_id}", headers=user_headers
    )
    assert viewer_delete.status_code == 204

    # Verify deletion took effect
    gone = client.get(
        f"/api/dashboard-item-layouts/{viewer_layout_id}", headers=user_headers
    )
    assert gone.status_code == 404
