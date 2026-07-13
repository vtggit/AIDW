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
from app.governance.executor import execute_deletion
from app.ingest.service import execute_run

logger = logging.getLogger(__name__)

POLL_SECONDS = float(os.getenv("WORKER_POLL_SECONDS", "5"))
STALE_RUNNING_SECONDS = int(os.getenv("WORKER_STALE_RUNNING_SECONDS", "1800"))
DELETION_MAX_ATTEMPTS = 5  # beyond this the request sits for operator triage (#76)


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


def claim_next_deletion() -> tuple[str, int] | None:
    """Atomically claim the oldest verified deletion request (verifying→executing) — the
    second claim spine (#76), same SKIP LOCKED shape as runs. Returns (id, generation):
    the generation (the row's attempts value) fences the executor's finalize and reset per
    the BEHAVIORAL-ARCHITECTURE guard. Requests at the attempts cap are left for triage.
    """
    with get_cursor() as cur:
        cur.execute(
            "UPDATE deletion_requests SET status = 'executing', updated_at = NOW() "
            "WHERE id = ("
            "  SELECT id FROM deletion_requests "
            "  WHERE status = 'verifying' AND COALESCE(attempts, 0) < %s "
            "  ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1"
            ") RETURNING id, COALESCE(attempts, 0) AS attempts",
            (DELETION_MAX_ATTEMPTS,),
        )
        row = cur.fetchone()
    return (row["id"], row["attempts"]) if row else None


def deletions_once() -> bool:
    """Claim and execute one verified deletion request. False when there was nothing to
    claim. Failures inside execute_deletion requeue themselves (retry-not-fail)."""
    claimed = claim_next_deletion()
    if claimed is None:
        return False
    request_id, generation = claimed
    logger.info("claimed deletion request %s (generation %d)", request_id, generation)
    execute_deletion(request_id, claimed=True, generation=generation)
    return True


def reap_stale_executing(max_age_seconds: int | None = None) -> int:
    """Retry-not-fail (#76): a stale ``executing`` deletion request goes BACK to
    ``verifying`` with attempts+1 — erasure is idempotent, so the next claim re-runs it
    safely (contrast runs, whose reaper finalizes ``failed``)."""
    cutoff_age = STALE_RUNNING_SECONDS if max_age_seconds is None else max_age_seconds
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=cutoff_age)
    with get_cursor() as cur:
        cur.execute(
            "UPDATE deletion_requests SET status = 'verifying', "
            "attempts = COALESCE(attempts, 0) + 1, error_detail = %s, updated_at = NOW() "
            "WHERE status = 'executing' AND updated_at < %s",
            ("reaped: executor did not finish (stale executing row)", cutoff),
        )
        reaped = cur.rowcount
    if reaped:
        logger.warning("reaped %d stale executing deletion request(s)", reaped)
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
                reap_stale_executing()
                while not stop["requested"] and run_once() is not None:
                    pass  # drain everything that is ready
                while not stop["requested"] and deletions_once():
                    pass  # then the deletion queue (#76 second claim spine)
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
