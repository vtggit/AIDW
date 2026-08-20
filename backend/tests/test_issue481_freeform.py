"""Proving test for issue #481 — status filtering on GET /api/sequence-runs.

Exercises three cases:
1. A matched status returns only matching runs and X-Total-Count equals the matched count.
2. An unmatched status returns an empty list with X-Total-Count 0.
3. Status combined with limit=1 returns one matching row while X-Total-Count still reports
   the full filtered count.
"""


def _create_run(client, admin_headers, name, status):
    resp = client.post(
        "/api/sequence-runs",
        headers=admin_headers,
        json={"name": name, "status": status},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_issue481_freeform(client, admin_headers):
    # Seed runs across two statuses.
    _create_run(client, admin_headers, "run-a", "succeeded")
    _create_run(client, admin_headers, "run-b", "succeeded")
    _create_run(client, admin_headers, "run-c", "failed")

    # Case 1: matched status returns only matching runs; X-Total-Count == matched count.
    resp = client.get(
        "/api/sequence-runs",
        headers=admin_headers,
        params={"status": "succeeded"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 2
    assert all(r["status"] == "succeeded" for r in body)
    assert resp.headers["X-Total-Count"] == "2"

    # Case 2: unmatched status returns an empty list with X-Total-Count 0.
    resp = client.get(
        "/api/sequence-runs",
        headers=admin_headers,
        params={"status": "running"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == []
    assert resp.headers["X-Total-Count"] == "0"

    # Case 3: status combined with limit=1 returns one matching row; X-Total-Count
    # still reports the full filtered count.
    resp = client.get(
        "/api/sequence-runs",
        headers=admin_headers,
        params={"status": "succeeded", "limit": 1},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["status"] == "succeeded"
    assert resp.headers["X-Total-Count"] == "2"
