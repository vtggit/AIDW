"""Proving test for issue #536 — windowed listing + count for sequence-runs and load-sequences.

Covers the acceptance criteria:
- GET /api/sequence-runs applies an optional status filter, offset and limit in SQL, and
  sets X-Total-Count from a count that applies the same optional status.
- GET /api/load-sequences sets X-Total-Count from a count (not a second full materialisation).
- Ordering is verified by inserting rows in a physical order that DIFFERS from the
  created_at DESC order, so a missing ORDER BY would be detected.
"""

from datetime import datetime, timedelta, timezone

from app.db.connection import get_cursor


def _create_sequence_run(client, admin_headers, name, status, created_at):
    resp = client.post(
        "/api/sequence-runs",
        headers=admin_headers,
        json={"name": name, "status": status},
    )
    assert resp.status_code == 201, resp.text
    run_id = resp.json()["id"]
    with get_cursor() as cur:
        cur.execute(
            "UPDATE sequence_runs SET created_at = %s WHERE id = %s",
            (created_at, run_id),
        )
    return run_id


def _create_load_sequence(client, admin_headers, name, created_at):
    resp = client.post(
        "/api/load-sequences",
        headers=admin_headers,
        json={"name": name},
    )
    assert resp.status_code == 201, resp.text
    seq_id = resp.json()["id"]
    with get_cursor() as cur:
        cur.execute(
            "UPDATE load_sequences SET created_at = %s WHERE id = %s",
            (created_at, seq_id),
        )
    return seq_id


def test_issue536_freeform(client, admin_headers):
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)

    # Five sequence runs with distinct created_at timestamps and mixed statuses.
    # created_at DESC order: r1(+5) > r2(+4) > r3(+3) > r4(+2) > r5(+1).
    #
    # Insertion (physical) order is DELIBERATELY different from the expected
    # created_at DESC order so that a missing ORDER BY would be detected:
    #   physical: r3, r1, r5, r2, r4
    #   expected: r1, r2, r3, r4, r5
    _create_sequence_run(
        client, admin_headers, "r3", "succeeded", base + timedelta(minutes=3)
    )
    _create_sequence_run(
        client, admin_headers, "r1", "succeeded", base + timedelta(minutes=5)
    )
    _create_sequence_run(
        client, admin_headers, "r5", "succeeded", base + timedelta(minutes=1)
    )
    _create_sequence_run(
        client, admin_headers, "r2", "failed", base + timedelta(minutes=4)
    )
    _create_sequence_run(
        client, admin_headers, "r4", "failed", base + timedelta(minutes=2)
    )

    # --- Unfiltered listing: full body in created_at DESC order, X-Total-Count = 5 ---
    resp = client.get("/api/sequence-runs", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["X-Total-Count"] == "5"
    body = resp.json()
    assert [r["name"] for r in body] == ["r1", "r2", "r3", "r4", "r5"]

    # --- Windowed listing: limit + offset, X-Total-Count still the full total ---
    resp = client.get(
        "/api/sequence-runs",
        headers=admin_headers,
        params={"limit": 2, "offset": 1},
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["X-Total-Count"] == "5"
    body = resp.json()
    assert [r["name"] for r in body] == ["r2", "r3"]

    # --- Status filter: X-Total-Count reflects the filtered total ------------
    resp = client.get(
        "/api/sequence-runs",
        headers=admin_headers,
        params={"status": "succeeded"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["X-Total-Count"] == "3"
    body = resp.json()
    assert [r["name"] for r in body] == ["r1", "r3", "r5"]

    # --- Status filter + window: filtered total in header, windowed body -----
    resp = client.get(
        "/api/sequence-runs",
        headers=admin_headers,
        params={"status": "failed", "limit": 1, "offset": 0},
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["X-Total-Count"] == "2"
    body = resp.json()
    assert [r["name"] for r in body] == ["r2"]

    # --- 422 validation messages preserved -----------------------------------
    resp = client.get("/api/sequence-runs", headers=admin_headers, params={"limit": 0})
    assert resp.status_code == 422
    assert "limit" in resp.json()["detail"]

    resp = client.get(
        "/api/sequence-runs", headers=admin_headers, params={"limit": 101}
    )
    assert resp.status_code == 422
    assert "limit" in resp.json()["detail"]

    resp = client.get(
        "/api/sequence-runs", headers=admin_headers, params={"offset": -1}
    )
    assert resp.status_code == 422
    assert "offset" in resp.json()["detail"]

    # --- NUL byte in status must not crash (422, not 500) --------------------
    resp = client.get(
        "/api/sequence-runs",
        headers=admin_headers,
        params={"status": "\x00"},
    )
    assert resp.status_code == 422, resp.text

    # --- Load sequences: X-Total-Count from a count --------------------------
    # Insertion (physical) order differs from created_at DESC order:
    #   physical: ls2, ls3, ls1
    #   expected: ls1, ls2, ls3
    _create_load_sequence(client, admin_headers, "ls2", base + timedelta(minutes=2))
    _create_load_sequence(client, admin_headers, "ls3", base + timedelta(minutes=1))
    _create_load_sequence(client, admin_headers, "ls1", base + timedelta(minutes=3))

    resp = client.get("/api/load-sequences", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["X-Total-Count"] == "3"
    body = resp.json()
    assert [r["name"] for r in body] == ["ls1", "ls2", "ls3"]

    # Windowed load-sequences: header is the full count, body is the window.
    resp = client.get(
        "/api/load-sequences",
        headers=admin_headers,
        params={"limit": 2, "offset": 1},
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["X-Total-Count"] == "3"
    body = resp.json()
    assert [r["name"] for r in body] == ["ls2", "ls3"]
