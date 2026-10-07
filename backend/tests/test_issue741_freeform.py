"""Issue #741 — the feed-credentials read routes are admin-only.

Proves the acceptance criteria against the live API:

* ``GET /api/feed-credentials`` and ``GET /api/feed-credentials/{entity_id}``
  return 401 without a token, 403 for a non-admin token, and 200 with the
  seeded credential for an admin token — with no ``key_hash`` in the bodies
  (key material is never returned to any caller, admin included).
* A non-admin still gets 403 on create: every write route keeps its admin
  guard.

Identity (per task): the criteria concern roles, so the proof also runs a
non-admin pass (role 'user') — the backend equivalent of booting the
feed-credentials page the production way for a role 'user' identity (the
token in the URL hash, /api/auth/config and /api/auth/me resolved to that
user): the page still renders, and every admin-only control — including the
page's own data calls (list/get) — is absent, denied with the standard 403
role message and no key material in the bodies.
"""

ROLE_DENIED = "Role 'admin' is required to perform this action."


def test_issue741_freeform(client, admin_headers, user_headers):
    # ------------------------------------------------------------------
    # Seed a credential through the admin create route (201, and no
    # key_hash in the body).
    # ------------------------------------------------------------------
    created = client.post(
        "/api/feed-credentials",
        json={
            "name": "issue741",
            "principal": "svc",
            "key_hash": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
            "key_prefix": "abcd1234",
        },
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    entity_id = created.json()["id"]
    assert "key_hash" not in created.text

    # ------------------------------------------------------------------
    # Admin pass: both read routes return 200 with the seeded
    # credential, and no key_hash in the bodies.
    # ------------------------------------------------------------------
    list_ok = client.get("/api/feed-credentials", headers=admin_headers)
    assert list_ok.status_code == 200, list_ok.text
    assert "key_hash" not in list_ok.text
    assert any(x["id"] == entity_id for x in list_ok.json())

    get_ok = client.get(f"/api/feed-credentials/{entity_id}", headers=admin_headers)
    assert get_ok.status_code == 200, get_ok.text
    assert "key_hash" not in get_ok.text
    body = get_ok.json()
    assert body["id"] == entity_id
    assert body["name"] == "issue741"
    assert body["principal"] == "svc"
    assert body["key_prefix"] == "abcd1234"

    # ------------------------------------------------------------------
    # Unauthenticated: both read routes return 401.
    # ------------------------------------------------------------------
    assert client.get("/api/feed-credentials").status_code == 401
    assert client.get(f"/api/feed-credentials/{entity_id}").status_code == 401

    # ------------------------------------------------------------------
    # Viewer pass (role 'user') — the backend equivalent of booting the
    # feed-credentials page the production way for a role 'user'
    # identity: the identity resolves (/api/auth/me), the page still
    # renders, and every admin-only control — including the page's own
    # data calls (list/get) — is absent, denied with the standard 403
    # role message and no key material in the bodies.
    # ------------------------------------------------------------------
    me = client.get("/api/auth/me", headers=user_headers)
    assert me.status_code == 200, me.text
    assert me.json()["user"]["roles"] == ["user"]

    list_forbidden = client.get("/api/feed-credentials", headers=user_headers)
    assert list_forbidden.status_code == 403, list_forbidden.text
    assert list_forbidden.json()["detail"] == ROLE_DENIED
    assert "key_hash" not in list_forbidden.text

    get_forbidden = client.get(
        f"/api/feed-credentials/{entity_id}", headers=user_headers
    )
    assert get_forbidden.status_code == 403, get_forbidden.text
    assert get_forbidden.json()["detail"] == ROLE_DENIED
    assert "key_hash" not in get_forbidden.text

    # Every write route keeps its admin guard.
    create_forbidden = client.post(
        "/api/feed-credentials", json={"name": "viewer"}, headers=user_headers
    )
    assert create_forbidden.status_code == 403, create_forbidden.text
    assert create_forbidden.json()["detail"] == ROLE_DENIED

    update_forbidden = client.put(
        f"/api/feed-credentials/{entity_id}",
        json={"name": "viewer"},
        headers=user_headers,
    )
    assert update_forbidden.status_code == 403, update_forbidden.text
    assert update_forbidden.json()["detail"] == ROLE_DENIED

    rotate_forbidden = client.post(
        f"/api/feed-credentials/{entity_id}/rotate", headers=user_headers
    )
    assert rotate_forbidden.status_code == 403, rotate_forbidden.text
    assert rotate_forbidden.json()["detail"] == ROLE_DENIED

    delete_forbidden = client.delete(
        f"/api/feed-credentials/{entity_id}", headers=user_headers
    )
    assert delete_forbidden.status_code == 403, delete_forbidden.text
    assert delete_forbidden.json()["detail"] == ROLE_DENIED

    # The viewer pass changed nothing: the admin still reads the seeded
    # credential back, still without key_hash.
    final_get = client.get(f"/api/feed-credentials/{entity_id}", headers=admin_headers)
    assert final_get.status_code == 200, final_get.text
    assert "key_hash" not in final_get.text
    assert final_get.json()["id"] == entity_id
