"""Retention sweep reaper — closes the executor's claim-window gap (PR #122 v1 note).

A crash between the executor's claim commit (pending -> running) and its finish commit leaves a
retention_runs row stuck at running forever: no code path can re-drive it (the claim wants
pending, the finish guard wants running in the same process). Mirroring the ingest reaper,
reap_stale_sweeps closes that window after the fact — stale running rows become failed with a
reaped error_detail, so the audit spine records the truth instead of a permanent lie.
updated_at is the liveness signal (the executor touches it at claim time)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db.connection import get_cursor

DEFAULT_MAX_AGE_SECONDS = 900


def reap_stale_sweeps(max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS) -> int:
    """Mark every retention_runs row stuck in running whose updated_at is older than the
    threshold as failed (error_detail names the reap). Younger running rows and terminal rows
    are untouched. Returns the number of rows reaped."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=max_age_seconds)
    with get_cursor() as cur:
        cur.execute(
            "UPDATE retention_runs SET status = 'failed', error_detail = %s, updated_at = %s "
            "WHERE status = 'running' AND updated_at < %s",
            (f"reaped: stale running sweep (idle > {max_age_seconds}s)", now, cutoff),
        )
        return cur.rowcount
