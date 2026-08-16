"""Proving test for Issue #442 — cadence helpers.

Pure pytest over ``app.scheduling.cadence``: no database, no I/O. The
``client``/``admin_headers`` fixtures are accepted (per the harness contract)
but the cadence helpers under test are dependency-free, so no HTTP calls are
made.
"""

from datetime import datetime, timedelta, timezone

from app.scheduling.cadence import interval_for, is_due


def test_issue442_freeform(client, admin_headers):
    # --- interval_for: recognised labels, case-insensitive after strip ---
    assert interval_for("hourly") == timedelta(hours=1)
    assert interval_for("daily") == timedelta(hours=24)
    assert interval_for("weekly") == timedelta(days=7)

    # case-insensitive
    assert interval_for("HOURLY") == timedelta(hours=1)
    assert interval_for("Daily") == timedelta(hours=24)
    assert interval_for("WEEKLY") == timedelta(days=7)

    # whitespace stripped
    assert interval_for("  hourly  ") == timedelta(hours=1)
    assert interval_for("\tdaily\n") == timedelta(hours=24)
    assert interval_for(" weekly ") == timedelta(days=7)

    # --- interval_for: unrecognised -> None ---
    assert interval_for(None) is None
    assert interval_for("") is None
    assert interval_for("   ") is None
    assert interval_for("monthly") is None
    assert interval_for("hourly-ish") is None
    assert interval_for("hourly daily") is None

    # --- is_due: unrecognised cadence -> False (even with no prior fire) ---
    now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    assert is_due(None, None, now) is False
    assert is_due("", None, now) is False
    assert is_due("monthly", None, now) is False
    assert is_due("monthly", now - timedelta(days=30), now) is False

    # --- is_due: recognised cadence, never fired -> True ---
    assert is_due("hourly", None, now) is True
    assert is_due("daily", None, now) is True
    assert is_due("weekly", None, now) is True

    # --- is_due: recognised cadence, elapsed >= interval -> True ---
    # exactly at the interval boundary (>=)
    assert is_due("hourly", now - timedelta(hours=1), now) is True
    assert is_due("daily", now - timedelta(hours=24), now) is True
    assert is_due("weekly", now - timedelta(days=7), now) is True
    # past the interval
    assert is_due("hourly", now - timedelta(hours=2), now) is True
    assert is_due("daily", now - timedelta(days=2), now) is True
    assert is_due("weekly", now - timedelta(days=10), now) is True

    # --- is_due: recognised cadence, elapsed < interval -> False ---
    assert is_due("hourly", now - timedelta(minutes=59), now) is False
    assert is_due("daily", now - timedelta(hours=23, minutes=59), now) is False
    assert is_due("weekly", now - timedelta(days=6, hours=23), now) is False
    assert is_due("hourly", now, now) is False
