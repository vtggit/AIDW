"""Proving test for issue #558: per-row savepoint isolation in fire_due_sequences_once."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import psycopg2
import pytest

from app.worker.scheduling import fire_due_sequences_once


def _build_cursor(rows, fail_seq_id=None, fail_exc=None):
    """Build a mock cursor simulating the scheduling SQL flow."""
    cur = MagicMock()
    log = []

    def _exec(sql, params=None):
        log.append((sql, params))
        if sql.startswith("SAVEPOINT"):
            return
        if sql.startswith("RELEASE SAVEPOINT"):
            return
        if sql.startswith("ROLLBACK TO SAVEPOINT"):
            return
        if "SELECT id, name, schedule_cadence" in sql:
            return
        if "SELECT 1 FROM sequence_runs" in sql:
            cur.fetchall.return_value = []
            return
        if "INSERT INTO sequence_runs" in sql:
            if fail_seq_id and params and params[2] == fail_seq_id:
                raise fail_exc
            return
        if "UPDATE load_sequences" in sql:
            return

    cur.execute.side_effect = _exec
    cur.fetchall.return_value = rows
    return cur, log


def test_issue558_surgical():
    """Per-row failures are isolated via savepoints; connection errors propagate."""
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = [
        {
            "id": "seq-1",
            "name": "A",
            "schedule_cadence": "daily",
            "last_fired_at": None,
        },
        {
            "id": "seq-2",
            "name": "B",
            "schedule_cadence": "daily",
            "last_fired_at": None,
        },
    ]

    # --- Part 1: per-row IntegrityError is isolated, other rows succeed ---
    cur, log = _build_cursor(
        rows,
        fail_seq_id="seq-1",
        fail_exc=psycopg2.IntegrityError("duplicate key"),
    )
    with (
        patch("app.worker.scheduling.get_cursor") as mock_gc,
        patch("app.worker.scheduling.is_due", return_value=True),
    ):
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=cur)
        cm.__exit__ = MagicMock(return_value=False)
        mock_gc.return_value = cm
        result = fire_due_sequences_once(now=now)

    # Only seq-2 succeeded
    assert len(result) == 1
    # One ROLLBACK TO SAVEPOINT for the failed row
    rollbacks = [s for s, _ in log if s.startswith("ROLLBACK TO SAVEPOINT")]
    assert len(rollbacks) == 1
    # Two RELEASE SAVEPOINT calls (one after rollback, one for success)
    releases = [s for s, _ in log if s.startswith("RELEASE SAVEPOINT")]
    assert len(releases) == 2

    # --- Part 2: OperationalError must propagate, not be swallowed ---
    cur2, _log2 = _build_cursor(
        rows[:1],
        fail_seq_id="seq-1",
        fail_exc=psycopg2.OperationalError("connection lost"),
    )
    with (
        patch("app.worker.scheduling.get_cursor") as mock_gc2,
        patch("app.worker.scheduling.is_due", return_value=True),
    ):
        cm2 = MagicMock()
        cm2.__enter__ = MagicMock(return_value=cur2)
        cm2.__exit__ = MagicMock(return_value=False)
        mock_gc2.return_value = cm2
        with pytest.raises(psycopg2.OperationalError):
            fire_due_sequences_once(now=now)
