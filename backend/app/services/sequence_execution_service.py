"""Service for executing sequence runs step-by-step."""

from datetime import datetime, timezone

from app.db.connection import get_cursor
from app.repositories.sequence_run_steps_postgres_repository import (
    SequenceRunStepPostgresRepository,
)
from app.repositories.sequence_runs_postgres_repository import (
    SequenceRunPostgresRepository,
)

_run_repo = SequenceRunPostgresRepository()
_run_step_repo = SequenceRunStepPostgresRepository()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def execute_sequence_run(run_id: str) -> dict:
    """Execute a pending sequence run.

    1. Verify the run exists and is in 'pending' status (409 otherwise).
    2. Mark the run as 'running' with started_at.
    3. Fetch all steps for the run's sequence, ordered by order_index.
    4. For each step:
       a. Create a sequence_run_steps row with status='pending'.
       b. Attempt to trigger the pipeline via the ingest service directly.
       c. On success: mark step 'success' with finished_at.
       d. On failure (any exception): mark step 'failed' with finished_at,
          then mark all remaining steps as 'skipped', mark run as 'failed',
          and return immediately.
    5. If all steps succeed: mark run as 'completed' with finished_at.
    6. Return the final run state including its steps.

    Returns a dict representing the run (with an added 'steps' key) even when steps failed.
    """
    from fastapi import HTTPException, status

    # 1. Fetch and validate run status
    run = _run_repo.get_by_id(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SequenceRun '{run_id}' not found.",
        )

    # The database defaults status to 'pending' on create. It may be None in the dict
    # if the column was NULL (though the constraint should prevent that). Treat None as pending.
    current_status = run.get("status") or "pending"

    if current_status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"SequenceRun '{run_id}' is not pending (current status: {current_status}).",
        )

    # 2. Mark run as running
    now = _now_iso()
    _run_repo.update(run_id, {"status": "running", "started_at": now})

    sequence_id = run["sequence_id"]

    # 3. Fetch steps ordered by order_index
    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM sequence_steps WHERE sequence_id = %s ORDER BY order_index ASC",
            (sequence_id,),
        )
        steps = [dict(r) for r in cur.fetchall()]

    if not steps:
        # No steps to execute — mark as completed immediately
        _run_repo.update(run_id, {"status": "completed", "finished_at": now})
        final_run = _run_repo.get_by_id(run_id)
        return {**final_run, "steps": []}

    # 4. Process each step
    failed = False
    for idx, step in enumerate(steps):
        if failed:
            break

        step_id = step["id"]
        pipeline_id = step["pipeline_id"]
        step_name = step.get("name", f"step-{idx}")

        # 4a. Create run_step row with status='pending'
        run_step_data = {
            "name": step_name,
            "run_id": run_id,
            "step_id": step_id,
            "status": "pending",
            "started_at": None,
            "finished_at": None,
        }
        run_step = _run_step_repo.create(run_step_data)
        run_step_id = run_step["id"]

        # Mark as running
        step_start = _now_iso()
        _run_step_repo.update(
            run_step_id, {"status": "running", "started_at": step_start}
        )

        try:
            # 4b. Trigger the pipeline via the ingest service directly
            from app.ingest.service import start_run

            start_run(pipeline_id)
            # 4c. Success
            step_finish = _now_iso()
            _run_step_repo.update(
                run_step_id, {"status": "success", "finished_at": step_finish}
            )

        except Exception:
            # 4d. Failure — mark this step as failed
            step_finish = _now_iso()
            _run_step_repo.update(
                run_step_id, {"status": "failed", "finished_at": step_finish}
            )

            # Mark all remaining steps as skipped
            for remaining_idx in range(idx + 1, len(steps)):
                remaining_step = steps[remaining_idx]
                remaining_step_id = remaining_step["id"]
                remaining_name = remaining_step.get("name", f"step-{remaining_idx}")

                rem_run_step_data = {
                    "name": remaining_name,
                    "run_id": run_id,
                    "step_id": remaining_step_id,
                    "status": "skipped",
                    "started_at": None,
                    "finished_at": None,
                }
                _run_step_repo.create(rem_run_step_data)

            # Mark the run as failed
            fail_time = _now_iso()
            _run_repo.update(run_id, {"status": "failed", "finished_at": fail_time})
            failed = True

    # 5. If all steps succeeded, mark run as completed
    if not failed:
        complete_time = _now_iso()
        _run_repo.update(run_id, {"status": "completed", "finished_at": complete_time})

    # 6. Fetch final run state with its steps
    final_run = _run_repo.get_by_id(run_id)

    # Fetch all run_steps for this run
    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM sequence_run_steps WHERE run_id = %s ORDER BY created_at ASC",
            (run_id,),
        )
        run_steps_raw = [dict(r) for r in cur.fetchall()]

    # Convert datetime fields to ISO strings
    run_steps = []
    for rs in run_steps_raw:
        converted = {}
        for key, value in rs.items():
            if isinstance(value, datetime):
                converted[key] = value.isoformat()
            else:
                converted[key] = value
        run_steps.append(converted)

    return {**final_run, "steps": run_steps}
