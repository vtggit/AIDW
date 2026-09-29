"""Proof for issue #566 — diagnose a failed sequence-run claim.

Proves the 0-row claim path of ``execute_sequence_run`` and the worker's
logging for it:

* the conditional claim UPDATE affecting 0 rows triggers a diagnostic
  re-read on a fresh connection, which yields
    - HTTP 404 ``SequenceRun '<id>' not found.`` when the row was deleted
      between the initial read and the UPDATE,
    - HTTP 409 ``SequenceRun '<id>' is not pending.`` when the row still
      exists,
    - HTTP 5xx when the re-read itself fails with a database error;
* the pre-existing early 404/409 responses and hostile caller-controlled ids
  (empty, huge, control characters, NUL bytes) are unchanged — no 500;
* ``execute_scheduled_run_once`` logs a 409 from the service at INFO (benign
  concurrent claim) and a 404 via ``logger.exception`` (ERROR, with the
  exception attached), never propagating either;
* the worker's claim query treats a NULL status as pending (COALESCE), so a
  schedule run whose status column is NULL is still claimed and executed;
* when the run row vanishes after execution, the service's final re-read
  raises a 5xx HTTPException instead of crashing while unpacking None.
"""

import logging
import uuid

import psycopg2
import pytest
from fastapi import HTTPException

import app.services.sequence_execution_service as seq_exec
from app.db.connection import get_cursor
from app.worker.scheduled_execution import execute_scheduled_run_once

WORKER_LOGGER = "app.worker.scheduled_execution"


def _insert_run(status: str | None = "pending", triggered_by: str | None = None) -> str:
    """Insert a load sequence plus a run for it; return the run id."""
    sequence_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO load_sequences (id, name) VALUES (%s, %s)",
            (sequence_id, f"seq-{sequence_id[:8]}"),
        )
        cur.execute(
            "INSERT INTO sequence_runs (id, name, sequence_id, status, triggered_by) "
            "VALUES (%s, %s, %s, %s, %s)",
            (run_id, f"run-{run_id[:8]}", sequence_id, status, triggered_by),
        )
    return run_id


def _delete_run(run_id: str) -> None:
    with get_cursor() as cur:
        cur.execute("DELETE FROM sequence_runs WHERE id = %s", (run_id,))


def _set_run_status(run_id: str, status: str) -> None:
    with get_cursor() as cur:
        cur.execute(
            "UPDATE sequence_runs SET status = %s WHERE id = %s", (status, run_id)
        )


