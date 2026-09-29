"""Scheduled sequence-run claim/execute.

Claims the oldest pending sequence run that was triggered by the scheduler and hands it to
``app.services.sequence_execution_service.execute_sequence_run`` — the single owner of the
pending→running transition and step execution. The claim marker is ``started_at`` (not
``status``) because ``execute_sequence_run`` requires the run to still be ``pending`` and
performs the pending→running transition itself; setting ``started_at`` here is the
idempotency fence that keeps a second worker from re-claiming the same row.

A NULL ``status`` counts as pending (``COALESCE(status, 'pending')``), matching
the service's own treatment of the nullable column, so NULL-status schedule
runs are claimed as well.
"""

import logging
from datetime import datetime, timezone

from app.db.connection import get_cursor

logger = logging.getLogger(__name__)


def execute_scheduled_run_once() -> str | None:
    """Atomically claim and execute one scheduled sequence run.

    Claims the OLDEST ``sequence_runs`` row with
    ``COALESCE(status, 'pending') = 'pending'`` AND
    ``triggered_by='schedule'`` AND ``started_at IS NULL`` via one atomic
    ``UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1)
    RETURNING id``. The claim sets ``started_at`` (the claim marker) but leaves
    ``status`` as ``pending`` so ``execute_sequence_run`` can perform its own
    pending→running transition.

    Returns the claimed run id, or ``None`` when nothing is claimable. Any
    exception raised by ``execute_sequence_run`` (including its HTTPException
    for 404/409) is caught and logged, never propagated.
    """
    from fastapi import HTTPException, status

    from app.services.sequence_execution_service import execute_sequence_run

    now = datetime.now(timezone.utc)
    with get_cursor() as cur:
        cur.execute(
            "UPDATE sequence_runs SET started_at = %s, updated_at = %s "
            "WHERE id = ("
            "  SELECT id FROM sequence_runs "
            "  WHERE COALESCE(status, 'pending') = 'pending' "
            "  AND triggered_by = 'schedule' AND started_at IS NULL "
            "  ORDER BY created_at, id FOR UPDATE SKIP LOCKED LIMIT 1"
            ") RETURNING id",
            (now, now),
        )
        row = cur.fetchone()

    if row is None:
        return None

    run_id = row["id"]
    logger.info("claimed scheduled sequence run %s", run_id)
    try:
        execute_sequence_run(run_id)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_409_CONFLICT:
            # A concurrent executor (another worker, or a manual /execute call)
            # claimed the run between our claim and the service's own
            # pending->running UPDATE. Benign: nothing to do.
            logger.info(
                "scheduled sequence run %s already claimed concurrently (benign 409)",
                run_id,
            )
        else:
            logger.exception("scheduled sequence run %s raised HTTPException", run_id)
    except Exception:
        logger.exception("scheduled sequence run %s failed", run_id)
    return run_id
