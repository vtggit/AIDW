"""Proving test for issue #552: sequence_runs.name truncation and NULL/empty handling."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.worker.scheduling import fire_due_sequences_once


def _run_fire(mock_cur):
    """Helper: patch get_cursor and is_due, call fire_due_sequences_once."""
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    with (
        patch("app.worker.scheduling.get_cursor") as mock_gc,
        patch("app.worker.scheduling.is_due", return_value=True),
    ):
        mock_gc.return_value.__enter__.return_value = mock_cur
        mock_gc.return_value.__exit__.return_value = False
        fire_due_sequences_once(now=now)


def _get_inserted_name(mock_cur):
    """Extract the name value from the INSERT call on mock_cur."""
    insert_calls = [
        c for c in mock_cur.execute.call_args_list if c[0][0].startswith("INSERT")
    ]
    assert len(insert_calls) == 1
    params = insert_calls[0][0][1]
    return params[1]  # name is the second column


def test_issue552_surgical():
    # --- Case 1: 255-char name must produce a composed name <= 255 chars ---
    long_name = "A" * 255
    seq_id = "seq-001"
    mock_cur = MagicMock()
    mock_cur.fetchall.side_effect = [
        [
            {
                "id": seq_id,
                "name": long_name,
                "schedule_cadence": "daily",
                "last_fired_at": None,
            },
        ],
        [],
    ]
    _run_fire(mock_cur)
    inserted = _get_inserted_name(mock_cur)
    assert len(inserted) <= 255, f"composed name is {len(inserted)} chars, exceeds 255"
    assert inserted.startswith("scheduled: "), "prefix 'scheduled: ' must be preserved"

    # --- Case 2: NULL name falls back to sequence_id ---
    mock_cur2 = MagicMock()
    mock_cur2.fetchall.side_effect = [
        [
            {
                "id": seq_id,
                "name": None,
                "schedule_cadence": "daily",
                "last_fired_at": None,
            },
        ],
        [],
    ]
    _run_fire(mock_cur2)
    inserted2 = _get_inserted_name(mock_cur2)
    assert (
        inserted2 == f"scheduled: {seq_id}"
    ), f"expected 'scheduled: {seq_id}', got {inserted2!r}"
    assert len(inserted2) <= 255

    # --- Case 3: empty-string name falls back to sequence_id ---
    mock_cur3 = MagicMock()
    mock_cur3.fetchall.side_effect = [
        [
            {
                "id": seq_id,
                "name": "",
                "schedule_cadence": "daily",
                "last_fired_at": None,
            },
        ],
        [],
    ]
    _run_fire(mock_cur3)
    inserted3 = _get_inserted_name(mock_cur3)
    assert (
        inserted3 == f"scheduled: {seq_id}"
    ), f"expected 'scheduled: {seq_id}', got {inserted3!r}"
    assert len(inserted3) <= 255
