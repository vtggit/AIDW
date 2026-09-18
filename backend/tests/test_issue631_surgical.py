"""Proving test for issue #631: reaper for stranded scheduled sequence runs."""

import inspect
from unittest.mock import MagicMock, patch

import pytest


def test_issue631_surgical():
    """reap_stranded_scheduled exists, targets the right rows, and is wired in."""
    from app.worker import loop

    # 1. Module-level timeout constant exists and is a positive int
    assert hasattr(loop, "STRANDED_SCHEDULED_SECONDS")
    assert isinstance(loop.STRANDED_SCHEDULED_SECONDS, int)
    assert loop.STRANDED_SCHEDULED_SECONDS > 0

    # 2. reap_stranded_scheduled function exists and is callable
    assert hasattr(loop, "reap_stranded_scheduled")
    assert callable(loop.reap_stranded_scheduled)

    # 3. Verify the SQL targets the correct rows and performs the correct update
    mock_cur = MagicMock()
    mock_cur.rowcount = 3
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_cur)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch.object(loop, "get_cursor", return_value=mock_ctx):
        result = loop.reap_stranded_scheduled(max_age_seconds=60)

    assert result == 3
    sql = mock_cur.execute.call_args[0][0]
    params = mock_cur.execute.call_args[0][1]

    # Must be an UPDATE on sequence_runs
    assert "UPDATE sequence_runs" in sql
    # Must set started_at = NULL and updated_at = NOW()
    assert "started_at = NULL" in sql
    assert "updated_at = NOW()" in sql
    # Must filter on triggered_by = 'schedule'
    assert "triggered_by = 'schedule'" in sql
    # Must filter on status = 'pending' (must not touch other statuses)
    assert "status = 'pending'" in sql
    # Must require started_at IS NOT NULL (stranded marker only)
    assert "started_at IS NOT NULL" in sql
    # Must use updated_at for age comparison (not started_at)
    assert "updated_at <" in sql
    # Must NOT compare started_at temporally (VARCHAR(255) safety)
    assert "started_at <" not in sql
    assert "started_at >" not in sql
    # The parameter should be a datetime (the cutoff)
    from datetime import datetime, timedelta, timezone

    assert isinstance(params[0], datetime)
    expected_cutoff = datetime.now(timezone.utc) - timedelta(seconds=60)
    delta = abs((params[0] - expected_cutoff).total_seconds())
    assert delta < 5  # allow a few seconds of test execution drift

    # 4. Verify the reaper is called from main_loop
    source = inspect.getsource(loop.main_loop)
    assert "reap_stranded_scheduled" in source

    # 5. Verify the reaper call is protected by try/except so the loop
    #    continues if the reaper query fails
    lines = source.split("\n")
    for i, line in enumerate(lines):
        if "reap_stranded_scheduled()" in line and "def " not in line:
            # Look in a small window around the call for try/except
            window = "\n".join(lines[max(0, i - 4) : i + 4])
            assert (
                "try:" in window
            ), "reap_stranded_scheduled call must be inside a try block"
            assert (
                "except" in window
            ), "reap_stranded_scheduled call must have an except handler"
            break
    else:
        pytest.fail("reap_stranded_scheduled() call not found in main_loop")
