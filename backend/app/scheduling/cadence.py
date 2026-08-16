"""Cadence helpers for load-sequence scheduling.

Pure, dependency-free helpers that translate a cadence label into a firing
interval and decide whether a scheduled load sequence is due. No database, no
I/O — the scheduling worker (a separate service) calls these to drive cadence
evaluation.
"""

from datetime import datetime, timedelta

# Recognised cadence labels (matched case-insensitively after stripping
# surrounding whitespace) mapped to their firing interval.
_INTERVALS: dict[str, timedelta] = {
    "hourly": timedelta(hours=1),
    "daily": timedelta(hours=24),
    "weekly": timedelta(days=7),
}


def interval_for(cadence: str | None) -> timedelta | None:
    """Return the firing interval for a cadence label, or None if unrecognised.

    The label is matched case-insensitively after stripping surrounding
    whitespace. Anything else — including ``None`` and the empty string —
    yields ``None``.
    """
    if cadence is None:
        return None
    key = cadence.strip().lower()
    return _INTERVALS.get(key)


def is_due(
    cadence: str | None,
    last_fired_at: datetime | None,
    now: datetime,
) -> bool:
    """Return whether a cadence is due to fire.

    - ``False`` when the cadence is unrecognised (``interval_for`` is None).
    - ``True`` when the sequence has never fired (``last_fired_at`` is None).
    - Otherwise ``True`` exactly when ``now - last_fired_at >= interval`` for
      timezone-aware datetimes.
    """
    interval = interval_for(cadence)
    if interval is None:
        return False
    if last_fired_at is None:
        return True
    return (now - last_fired_at) >= interval
