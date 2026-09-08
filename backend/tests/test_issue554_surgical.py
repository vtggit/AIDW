"""Proving test for issue #554: skip sequences with existing pending/running runs."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.worker.scheduling import fire_due_sequences_once


def _run_fire(mock_cur, now=None):
    """Helper: patch get_cursor and is_due, call fire_due_sequences_once."""
    if now is None:
        now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    with (
        patch("app.worker.scheduling.get_cursor") as mock_gc,
        patch("app.worker.scheduling.is_due", return_value=True),
    ):
        mock_gc.return_value.__enter__.return_value = mock_cur
        mock_gc.return_value.__exit__.return_value = False
        return fire_due_sequences_once(now=now)


def test_issue554_surgical():
    """Sequence with an existing pending run is skipped: no INSERT, no UPDATE."""
    seq_id = "seq-554"
    mock_cur = MagicMock()
    # First fetchall: the due sequence row; second fetchall: existing pending run
    mock_cur.fetchall.side_effect = [
        [
            {
                "id": seq_id,
                "name": "my-seq",
                "schedule_cadence": "daily",
                "last_fired_at": None,
            },
        ],
        [{"1": 1}],  # non-empty: a pending/running run already exists
    ]

    result = _run_fire(mock_cur)

    # No run should be created
    assert result == [], f"expected no runs created, got {result}"

    # No INSERT into sequence_runs
    insert_calls = [
        c for c in mock_cur.execute.call_args_list if c[0][0].startswith("INSERT")
    ]
    assert (
        len(insert_calls) == 0
    ), "INSERT should not be called when a pending run exists"

    # No UPDATE to load_sequences (last_fired_at not stamped)
    update_calls = [
        c for c in mock_cur.execute.call_args_list if c[0][0].startswith("UPDATE")
    ]
    assert (
        len(update_calls) == 0
    ), "UPDATE should not be called when a pending run exists"
