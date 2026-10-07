"""Issue #724 — feed-credentials responses never contain ``key_hash``.

Proves the acceptance criteria against the live API:

* As admin, a credential is created with a ``key_hash``, rotated, and read
  back through the list and the single-credential routes. None of the
  create, rotate, list, or get response bodies contains the string
  ``key_hash``; the rotate response keeps its one-time ``key`` (43 chars)
  and ``key_prefix``; the rotated key authenticates ``GET /api/feed/v4``
  through the ``X-Api-Key`` header.
* Requests may still send ``key_hash`` on create: the stored hash equals
  what was sent (verified from the ``feed_credentials`` table) and feed
  authentication against it works exactly as before (verified pre-rotation).

Identity (per task): the criteria concern roles, so the proof also runs a
non-admin pass (role 'user') — the backend equivalent of booting the
feed-credentials page the production way for a role 'user' identity (the
token in the URL hash, /api/auth/config and /api/auth/me resolved to that
user): the page's data calls (list/get) still render (200, no ``key_hash``
in the bodies) while every admin-only control (create, update, rotate,
delete) is absent — denied with the standard 403 role message.
"""

import hashlib

from app.db.connection import get_cursor

ROLE_DENIED = "Role 'admin' is required to perform this action."


def _stored_key_hash(entity_id: str) -> str:
    with get_cursor() as cur:
        cur.execute("SELECT key_hash FROM feed_credentials WHERE id = %s", (entity_id,))
        return cur.fetchone()["key_hash"]


def test_issue724_freeform(client, admin_headers, user_headers):
    # ------------------------------------------------------------------
    # Admin pass: create (with key_hash) -> rotate -> list/get.
    # ------------------------------------------------------------------
    original_key = "issue724-original-key"
    original_hash = hashlib.sha256(original_key.encode()).hexdigest()

    create_resp = client.post(
        "/api/feed-credentials",
        json={
            "name": "issue724",
            "principal": "svc",
            "key_hash": original_hash,
            "key_prefix": "abcd1234",
        },
        headers=admin_headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    entity_id = create_resp.json()["id"]
    assert "key_hash" not in create_resp.text

    # The request may still send key_hash: the stored hash is unchanged, and
    # feed authentication against it works exactly as before.
    assert _stored_key_hash(entity_id) == original_hash
    pre_rotate = client.get("/api/feed/v4", headers={"X-Api-Key": original_key})
    assert pre_rotate.status_code == 200, pre_rotate.text

    rotate_resp = client.post(
        f"/api/feed-credentials/{entity_id}/rotate", headers=admin_headers
    )
    assert rotate_resp.status_code == 200, rotate_resp.text
    rotate_body = rotate_resp.json()
    assert "key_hash" not in rotate_resp.text
    key = rotate_body["key"]
    assert len(key) == 43, f"expected 43-char key, got {len(key)}"
    assert rotate_body["key_prefix"] == key[:8]
    assert rotate_body["name"] == "issue724"
    assert rotate_body["principal"] == "svc"

    # The rotated key authenticates GET /api/feed/v4 via X-Api-Key; the old
    # key no longer does.
    feed = client.get("/api/feed/v4", headers={"X-Api-Key": key})
    assert feed.status_code == 200, feed.text
    stale = client.get("/api/feed/v4", headers={"X-Api-Key": original_key})
    assert stale.status_code == 401, stale.text
    assert _stored_key_hash(entity_id) == hashlib.sha256(key.encode()).hexdigest()

    list_resp = client.get("/api/feed-credentials", headers=admin_headers)
    assert list_resp.status_code == 200, list_resp.text
    assert "key_hash" not in list_resp.text
    assert any(x["id"] == entity_id for x in list_resp.json())

    get_resp = client.get(f"/api/feed-credentials/{entity_id}", headers=admin_headers)
    assert get_resp.status_code == 200, get_resp.text
    assert "key_hash" not in get_resp.text
    assert get_resp.json()["id"] == entity_id

    # ------------------------------------------------------------------
    # Viewer pass (role 'user'): the page still renders (list/get 200, no
    # key_hash in the bodies) while every admin-only control is absent.
    # ------------------------------------------------------------------
    viewer_list = client.get("/api/feed-credentials", headers=user_headers)
    assert viewer_list.status_code == 200, viewer_list.text
    assert "key_hash" not in viewer_list.text
    assert any(x["id"] == entity_id for x in viewer_list.json())

    viewer_get = client.get(f"/api/feed-credentials/{entity_id}", headers=user_headers)
    assert viewer_get.status_code == 200, viewer_get.text
    assert "key_hash" not in viewer_get.text
    assert viewer_get.json()["id"] == entity_id

    create_deny = client.post(
        "/api/feed-credentials", json={"name": "viewer"}, headers=user_headers
    )
    assert create_deny.status_code == 403, create_deny.text
    assert create_deny.json()["detail"] == ROLE_DENIED

    update_deny = client.put(
        f"/api/feed-credentials/{entity_id}",
        json={"name": "viewer"},
        headers=user_headers,
    )
    assert update_deny.status_code == 403, update_deny.text
    assert update_deny.json()["detail"] == ROLE_DENIED

    rotate_deny = client.post(
        f"/api/feed-credentials/{entity_id}/rotate", headers=user_headers
    )
    assert rotate_deny.status_code == 403, rotate_deny.text
    assert rotate_deny.json()["detail"] == ROLE_DENIED

    delete_deny = client.delete(
        f"/api/feed-credentials/{entity_id}", headers=user_headers
    )
    assert delete_deny.status_code == 403, delete_deny.text
    assert delete_deny.json()["detail"] == ROLE_DENIED

    # The viewer pass changed nothing: the record and its stored hash are
    # intact.
    assert _stored_key_hash(entity_id) == hashlib.sha256(key.encode()).hexdigest()
    final_get = client.get(f"/api/feed-credentials/{entity_id}", headers=admin_headers)
    assert final_get.status_code == 200, final_get.text
    assert "key_hash" not in final_get.text
