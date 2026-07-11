"""Retention sweep execution (governance #80) — the sweeper's run state machine.

Mirrors the ingest run spine (``app.ingest.service``): ``create_pending_sweep`` writes the
``retention_runs`` audit row, ``execute_sweep`` atomically claims it (pending -> running, exactly
one executor wins) and executes; ANY execution failure lands ON the run (status=failed) rather
than raising, so a committed 'running' row is never left behind. The sweep itself is a direct
``DELETE`` below the policy's cutoff (``plan_sweep``): these are TEST databases by operator
decision, so the correctness rails stay (closed table allowlist, parameterized predicates,
fail-closed on unsupported action/scope) while backup/recovery machinery is deliberately absent.

The run row cannot yet carry failure detail (no error_detail column — a field-add lane
follow-up); failures are logged with the run id.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from app.db.connection import get_cursor
from app.retention.planner import plan_sweep

logger = logging.getLogger(__name__)

# The ONLY sweepable tables: table_class -> (has dataset_id, extra WHERE fragment). The policy's
# table_class is CHECK-constrained to this same set in the DB; the closed allowlist here keeps
# raw identifiers impossible in the DELETE even if the two ever drift. Run-spine tables carry a
# LIFECYCLE guard: `runs` is also the ingest worker's live queue (a pending row IS queued work,
# a running row is in-flight evidence) and discovery_runs mirrors that lifecycle — retention
# sweeps age out TERMINAL rows only, never live/queued ones. NULL-status rows stay sweepable
# (they are results, not queue entries).
_TERMINAL_ONLY = "AND (status IS NULL OR status NOT IN ('pending', 'running'))"
_SWEEPABLE = {
    "connection_tests": (False, None),
    "runs": (False, _TERMINAL_ONLY),
    "discovery_runs": (False, _TERMINAL_ONLY),
    "ingested_records": (True, None),
    "field_profiles": (False, None),
}


class SweepError(Exception):
    """A sweep precondition failed (unknown policy, unsupported action/scope, ...)."""


def create_pending_sweep(policy_id: str, trigger: str = "manual") -> dict:
    """Write the pending retention_runs row for one policy. Raises SweepError on an unknown
    policy (the caller 404s); everything else about the policy is judged at execution time so
    the run row records the outcome."""
    now = datetime.now(timezone.utc)
    run_id = str(uuid.uuid4())
    with get_cursor() as cur:
        cur.execute("SELECT id FROM retention_policies WHERE id = %s", (policy_id,))
        if cur.fetchone() is None:
            raise SweepError("no such retention policy: %s" % policy_id)
        cur.execute(
            "INSERT INTO retention_runs "
            "(id, name, status, trigger, policy_id, created_at, updated_at) "
            "VALUES (%s, %s, 'pending', %s, %s, %s, %s)",
            (run_id, "sweep %s" % policy_id[:13], trigger, policy_id, now, now),
        )
    return {
        "id": run_id,
        "status": "pending",
        "policy_id": policy_id,
        "trigger": trigger,
    }


def execute_sweep(run_id: str) -> dict | None:
    """Claim (pending -> running, atomic) and execute one sweep run. Returns the finished run
    body, or None when the run doesn't exist or was already claimed. A failure is recorded ON
    the run (status=failed) — never raised past this function."""
    now = datetime.now(timezone.utc)
    with get_cursor() as cur:
        cur.execute(
            "UPDATE retention_runs SET status = 'running', updated_at = %s "
            "WHERE id = %s AND status = 'pending'",
            (now, run_id),
        )
        claimed = cur.rowcount == 1
    if not claimed:
        return None
    # from here on NOTHING may escape (the module contract): _do_sweep finishes the run itself
    # (the DELETE and its succeeded/counters audit record commit in ONE transaction), the
    # failure path records status=failed, and even a transient DB error while recording or
    # reading back degrades to a logged partial body — never a raised exception, never a 500
    # for a claimed run.
    try:
        _do_sweep(run_id)
    except Exception:
        # the run row has no error_detail column yet; the log carries the cause
        logger.exception("retention sweep %s failed", run_id)
        try:
            _finish(run_id, "failed", 0, 0)
        except Exception:
            logger.exception("retention sweep %s: could not record the failure", run_id)
    try:
        return get_run(run_id)
    except Exception:
        logger.exception("retention sweep %s: readback failed", run_id)
        return {"id": run_id}


def _do_sweep(run_id: str) -> None:
    """The sweep body: load the run's policy, compute the cutoff, DELETE below it — and commit
    the DELETE together with the run's succeeded/counters update in ONE transaction, so a crash
    can never leave rows deleted without the audit record that explains them. Fail-closed on
    every unsupported combination."""
    now = datetime.now(timezone.utc)
    with get_cursor() as cur:
        cur.execute(
            "SELECT p.table_class, p.action, p.scope, p.dataset_id, "
            "       p.retention_period_days, p.is_enabled "
            "FROM retention_runs r JOIN retention_policies p ON p.id = r.policy_id "
            "WHERE r.id = %s",
            (run_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise SweepError("run %s has no policy attached" % run_id)
    policy = dict(row)  # get_cursor yields RealDictCursor rows

    cutoff = plan_sweep(policy, now)
    if cutoff is None:
        if policy["is_enabled"]:
            # an ENABLED policy with no valid period is a misconfiguration, not a no-op —
            # recording it as succeeded would hide "retention never enforced" behind a green
            # audit trail forever
            raise SweepError("enabled policy has no valid retention_period_days")
        _finish(run_id, "succeeded", 0, 0)  # disabled policy: a clean, recorded no-op
        return

    table = policy["table_class"]
    if table not in _SWEEPABLE:
        raise SweepError("table class %r is not sweepable" % table)
    has_dataset, lifecycle_guard = _SWEEPABLE[table]
    if policy["action"] != "purge":
        raise SweepError(
            "action %r is not yet supported (purge only)" % policy["action"]
        )

    where, params = "created_at < %s", [cutoff]
    if lifecycle_guard:
        where += (
            " " + lifecycle_guard
        )  # terminal rows only — never queued/in-flight work
    if policy["scope"] == "dataset":
        if not has_dataset:
            raise SweepError(
                "table class %r has no dataset_id column — a dataset-scoped policy "
                "cannot sweep it" % table
            )
        if not policy["dataset_id"]:
            raise SweepError("dataset-scoped policy has no dataset_id set")
        where += " AND dataset_id = %s"
        params.append(policy["dataset_id"])

    with get_cursor() as cur:
        # `table` and the guard fragment come from the closed _SWEEPABLE allowlist above —
        # never from input. DELETE + audit record: one transaction, atomic.
        cur.execute('DELETE FROM "%s" WHERE %s' % (table, where), params)
        purged = cur.rowcount
        cur.execute(
            "UPDATE retention_runs SET status = 'succeeded', records_purged = %s, "
            "records_anonymized = 0, updated_at = %s WHERE id = %s AND status = 'running'",
            (purged, datetime.now(timezone.utc), run_id),
        )


def _finish(run_id: str, status: str, purged: int, anonymized: int) -> None:
    now = datetime.now(timezone.utc)
    with get_cursor() as cur:
        cur.execute(
            "UPDATE retention_runs SET status = %s, records_purged = %s, "
            "records_anonymized = %s, updated_at = %s "
            "WHERE id = %s AND status = 'running'",
            (status, purged, anonymized, now, run_id),
        )


def get_run(run_id: str) -> dict | None:
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, name, status, trigger, policy_id, records_purged, "
            "records_anonymized FROM retention_runs WHERE id = %s",
            (run_id,),
        )
        r = cur.fetchone()
    return dict(r) if r is not None else None
