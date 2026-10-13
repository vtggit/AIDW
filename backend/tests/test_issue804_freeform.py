"""Proving test for issue #804 — the worker finalises sequence runs whose executor died.

``reap_stale_sequence_runs`` (app/worker/loop.py) targets ``sequence_runs`` rows with status
``running`` whose ``updated_at`` is older than the cutoff (``WORKER_STALE_SEQUENCE_RUN_SECONDS``,
default 7200, read like the worker's other cutoffs): the run becomes ``failed`` with
``finished_at``/``updated_at`` stamped now, and each of its ``sequence_run_steps`` rows still
``running`` or ``pending`` becomes ``failed`` the same way, all in one transaction; steps that
already succeeded keep their status. Runs younger than the cutoff, and ``completed`` /
``failed`` / ``pending`` runs of any age, are untouched.

The worker loop calls the reaper on every pass, before it looks for due sequences, so a
sequence blocked on its dead run is re-fired by ``fire_due_sequences_once`` on the same pass.
The reaper works in bounded passes (a per-call batch cap) and a failure inside it is logged
without stopping the loop's pass.
"""

import importlib
import logging
import uuid
from datetime import datetime, timedelta, timezone

from app.db.connection import get_cursor
from app.worker import loop
from app.worker.scheduling import fire_due_sequences_once

LOOP_LOGGER = "app.worker.loop"


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(ts: datetime) -> str:
    return ts.isoformat()


def _insert_run(
    sequence_id, status, updated_at, started_at=None, triggered_by="manual"
):
    run_id = _uid("run")
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO sequence_runs "
            "(id, name, sequence_id, status, started_at, finished_at, triggered_by, "
            " created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, NULL, %s, %s, %s)",
            (
                run_id,
                f"seed {run_id[:16]}",
                sequence_id,
                status,
                started_at,
                triggered_by,
                updated_at,
                updated_at,
            ),
        )
    return run_id


def _insert_step(run_id, status, updated_at, started_at=None, finished_at=None):
    step_id = _uid("step")
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO sequence_run_steps "
            "(id, name, run_id, step_id, status, started_at, finished_at, "
            " created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                step_id,
                f"step {step_id[:16]}",
                run_id,
                step_id,
                status,
                started_at,
                finished_at,
                updated_at,
                updated_at,
            ),
        )
    return step_id


def _insert_sequence(name, last_fired_at=None):
    """An enabled hourly sequence; ``last_fired_at=None`` means never fired (due)."""
    seq_id = _uid("seq")
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO load_sequences "
            "(id, name, schedule_cadence, schedule_enabled, last_fired_at, "
            " created_at, updated_at) "
            "VALUES (%s, %s, 'hourly', TRUE, %s, NOW(), NOW())",
            (seq_id, name, last_fired_at),
        )
    return seq_id


def _run_row(run_id):
    with get_cursor() as cur:
        cur.execute(
            "SELECT status, finished_at, updated_at FROM sequence_runs WHERE id = %s",
            (run_id,),
        )
        return dict(cur.fetchone())


def _step_row(step_id):
    with get_cursor() as cur:
        cur.execute(
            "SELECT status, finished_at, updated_at FROM sequence_run_steps WHERE id = %s",
            (step_id,),
        )
        return dict(cur.fetchone())


