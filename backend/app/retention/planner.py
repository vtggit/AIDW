"""Retention sweep-planning logic.

Pure functions that compute sweep cutoffs from a retention policy and a
reference timestamp.  No database access — callers supply the policy
dict and the current UTC datetime.
"""

from __future__ import annotations

from datetime import datetime, timedelta


def plan_sweep(policy: dict, now: datetime) -> datetime | None:
    """Return the sweep cutoff datetime, or *None* when no sweep is due.

    Parameters
    ----------
    policy:
        A dict with at least the keys ``is_enabled`` (bool) and
        ``retention_period_days`` (positive int).
    now:
        The current UTC datetime used as the reference point.

    Returns
    -------
    datetime or None
        ``now - timedelta(days=retention_period_days)`` when the policy
        is enabled and the period is a valid positive integer; ``None``
        otherwise.
    """
    # Policy must be explicitly enabled
    if not policy.get("is_enabled"):
        return None

    period = policy.get("retention_period_days")

    # Must be an int (bool is a subclass of int — reject it) and > 0
    if not isinstance(period, int) or isinstance(period, bool) or period <= 0:
        return None

    return now - timedelta(days=period)