def test_issue566_freeform(
    client, monkeypatch, caplog
):  # noqa: C901 — single proving function
    original_get_by_id = seq_exec._run_repo.get_by_id

    # ------------------------------------------------------------------
    # AC-1: row deleted between the initial read and the claim UPDATE -> 404
    # ------------------------------------------------------------------
    deleted_run_id = _insert_run()
    deleted_seen = {"done": False}

    def get_by_id_delete_after_read(entity_id):
        row = original_get_by_id(entity_id)
        if entity_id == deleted_run_id and row is not None and not deleted_seen["done"]:
            deleted_seen["done"] = True
            _delete_run(entity_id)
        return row

    monkeypatch.setattr(seq_exec._run_repo, "get_by_id", get_by_id_delete_after_read)
    with pytest.raises(HTTPException) as excinfo:
        seq_exec.execute_sequence_run(deleted_run_id)
    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == f"SequenceRun '{deleted_run_id}' not found."

    # ------------------------------------------------------------------
    # AC-1: row still exists after the claim UPDATE affects 0 rows -> 409
    # (the initial read served a stale 'pending' view; concurrently the run
    # was already claimed and is now 'running')
    # ------------------------------------------------------------------
    conflicted_run_id = _insert_run(status="running")
    stale_seen = {"done": False}

    def get_by_id_stale_pending(entity_id):
        if entity_id == conflicted_run_id and not stale_seen["done"]:
            stale_seen["done"] = True
            row = original_get_by_id(entity_id)
            return {**row, "status": "pending"}
        return original_get_by_id(entity_id)

    monkeypatch.setattr(seq_exec._run_repo, "get_by_id", get_by_id_stale_pending)
    with pytest.raises(HTTPException) as excinfo:
        seq_exec.execute_sequence_run(conflicted_run_id)
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail == f"SequenceRun '{conflicted_run_id}' is not pending."

    # ------------------------------------------------------------------
    # AC-4: the diagnostic re-read fails on a database error -> 5xx, not 404/409
    # ------------------------------------------------------------------
    doomed_run_id = _insert_run()
    recheck_calls = {"n": 0}

    def get_by_id_recheck_fails(entity_id):
        recheck_calls["n"] += 1
        if recheck_calls["n"] == 1:
            row = original_get_by_id(entity_id)
            _delete_run(entity_id)
            return row
        raise psycopg2.OperationalError("simulated connection loss on re-read")

    monkeypatch.setattr(seq_exec._run_repo, "get_by_id", get_by_id_recheck_fails)
    with pytest.raises(HTTPException) as excinfo:
        seq_exec.execute_sequence_run(doomed_run_id)
    assert 500 <= excinfo.value.status_code < 600

    # ------------------------------------------------------------------
    # Unchanged behaviour: early 404/409 paths and hostile caller-controlled ids
    # ------------------------------------------------------------------
    monkeypatch.undo()

    running_run_id = _insert_run(status="running")
    with pytest.raises(HTTPException) as excinfo:
        seq_exec.execute_sequence_run(running_run_id)
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail == (
        f"SequenceRun '{running_run_id}' is not pending (current status: running)."
    )

    with pytest.raises(HTTPException) as excinfo:
        seq_exec.execute_sequence_run("no-such-run")
    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "SequenceRun 'no-such-run' not found."

    for hostile in ("", "x" * 10_000, "a\x00b", "a\nb", "   "):
        with pytest.raises(HTTPException) as excinfo:
            seq_exec.execute_sequence_run(hostile)
        assert excinfo.value.status_code == 404

    # ------------------------------------------------------------------
    # AC-2: worker logs a 409 from the service at INFO (benign concurrent
    # claim) — the run is claimed by a second executor right after the
    # service's initial read
    # ------------------------------------------------------------------
    worker_409_run_id = _insert_run(triggered_by="schedule")
    concurrent_claim_seen = {"done": False}

    def get_by_id_concurrent_claim(entity_id):
        if entity_id == worker_409_run_id and not concurrent_claim_seen["done"]:
            concurrent_claim_seen["done"] = True
            row = original_get_by_id(entity_id)
            _set_run_status(entity_id, "running")
            return row
        return original_get_by_id(entity_id)

    monkeypatch.setattr(seq_exec._run_repo, "get_by_id", get_by_id_concurrent_claim)
    caplog.records.clear()
    with caplog.at_level(logging.INFO, logger=WORKER_LOGGER):
        claimed = execute_scheduled_run_once()
    assert claimed == worker_409_run_id
    worker_records = [r for r in caplog.records if r.name == WORKER_LOGGER]
    info_records = [
        r
        for r in worker_records
        if r.levelno == logging.INFO and "concurrent" in r.getMessage()
    ]
    assert info_records, "benign concurrent claim must be logged at INFO"
    assert not [r for r in worker_records if r.levelno >= logging.ERROR]

    # ------------------------------------------------------------------
    # AC-2: worker keeps the logger.exception (ERROR) path for a 404 — the
    # run is deleted between the initial read and the claim UPDATE
    # ------------------------------------------------------------------
    worker_404_run_id = _insert_run(triggered_by="schedule")
    worker_404_seen = {"done": False}

    def get_by_id_delete_after_read_worker(entity_id):
        row = original_get_by_id(entity_id)
        if (
            entity_id == worker_404_run_id
            and row is not None
            and not worker_404_seen["done"]
        ):
            worker_404_seen["done"] = True
            _delete_run(entity_id)
        return row

    monkeypatch.setattr(
        seq_exec._run_repo, "get_by_id", get_by_id_delete_after_read_worker
    )
    caplog.records.clear()
    with caplog.at_level(logging.INFO, logger=WORKER_LOGGER):
        claimed = execute_scheduled_run_once()
    assert claimed == worker_404_run_id  # neither 404 nor 409 propagates
    worker_records = [r for r in caplog.records if r.name == WORKER_LOGGER]
    error_records = [r for r in worker_records if r.levelno == logging.ERROR]
    assert len(error_records) == 1
    assert error_records[0].exc_info is not None
    logged_exception = error_records[0].exc_info[1]
    assert isinstance(logged_exception, HTTPException)
    assert logged_exception.status_code == 404
    assert logged_exception.detail == f"SequenceRun '{worker_404_run_id}' not found."

    # ------------------------------------------------------------------
    # Review fix: the worker's claim query must treat a NULL status as
    # pending — the literal ``status = 'pending'`` filter silently skipped
    # NULL-status rows, so schedule runs were never claimed
    # ------------------------------------------------------------------
    monkeypatch.undo()
    null_status_run_id = _insert_run(status=None, triggered_by="schedule")
    caplog.records.clear()
    with caplog.at_level(logging.INFO, logger=WORKER_LOGGER):
        claimed = execute_scheduled_run_once()
    assert claimed == null_status_run_id
    final_null_status = seq_exec._run_repo.get_by_id(null_status_run_id)
    assert final_null_status is not None
    assert final_null_status["status"] == "completed"
    assert not [
        r
        for r in caplog.records
        if r.name == WORKER_LOGGER and r.levelno >= logging.ERROR
    ]

    # ------------------------------------------------------------------
    # Review fix: the final run read can return None (row deleted
    # mid-execution) — the service must raise a 5xx HTTPException, not
    # crash with a TypeError unpacking None
    # ------------------------------------------------------------------
    vanished_run_id = _insert_run()
    vanished_reads = {"n": 0}

    def get_by_id_vanish_after_update(entity_id):
        row = original_get_by_id(entity_id)
        if entity_id == vanished_run_id and row is not None:
            vanished_reads["n"] += 1
            # The second read is the post-UPDATE confirmation inside
            # _run_repo.update(); delete the row right after it so the
            # service's final read observes the vanished row.
            if vanished_reads["n"] == 2:
                _delete_run(entity_id)
        return row

    monkeypatch.setattr(seq_exec._run_repo, "get_by_id", get_by_id_vanish_after_update)
    with pytest.raises(HTTPException) as excinfo:
        seq_exec.execute_sequence_run(vanished_run_id)
    assert 500 <= excinfo.value.status_code < 600