def _runs_for_sequence(sequence_id):
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, status, triggered_by FROM sequence_runs "
            "WHERE sequence_id = %s ORDER BY created_at, id",
            (sequence_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def test_issue804_freeform(client, admin_headers, monkeypatch, caplog):
    # Sanity: the app is up and the API is reachable (exercises the fixtures).
    assert client.get("/api/load-sequences", headers=admin_headers).status_code == 200

    now = _now()

    # ------------------------------------------------------------------ #
    # 1. core reaper behaviour: only the stale running run moves          #
    # ------------------------------------------------------------------ #
    # A running run three hours old: one success step, one running step.
    # Its sequence was fired recently, so it is not due (stays out of the
    # firing sections' way).
    stale_seq = _insert_sequence("stale-seq", last_fired_at=now)
    stale_run = _insert_run(
        stale_seq,
        "running",
        now - timedelta(hours=3),
        started_at=_iso(now - timedelta(hours=3)),
    )
    ok_step = _insert_step(
        stale_run,
        "success",
        now - timedelta(hours=3),
        started_at=_iso(now - timedelta(hours=3) + timedelta(seconds=1)),
        finished_at=_iso(now - timedelta(hours=3) + timedelta(seconds=2)),
    )
    live_step = _insert_step(
        stale_run,
        "running",
        now - timedelta(hours=3),
        started_at=_iso(now - timedelta(hours=3) + timedelta(seconds=3)),
    )

    # A running run ten minutes old (younger than any cutoff used here).
    fresh_seq = _insert_sequence("fresh-seq", last_fired_at=now)
    fresh_run = _insert_run(fresh_seq, "running", now - timedelta(minutes=10))
    fresh_pending_step = _insert_step(fresh_run, "pending", now - timedelta(minutes=10))
    fresh_running_step = _insert_step(
        fresh_run,
        "running",
        now - timedelta(minutes=10),
        started_at=_iso(now - timedelta(minutes=9)),
    )

    # Terminal / non-running runs of any age: completed, failed, pending.
    done_run = _insert_run(
        _uid("seq"),
        "completed",
        now - timedelta(days=7),
        started_at=_iso(now - timedelta(days=7)),
    )
    failed_run = _insert_run(
        _uid("seq"),
        "failed",
        now - timedelta(days=7),
        started_at=_iso(now - timedelta(days=7)),
    )
    pending_run = _insert_run(_uid("seq"), "pending", now - timedelta(days=7))

    before = {
        "ok_step": _step_row(ok_step),
        "live_step": _step_row(live_step),
        "fresh_run": _run_row(fresh_run),
        "fresh_pending_step": _step_row(fresh_pending_step),
        "fresh_running_step": _step_row(fresh_running_step),
        "done_run": _run_row(done_run),
        "failed_run": _run_row(failed_run),
        "pending_run": _run_row(pending_run),
    }

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger=LOOP_LOGGER):
        reaped = loop.reap_stale_sequence_runs(max_age_seconds=3600)

    # The function returns how many runs it finalised.
    assert reaped == 1

    # The stale run is failed with finished_at (and updated_at) stamped.
    got = _run_row(stale_run)
    assert got["status"] == "failed"
    assert got["finished_at"] is not None
    assert got["updated_at"] >= now

    # Its still-running step is failed with finished_at set.
    live = _step_row(live_step)
    assert live["status"] == "failed"
    assert live["finished_at"] is not None
    assert live["updated_at"] >= now

    # The success step is unchanged, byte for byte.
    assert _step_row(ok_step) == before["ok_step"]

    # The young running run and its steps are untouched.
    assert _run_row(fresh_run) == before["fresh_run"]
    assert _step_row(fresh_pending_step) == before["fresh_pending_step"]
    assert _step_row(fresh_running_step) == before["fresh_running_step"]

    # completed / failed / pending runs of any age are untouched.
    assert _run_row(done_run) == before["done_run"]
    assert _run_row(failed_run) == before["failed_run"]
    assert _run_row(pending_run) == before["pending_run"]

    # Exactly one warning, naming how many runs were finalised.
    warnings = [
        r
        for r in caplog.records
        if r.name == LOOP_LOGGER and r.levelno == logging.WARNING
    ]
    assert len(warnings) == 1
    assert warnings[0].getMessage() == "finalised 1 stale sequence run(s)"

    # ------------------------------------------------------------------ #
    # 2. the cutoff is read from WORKER_STALE_SEQUENCE_RUN_SECONDS        #
    # ------------------------------------------------------------------ #
    # A 30-minute-old running run: older than 900s, younger than the 7200s
    # default — only the env-driven cutoff catches it.
    mid_seq = _insert_sequence("mid-seq", last_fired_at=_now())
    mid_run = _insert_run(mid_seq, "running", _now() - timedelta(minutes=30))
    _insert_step(
        mid_run,
        "running",
        _now() - timedelta(minutes=30),
        started_at=_iso(_now() - timedelta(minutes=29)),
    )

    monkeypatch.setenv("WORKER_STALE_SEQUENCE_RUN_SECONDS", "900")
    importlib.reload(loop)
    try:
        assert loop.STALE_SEQUENCE_RUN_SECONDS == 900
        reaped = loop.reap_stale_sequence_runs()  # no argument: env-driven cutoff
    finally:
        monkeypatch.delenv("WORKER_STALE_SEQUENCE_RUN_SECONDS")
        importlib.reload(loop)

    assert reaped == 1
    got = _run_row(mid_run)
    assert got["status"] == "failed" and got["finished_at"] is not None
    # the ten-minute-old run is still younger than 900s: untouched
    assert _run_row(fresh_run) == before["fresh_run"]
    # env restored: the module is back to the 7200s default
    assert loop.STALE_SEQUENCE_RUN_SECONDS == 7200

    # ------------------------------------------------------------------ #
    # 3. bounded passes (AC-3): one call finalises at most one batch      #
    # ------------------------------------------------------------------ #
    monkeypatch.setattr(loop, "STALE_SEQUENCE_RUN_BATCH", 2)
    batch_runs = []
    for _ in range(3):
        run_id = _insert_run(_uid("seq"), "running", _now() - timedelta(hours=5))
        _insert_step(
            run_id,
            "running",
            _now() - timedelta(hours=5),
            started_at=_iso(_now() - timedelta(hours=5)),
        )
        batch_runs.append(run_id)

    assert loop.reap_stale_sequence_runs(max_age_seconds=3600) == 2
    remaining = [r for r in batch_runs if _run_row(r)["status"] == "running"]
    assert len(remaining) == 1  # the third waits for the next pass, not a longer one
    assert loop.reap_stale_sequence_runs(max_age_seconds=3600) == 1
    assert loop.reap_stale_sequence_runs(max_age_seconds=3600) == 0

    # ------------------------------------------------------------------ #
    # 4. the schedule resumes: blocked before the reaper, fired after     #
    # ------------------------------------------------------------------ #
    blocked_seq = _insert_sequence("blocked-seq")  # never fired: due
    blocked_run = _insert_run(
        blocked_seq,
        "running",
        _now() - timedelta(hours=3),
        started_at=_iso(_now() - timedelta(hours=3)),
        triggered_by="schedule",
    )

    # Before the reaper: the open (stale) run blocks firing.
    assert fire_due_sequences_once() == []

    assert loop.reap_stale_sequence_runs(max_age_seconds=3600) == 1
    assert _run_row(blocked_run)["status"] == "failed"

    # After the reaper: the sequence is due again and gets one new pending run.
    created = fire_due_sequences_once()
    assert len(created) == 1
    rows = _runs_for_sequence(blocked_seq)
    assert len(rows) == 2
    new_run = next(r for r in rows if r["id"] != blocked_run)
    assert new_run["id"] == created[0]
    assert new_run["status"] == "pending"
    assert new_run["triggered_by"] == "schedule"

    # ------------------------------------------------------------------ #
    # 5. one pass of the worker loop: finalise AND fire in the same pass  #
    # ------------------------------------------------------------------ #
    due_seq = _insert_sequence("due-seq")  # never fired: due
    due_stale_run = _insert_run(
        due_seq,
        "running",
        _now() - timedelta(hours=3),
        started_at=_iso(_now() - timedelta(hours=3)),
        triggered_by="schedule",
    )
    _insert_step(
        due_stale_run,
        "running",
        _now() - timedelta(hours=3),
        started_at=_iso(_now() - timedelta(hours=3)),
    )

    loop.main_loop(poll_seconds=0, max_iterations=1)

    # The stale run was finalised by the reaper inside the pass...
    got = _run_row(due_stale_run)
    assert got["status"] == "failed" and got["finished_at"] is not None
    # ...and the sequence was fired by the very same pass (one new run row;
    # the loop may already have executed it, which is normal draining).
    rows = _runs_for_sequence(due_seq)
    assert len(rows) == 2
    new_due = next(r for r in rows if r["id"] != due_stale_run)
    assert new_due["triggered_by"] == "schedule"
    assert new_due["status"] in ("pending", "completed")
    with get_cursor() as cur:
        cur.execute(
            "SELECT last_fired_at FROM load_sequences WHERE id = %s", (due_seq,)
        )
        assert cur.fetchone()["last_fired_at"] is not None  # stamped by the firing

    # ------------------------------------------------------------------ #
    # 6. the reaper raising inside a pass: logged, and the pass completes #
    # ------------------------------------------------------------------ #
    boom_seq = _insert_sequence("boom-seq")  # never fired: due
    boom_run = _insert_run(
        boom_seq,
        "running",
        _now() - timedelta(hours=3),
        started_at=_iso(_now() - timedelta(hours=3)),
        triggered_by="schedule",
    )

    fire_calls = []
    real_fire = fire_due_sequences_once

    def spy_fire(now_arg=None):
        fire_calls.append(True)
        return real_fire(now=now_arg)

    def boom():
        raise RuntimeError("reaper db blip")

    monkeypatch.setattr(loop, "reap_stale_sequence_runs", boom)
    monkeypatch.setattr(loop, "fire_due_sequences_once", spy_fire)
    caplog.clear()
    with caplog.at_level(logging.ERROR, logger=LOOP_LOGGER):
        loop.main_loop(poll_seconds=0, max_iterations=1)  # must not raise

    # The failure was logged, naming the reaper...
    errors = [
        r
        for r in caplog.records
        if r.name == LOOP_LOGGER and r.levelno >= logging.ERROR
    ]
    assert any("reap_stale_sequence_runs failed" in r.getMessage() for r in errors)
    # ...and the rest of the pass ran: the scheduler was reached after the
    # failed reaper in the same pass.
    assert fire_calls
    # The reaper never ran, so the run is still open and the sequence was
    # not fired this pass (its open run keeps blocking it).
    assert _run_row(boom_run)["status"] == "running"
    assert [r["id"] for r in _runs_for_sequence(boom_seq)] == [boom_run]
