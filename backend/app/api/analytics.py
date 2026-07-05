"""Analytics API routes for lead conversion funnel, pipeline metrics, and activity trends."""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.db.connection import get_cursor
from app.repositories.leads_postgres_repository import LeadsPostgresRepository

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

_repository = LeadsPostgresRepository()

# Ordered funnel stages (top → bottom)
FUNNEL_STAGES = ["new", "contacted", "qualified", "proposal", "won"]
# Terminal stages (leads that have exited the funnel)
TERMINAL_STAGES = {"won", "lost"}


def _parse_ts(val: str | None) -> datetime | None:
    """Parse an ISO timestamp string into a datetime, tolerant of Z suffix."""
    if not val:
        return None
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except Exception:
        return None


def _compute_avg_days(lead: dict, prev_stage: str | None) -> float | None:
    """Estimate days spent in *prev_stage* for a single lead.

    We approximate by using created_at → updated_at for leads that have
    moved beyond prev_stage (i.e., their current stage is later in the
    funnel or they are terminal).  For leads still in prev_stage we use
    created_at → now.
    """
    created = _parse_ts(lead.get("created_at"))
    updated = _parse_ts(lead.get("updated_at"))
    now = datetime.now(timezone.utc)

    if not created:
        return None

    # For leads currently in prev_stage, measure from creation to now
    if lead.get("stage") == prev_stage:
        delta = now - created
    else:
        # Lead has moved on — use updated_at as the exit point
        if not updated or updated <= created:
            return None
        delta = updated - created

    return delta.total_seconds() / 86400


@router.get("/funnel")
def get_funnel_analytics(
    _user: AuthUser = Depends(require_authenticated_user),
):
    """Return lead conversion funnel analytics.

    The funnel shows how leads flow through each stage, with conversion
    rates, drop-off counts, and average time spent per stage.
    """
    leads = _repository.list_all()
    lead_dicts = [
        lead.model_dump() if hasattr(lead, "model_dump") else lead for lead in leads
    ]

    total_leads = len(lead_dicts)
    now = datetime.now(timezone.utc)

    # Count leads per stage and sum values
    stage_counts: dict[str, int] = {}
    stage_values: dict[str, float] = {}
    for stage in FUNNEL_STAGES:
        stage_leads = [lead for lead in lead_dicts if lead.get("stage") == stage]
        stage_counts[stage] = len(stage_leads)
        stage_values[stage] = sum(lead.get("value") or 0 for lead in stage_leads)

    # Count terminal "lost" leads
    lost_count = sum(1 for lead in lead_dicts if lead.get("stage") == "lost")

    # Build funnel steps with conversion metrics
    funnel_steps: list[dict[str, Any]] = []

    for i, stage in enumerate(FUNNEL_STAGES):
        count = stage_counts[stage]
        value = stage_values[stage]

        # Conversion rate from previous stage
        prev_count = total_leads if i == 0 else stage_counts[FUNNEL_STAGES[i - 1]]

        conversion_rate = (count / prev_count * 100) if prev_count > 0 else 0.0

        # Drop-off: leads that were in previous stage but didn't reach this one
        drop_off = prev_count - count if i > 0 else 0
        drop_off_rate = (drop_off / prev_count * 100) if prev_count > 0 else 0.0

        # Average days in this stage
        stage_lead_list = [lead for lead in lead_dicts if lead.get("stage") == stage]
        days_list: list[float] = []
        for lead in stage_lead_list:
            d = _compute_avg_days(lead, stage)
            if d is not None and d >= 0:
                days_list.append(d)
        avg_days = sum(days_list) / len(days_list) if days_list else None

        # Percentage of total pipeline value
        total_value = sum(stage_values.values())
        value_pct = (value / total_value * 100) if total_value > 0 else 0.0

        funnel_steps.append(
            {
                "stage": stage,
                "label": stage.capitalize(),
                "count": count,
                "value": round(value, 2),
                "conversion_rate": round(conversion_rate, 1),
                "drop_off": drop_off,
                "drop_off_rate": round(drop_off_rate, 1),
                "avg_days_in_stage": (
                    round(avg_days, 1) if avg_days is not None else None
                ),
                "value_percentage": round(value_pct, 1),
                "of_total": (
                    round(count / total_leads * 100, 1) if total_leads > 0 else 0.0
                ),
            }
        )

    # Overall metrics
    won_count = stage_counts.get("won", 0)
    overall_conversion = (won_count / total_leads * 100) if total_leads > 0 else 0.0
    total_pipeline_value = sum(stage_values.values())
    won_value = stage_values.get("won", 0)

    return {
        "total_leads": total_leads,
        "lost_leads": lost_count,
        "won_leads": won_count,
        "overall_conversion_rate": round(overall_conversion, 1),
        "total_pipeline_value": round(total_pipeline_value, 2),
        "won_value": round(won_value, 2),
        "funnel_steps": funnel_steps,
        "generated_at": now.isoformat(),
    }


# Allowed query parameter values
_VALID_RANGES: dict[str, int] = {"7d": 7, "30d": 30, "90d": 90}
_VALID_GROUPS: set[str] = {"day", "week"}
_ACTIVITY_TYPES: set[str] = {"call", "email", "meeting", "note", "task"}


@router.get("/activity-trends")
def get_activity_trends(
    _user: AuthUser = Depends(require_authenticated_user),
    range: str = Query(default="30d", alias="range"),
    group: str = Query(default="day"),
):
    """Return time-bucketed activity volume trends.

    Groups activities by day or week within the requested date range and
    returns per-bucket totals broken down by activity type.
    """
    days = _VALID_RANGES.get(range, 30)
    if group not in _VALID_GROUPS:
        group = "day"

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)

    # Build date bucket expression
    if group == "week":
        date_expr = "DATE_TRUNC('week', occurred_at)::date"
    else:
        date_expr = "DATE_TRUNC('day', occurred_at)::date"

    # Query: total count per bucket + count per type
    query = f"""
        SELECT
            {date_expr} AS bucket_date,
            COUNT(*) AS total,
            COALESCE(SUM(CASE WHEN type = 'call' THEN 1 ELSE 0 END), 0) AS call,
            COALESCE(SUM(CASE WHEN type = 'email' THEN 1 ELSE 0 END), 0) AS email,
            COALESCE(SUM(CASE WHEN type = 'meeting' THEN 1 ELSE 0 END), 0) AS meeting,
            COALESCE(SUM(CASE WHEN type = 'note' THEN 1 ELSE 0 END), 0) AS note,
            COALESCE(SUM(CASE WHEN type = 'task' THEN 1 ELSE 0 END), 0) AS task
        FROM activities
        WHERE occurred_at >= %s AND occurred_at <= %s
        GROUP BY bucket_date
        ORDER BY bucket_date ASC
    """

    with get_cursor() as cur:
        cur.execute(query, (start, now))
        rows = cur.fetchall()

    buckets = []
    for row in rows:
        d = dict(row)
        d["bucket_date"] = d["bucket_date"].isoformat()
        buckets.append(d)

    # Find peak bucket
    peak_bucket = None
    peak_count = 0
    for b in buckets:
        if b["total"] > peak_count:
            peak_count = b["total"]
            peak_bucket = b["bucket_date"]

    return {
        "range": range,
        "group": group,
        "start_date": start.isoformat(),
        "end_date": now.isoformat(),
        "total_activities": sum(b["total"] for b in buckets),
        "buckets": buckets,
        "peak_bucket": peak_bucket,
        "peak_count": peak_count,
        "generated_at": now.isoformat(),
    }
