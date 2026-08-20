"""Issue #489 — GET /api/sequence-runs pagination validation + X-Total-Count.

Proves:
  * limit outside 1..100 -> 422 naming 'limit'
  * offset below 0 -> 422 naming 'offset'
  * no offset/limit/status -> 200 with the full list (behavior unchanged)
  * every 200 list response without a status filter carries X-Total-Count equal to the
    unfiltered total
  * the status-filtered path keeps carrying X-Total-Count equal to the filtered total
"""

import uuid

from app.db.connection import get_cursor


def _create_sequence_run(name: str, status_value: str | None = None) -> str:
    """Insert a sequence_runs row directly and return its id."""
    run_id = str(uuid.uuid4())
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO sequence_runs (id, name, status, created_at, updated_at) "
            "VALUES (%s, %s, %s, NOW(), NOW())",
            (run_id, name, status_value),
        )
    return run_id


def _clear_sequence_runs() -> None:
    """Remove all sequence_runs rows so the test's counts are self-contained.

    The session-wide clean_database fixture only truncates audit_log, so
    sequence_runs rows persist across tests; clear them here so the
    assertions below hold regardless of prior test state.
    """
    with get_cursor() as cur:
        cur.execute("DELETE FROM sequence_runs")


def test_issue489_freeform(client, admin_headers):
    # Start from a clean slate so the seeded counts are exact.
    _clear_sequence_runs()

    # Seed a known set of rows: 3 'pending', 2 'succeeded', 1 'failed'.
    for i in range(3):
        _create_sequence_run(f"pending-run-{i}", "pending")
    for i in range(2):
        _create_sequence_run(f"succeeded-run-{i}", "succeeded")
    _create_sequence_run("failed-run-0", "failed")
    total = 6

    # --- limit out of range -> 422 naming 'limit' -------------------------
    for bad_limit in (0, 101, -5):
        resp = client.get(
            "/api/sequence-runs", params={"limit": bad_limit}, headers=admin_headers
        )
        assert (
            resp.status_code == 422
        ), f"limit={bad_limit} expected 422, got {resp.status_code}"
        body = resp.text
        assert "limit" in body, f"422 body must name 'limit': {body}"

    # --- offset below 0 -> 422 naming 'offset' ----------------------------
    for bad_offset in (-1, -10):
        resp = client.get(
            "/api/sequence-runs", params={"offset": bad_offset}, headers=admin_headers
        )
        assert (
            resp.status_code == 422
        ), f"offset={bad_offset} expected 422, got {resp.status_code}"
        body = resp.text
        assert "offset" in body, f"422 body must name 'offset': {body}"

    # --- no offset, no limit, no status -> 200 with the full list ---------
    resp = client.get("/api/sequence-runs", headers=admin_headers)
    assert resp.status_code == 200
    rows = resp.json()
    assert isinstance(rows, list)
    assert len(rows) == total, f"expected full list of {total}, got {len(rows)}"
    # unfiltered 200 carries X-Total-Count equal to the unfiltered total
    assert resp.headers.get("X-Total-Count") == str(total)

    # --- valid windowed unfiltered request still 200 + unfiltered total ---
    resp = client.get(
        "/api/sequence-runs",
        params={"limit": 2, "offset": 1},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 2
    assert resp.headers.get("X-Total-Count") == str(total)

    # --- status-filtered path keeps X-Total-Count = filtered total --------
    resp = client.get(
        "/api/sequence-runs", params={"status": "pending"}, headers=admin_headers
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 3
    assert all(r.get("status") == "pending" for r in rows)
    assert resp.headers.get("X-Total-Count") == "3"

    # --- status-filtered + window still reports the filtered total --------
    resp = client.get(
        "/api/sequence-runs",
        params={"status": "succeeded", "limit": 1, "offset": 0},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert resp.headers.get("X-Total-Count") == "2"
