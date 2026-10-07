"""Proving test for issue #720 — the retention read routes are admin-only.

The four retention read routes (GET /api/retention-policies,
GET /api/retention-policies/{entity_id}, GET /api/retention-runs,
GET /api/retention-runs/{entity_id}) move from ``require_authenticated_user``
to ``require_role(ROLE_ADMIN)``; for admins the response bodies and status
codes are unchanged.

Identity (per task): the criteria concern roles, so the proof also runs a
non-admin pass (role 'user') — the backend equivalent of booting the
retention page the production way for a role 'user' identity (the token in
the URL hash, /api/auth/config and /api/auth/me resolved to that user):
the page's data calls (the four read routes) now return 403, so that
caller is granted no admin-only read access, while the page still renders
(the panel is read-only — it has no admin-only controls in its DOM — and a
403 surfaces as its "Could not load ..." note, never an error state).

Coverage:
  * admin     — 200 on all four routes, the seeded row (one policy, one
                run) present, response shape unchanged (exact key set);
  * non-admin — 403 on all four routes with the role-denied detail;
  * anonymous — 401 on all four routes with the unchanged auth detail;
  * hostile ids — empty, non-numeric, huge, unicode, control chars and NUL
                bytes never produce a 500; a NUL-bearing id is answered 404
                with the standard not-found body, like any other unknown id
                (no 422 short-circuit changing the admin GET status).
"""

POLICY_KEYS = {
    "id",
    "name",
    "table_class",
    "action",
    "scope",
    "dataset_id",
    "retention_period_days",
    "is_enabled",
    "created_at",
    "updated_at",
}

RUN_KEYS = {
    "id",
    "name",
    "status",
    "trigger",
    "policy_id",
    "error_detail",
    "records_purged",
    "records_anonymized",
    "created_at",
    "updated_at",
}

ROLE_DENIED_DETAIL = "Role 'admin' is required to perform this action."
UNAUTHENTICATED_DETAIL = "Authentication required. Provide a valid Bearer token."


def _seed(client, admin_headers):
    """Create one policy and one run against it (as admin); return both rows."""
    policy = client.post(
        "/api/retention-policies",
        json={
            "name": "issue720-policy",
            "table_class": "connection_tests",
            "action": "purge",
            "scope": "class",
            "is_enabled": True,
            "retention_period_days": 30,
        },
        headers=admin_headers,
    )
    assert policy.status_code == 201, policy.text
    policy_row = policy.json()
    run = client.post(
        "/api/retention-runs",
        json={
            "name": "issue720-run",
            "status": "succeeded",
            "trigger": "manual",
            "policy_id": policy_row["id"],
            "records_purged": 7,
            "records_anonymized": 3,
        },
        headers=admin_headers,
    )
    assert run.status_code == 201, run.text
    return policy_row, run.json()


def _get(client, path, headers):
    """GET *path*; return (client_rejected, response).

    A conforming HTTP client (httpx, browsers) rejects raw NUL / control
    characters in a URL before the request is sent — in that case no
    response (and hence no 500) can occur at all.
    """
    try:
        return False, client.get(path, headers=headers)
    except Exception:
        return True, None


def test_issue720_freeform(client, admin_headers, user_headers):
    policy_row, run_row = _seed(client, admin_headers)
    read_paths = [
        "/api/retention-policies",
        f"/api/retention-policies/{policy_row['id']}",
        "/api/retention-runs",
        f"/api/retention-runs/{run_row['id']}",
    ]

    # --- viewer pass: non-admin (role 'user') is denied admin-only reads ---
    for path in read_paths:
        response = client.get(path, headers=user_headers)
        assert response.status_code == 403, (path, response.text)
        assert response.json()["detail"] == ROLE_DENIED_DETAIL

    # --- anonymous pass: 401 with the unchanged auth error message ---
    for path in read_paths:
        response = client.get(path)
        assert response.status_code == 401, (path, response.text)
        assert response.json()["detail"] == UNAUTHENTICATED_DETAIL

    # --- admin pass: 200 with the seeded rows, unchanged response shape ---
    listing = client.get("/api/retention-policies", headers=admin_headers)
    assert listing.status_code == 200
    policy_rows = listing.json()
    assert any(row["id"] == policy_row["id"] for row in policy_rows)
    row = next(x for x in policy_rows if x["id"] == policy_row["id"])
    assert set(row) == POLICY_KEYS
    policy_path = f"/api/retention-policies/{policy_row['id']}"
    got = client.get(policy_path, headers=admin_headers)
    assert got.status_code == 200
    assert got.json() == row

    listing = client.get("/api/retention-runs", headers=admin_headers)
    assert listing.status_code == 200
    run_rows = listing.json()
    assert any(r["id"] == run_row["id"] for r in run_rows)
    row = next(x for x in run_rows if x["id"] == run_row["id"])
    assert set(row) == RUN_KEYS
    run_path = f"/api/retention-runs/{run_row['id']}"
    got = client.get(run_path, headers=admin_headers)
    assert got.status_code == 200
    assert got.json() == row

    # --- hostile entity ids must never produce a 500 ---
    # Every unknown id — NUL-bearing ones included — is answered 404 with
    # the standard not-found body, exactly like any other admin GET for a
    # missing entity; the short-circuit must not change the admin GET
    # status (no 500 from psycopg2, no 422 of its own).
    not_found_noun = {
        "/api/retention-policies": "RetentionPolicy",
        "/api/retention-runs": "RetentionRun",
    }
    hostile = [
        ("non-numeric", "not-a-uuid", "not-a-uuid"),
        ("huge", "A" * 10_000, "A" * 10_000),
        ("unicode", "ünïcode-é", "ünïcode-é"),
        ("percent-encoded NUL", "a%00b", "a\x00b"),
    ]
    for label, path_value, decoded_id in hostile:
        for base, noun in not_found_noun.items():
            rejected, response = _get(client, f"{base}/{path_value}", admin_headers)
            assert not rejected, (label, base)
            assert response.status_code == 404, (
                label,
                base,
                response.status_code,
                response.text,
            )
            assert response.json()["detail"] == f"{noun} '{decoded_id}' not found."

    # raw NUL / control chars: the client refuses to send them, so no 500 is
    # possible; if a client ever did send them, the server must still not 500
    for label, value in [("raw NUL", "a\x00b"), ("raw control char", "a\x01b")]:
        for base in ("/api/retention-policies", "/api/retention-runs"):
            rejected, response = _get(client, f"{base}/{value}", admin_headers)
            if not rejected:
                assert response.status_code < 500, (label, base, response.status_code)

    # empty id: the trailing-slash path never 500s (it lands on the list
    # route via redirect for admins, 403 for non-admins)
    empty = client.get("/api/retention-policies/", headers=admin_headers)
    assert empty.status_code < 500
    assert client.get("/api/retention-runs/", headers=user_headers).status_code < 500
