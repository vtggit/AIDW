"""Worker claim/execute/reap loop.

The claim is the canonical Postgres job-queue pattern: one atomic UPDATE whose target row is
picked by a ``FOR UPDATE SKIP LOCKED`` subselect — concurrent workers skip each other's locked
rows, so every pending run is claimed by exactly one executor (probe R1 from the architecture
doc, proven live by the two-connection test). Execution is ``app.ingest.service.execute_run``
with ``claimed=True`` — the run row is already ``running``. The reaper enforces the run-spine
invariant fleet-wide: a ``running`` row whose executor died (crash, OOM, kill -9) is finalized
``failed`` instead of sitting corrupt forever; ``updated_at`` is the liveness signal (the claim
touches it, and one run is a single bounded fetch + apply, so a generous cutoff cannot reap a
live run).
"""

import contextlib
import logging
import os
import signal
import time
from datetime import datetime, timedelta, timezone

from app.db.connection import get_cursor
from app.ingest.service import execute_run

logger = logging.getLogger(__name__)

POLL_SECONDS = float(os.getenv("WORKER_POLL_SECONDS", "5"))
STALE_RUNNING_SECONDS = int(os.getenv("WORKER_STALE_RUNNING_SECONDS", "1800"))


def claim_next() -> str | None:
    """Atomically claim the oldest pending run (pending→running). Returns its id, or None when
    the queue is empty or every pending row is locked by another worker."""
    now = datetime.now(timezone.utc)
    with get_cursor() as cur:
        cur.execute(
            "UPDATE runs SET status = 'running', started_at = %s, updated_at = %s "
            "WHERE id = ("
            "  SELECT id FROM runs WHERE status = 'pending' "
            "  ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1"
            ") RETURNING id",
            (now, now),
        )
        row = cur.fetchone()
    return row["id"] if row else None


def run_once() -> dict | None:
    """Claim and execute one pending run. Returns the finished run body, or None when there was
    nothing to claim."""
    run_id = claim_next()
    if run_id is None:
        return None
    logger.info("claimed run %s", run_id)
    return execute_run(run_id, claimed=True)


def reap_stale_running(max_age_seconds: int | None = None) -> int:
    """Finalize ``running`` rows whose executor died: older than the cutoff → ``failed`` with an
    explicit error_detail. Returns the number reaped."""
    cutoff_age = STALE_RUNNING_SECONDS if max_age_seconds is None else max_age_seconds
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=cutoff_age)
    with get_cursor() as cur:
        cur.execute(
            "UPDATE runs SET status = 'failed', error_detail = %s, finished_at = %s, "
            "updated_at = %s WHERE status = 'running' AND updated_at < %s",
            (
                "reaped: executor did not finish (stale running row)",
                now,
                now,
                cutoff,
            ),
        )
        reaped = cur.rowcount
    if reaped:
        logger.warning("reaped %d stale running run(s)", reaped)
    return reaped


def main_loop(
    poll_seconds: float | None = None, max_iterations: int | None = None
) -> None:
    """Reap, drain the queue, sleep, repeat — until SIGTERM/SIGINT (or max_iterations, for
    tests). Sleeps in short slices so a stop signal lands promptly."""
    poll = POLL_SECONDS if poll_seconds is None else poll_seconds
    stop = {"requested": False}

    def _request_stop(*_args) -> None:
        stop["requested"] = True

    previous_handlers = {}
    # ValueError = not the main thread (tests) — rely on max_iterations instead of signals
    with contextlib.suppress(ValueError):
        for sig in (signal.SIGTERM, signal.SIGINT):
            previous_handlers[sig] = signal.getsignal(sig)
            signal.signal(sig, _request_stop)

    logger.info(
        "worker started (poll=%ss, stale-cutoff=%ss)", poll, STALE_RUNNING_SECONDS
    )
    iterations = 0
    try:
        while not stop["requested"]:
            if max_iterations is not None and iterations >= max_iterations:
                break
            iterations += 1
            try:
                reap_stale_running()
                while not stop["requested"] and run_once() is not None:
                    pass  # drain everything that is ready
            except Exception:
                # one bad iteration (db blip, unexpected error) must not kill the process
                logger.exception("worker iteration failed")
            deadline = time.monotonic() + poll
            while not stop["requested"] and time.monotonic() < deadline:
                time.sleep(min(0.2, poll))
    finally:
        # restore whatever handlers we displaced (pytest's SIGINT handling, notably)
        for sig, handler in previous_handlers.items():
            with contextlib.suppress(ValueError, TypeError):
                signal.signal(sig, handler)
    logger.info("worker stopped")
