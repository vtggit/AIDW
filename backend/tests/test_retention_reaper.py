"""Retention sweep reaper (issue #133) — stale running runs become failed; nothing else moves."""

import uuid
from datetime import datetime, timedelta, timezone


def _seed_run(run_id, status, updated_at):
    from app.db.connection import get_cursor

    now = datetime.now(timezone.utc)
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO retention_runs (id, name, status, trigger, created_at, updated_at) "
            "VALUES (%s, %s, %s, 'manual', %s, %s)",
            (run_id, f"reaper-seed {run_id[:8]}", status, now, updated_at),
        )


def _get(run_id):
    from app.db.connection import get_cursor

    with get_cursor() as cur:
        cur.execute(
            "SELECT status, error_detail FROM retention_runs WHERE id = %s", (run_id,)
        )
        return dict(cur.fetchone())


def test_reaper_fails_only_stale_running_runs(client, admin_headers):
    from app.retention.reaper import reap_stale_sweeps

    now = datetime.now(timezone.utc)
    stale_running = uuid.uuid4().hex
    fresh_running = uuid.uuid4().hex
    stale_done = uuid.uuid4().hex
    _seed_run(stale_running, "running", now - timedelta(seconds=3600))
    _seed_run(fresh_running, "running", now - timedelta(seconds=10))
    _seed_run(stale_done, "succeeded", now - timedelta(seconds=3600))

    reaped = reap_stale_sweeps(max_age_seconds=900)

    assert reaped == 1
    got = _get(stale_running)
    assert got["status"] == "failed" and "reaped" in got["error_detail"]
    assert _get(fresh_running)["status"] == "running"  # younger: untouched
    assert _get(stale_done)["status"] == "succeeded"  # terminal: untouched
    # idempotent: nothing left to reap
    assert reap_stale_sweeps(max_age_seconds=900) == 0
