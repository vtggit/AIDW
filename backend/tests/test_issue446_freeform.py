"""Proof for issue #446 — scheduled sequence-run claim/execute.

Proves ``app.worker.scheduled_execution.execute_scheduled_run_once``:
  * claims the oldest pending, schedule-triggered sequence run and returns its id,
    after which the run is no longer 'pending';
  * leaves a manual pending run (triggered_by NULL) untouched;
  * returns None on a further call when nothing is claimable.
"""

import uuid

from app.db.connection import get_cursor
from app.worker.scheduled_execution import execute_scheduled_run_once


def _truncate_tables() -> None:
    """Truncate the tables this test uses to guarantee isolation.

    The autouse ``clean_database`` fixture only truncates ``audit_log``;
    sequence-related tables may carry rows from other tests in the session.
    """
    with get_cursor() as cur:
        cur.execute(
            "TRUNCATE TABLE sequence_run_steps, sequence_runs, sequence_steps, "
            "load_sequences RESTART IDENTITY CASCADE;"
        )


def _insert_load_sequence(name: str) -> str:
    seq_id = str(uuid.uuid4())
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO load_sequences (id, name) VALUES (%s, %s)",
            (seq_id, name),
        )
    return seq_id


def _insert_sequence_run(sequence_id: str, triggered_by: str | None) -> str:
    run_id = str(uuid.uuid4())
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO sequence_runs (id, name, sequence_id, status, triggered_by) "
            "VALUES (%s, %s, %s, 'pending', %s)",
            (run_id, f"run-{run_id[:8]}", sequence_id, triggered_by),
        )
    return run_id


def _run_status(run_id: str) -> str | None:
    with get_cursor() as cur:
        cur.execute(
            "SELECT status FROM sequence_runs WHERE id = %s",
            (run_id,),
        )
        row = cur.fetchone()
    return row["status"] if row else None


def test_issue446_freeform(client, admin_headers):
    # Guarantee a clean slate for the tables this test exercises.
    _truncate_tables()

    # A load sequence plus a schedule-triggered pending run for it.
    seq_id = _insert_load_sequence("sched-seq")
    sched_run_id = _insert_sequence_run(seq_id, "schedule")

    # A manual pending run (triggered_by NULL) that must be left alone.
    manual_seq_id = _insert_load_sequence("manual-seq")
    manual_run_id = _insert_sequence_run(manual_seq_id, None)

    # The call claims the schedule run and returns its id.
    claimed = execute_scheduled_run_once()
    assert claimed == sched_run_id

    # Afterwards the claimed run is no longer 'pending'.
    assert _run_status(sched_run_id) != "pending"

    # The manual pending run (triggered_by NULL) is left pending.
    assert _run_status(manual_run_id) == "pending"

    # A further call finds nothing claimable.
    assert execute_scheduled_run_once() is None
