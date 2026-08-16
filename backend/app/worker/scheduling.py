"""Schedule-driven load-sequence firing.

Mirrors the worker claim shape from ``app.worker.loop`` (one atomic
``FOR UPDATE SKIP LOCKED`` read inside a single transaction) but for
load-sequence schedules: select the enabled, cadence-bearing sequences,
evaluate each with the pure ``app.scheduling.cadence.is_due`` helper, and
for every due sequence insert ONE pending ``sequence_runs`` row and stamp
``load_sequences.last_fired_at``. This module never executes a run — it
only enqueues the pending row for the existing worker loop to claim.
"""

import logging
import uuid
from datetime import datetime, timezone

from app.db.connection import get_cursor
from app.scheduling.cadence import is_due

logger = logging.getLogger(__name__)


def fire_due_sequences_once(now: datetime | None = None) -> list[str]:
    """Fire every due load sequence exactly once.

    Inside ONE transaction (a single ``with get_cursor() as cur:`` block,
    rows read by name) it selects the enabled, cadence-bearing sequences
    with ``FOR UPDATE SKIP LOCKED``, evaluates each with
    ``app.scheduling.cadence.is_due`` (never re-implemented here), and for
    every due sequence inserts ONE pending ``sequence_runs`` row and
    updates that sequence's ``last_fired_at``/``updated_at`` to ``now``.

    Returns the created run ids (``[]`` when nothing is due). Never
    executes a run, and never touches a non-due or unrecognised-cadence
    sequence.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    created_run_ids: list[str] = []
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, name, schedule_cadence, last_fired_at "
            "FROM load_sequences "
            "WHERE schedule_cadence IS NOT NULL "
            "  AND (schedule_enabled IS TRUE OR schedule_enabled IS NULL) "
            "FOR UPDATE SKIP LOCKED"
        )
        rows = cur.fetchall()

        for row in rows:
            sequence_id = row["id"]
            sequence_name = row["name"]
            cadence = row.get("schedule_cadence")
            last_fired_at = row.get("last_fired_at")

            if not is_due(cadence, last_fired_at, now):
                continue

            run_id = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO sequence_runs "
                "(id, name, sequence_id, status, triggered_by, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    run_id,
                    f"scheduled: {sequence_name}",
                    sequence_id,
                    "pending",
                    "schedule",
                    now,
                    now,
                ),
            )
            cur.execute(
                "UPDATE load_sequences "
                "SET last_fired_at = %s, updated_at = %s "
                "WHERE id = %s",
                (now, now, sequence_id),
            )
            created_run_ids.append(run_id)

    if created_run_ids:
        logger.info("fired %d due load sequence(s)", len(created_run_ids))
    return created_run_ids
