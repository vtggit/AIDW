"""Tests for the retention sweep-planning module (Issue #118)."""

from datetime import datetime, timedelta, timezone

from app.retention.planner import plan_sweep


def test_issue118_freeform():
    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    # --- Disabled policy → None ---
    assert plan_sweep({"is_enabled": False, "retention_period_days": 30}, now) is None

    # --- Missing retention_period_days → None ---
    assert plan_sweep({"is_enabled": True}, now) is None

    # --- Non-positive retention_period_days → None ---
    assert plan_sweep({"is_enabled": True, "retention_period_days": 0}, now) is None
    assert plan_sweep({"is_enabled": True, "retention_period_days": -5}, now) is None

    # --- Non-integer retention_period_days → None ---
    assert plan_sweep({"is_enabled": True, "retention_period_days": "30"}, now) is None
    assert plan_sweep({"is_enabled": True, "retention_period_days": 30.5}, now) is None
    assert plan_sweep({"is_enabled": True, "retention_period_days": True}, now) is None
    assert plan_sweep({"is_enabled": True, "retention_period_days": None}, now) is None

    # --- Valid policy → cutoff datetime ---
    result = plan_sweep({"is_enabled": True, "retention_period_days": 30}, now)
    expected = now - timedelta(days=30)
    assert result == expected

    # --- Edge: 1-day retention ---
    result = plan_sweep({"is_enabled": True, "retention_period_days": 1}, now)
    expected = now - timedelta(days=1)
    assert result == expected
