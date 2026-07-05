"""PostgreSQL repository for sales goals and quota tracking."""

from datetime import datetime, timezone
from uuid import uuid4

from app.db.connection import get_cursor


def _generate_id() -> str:
    return str(uuid4())


def _row_to_dict(row) -> dict:
    d = dict(row)
    for key in ("created_at", "updated_at"):
        if d.get(key) and isinstance(d[key], datetime):
            d[key] = d[key].isoformat()
    # Ensure numeric fields are floats
    for key in ("target_value", "current_value"):
        if d.get(key) is not None:
            d[key] = float(d[key])
    return d


class SalesGoalsPostgresRepository:
    """PostgreSQL repository for sales_goals table."""

    def list_all(self, active_only: bool = False) -> list[dict]:
        query = "SELECT * FROM sales_goals"
        if active_only:
            query += " WHERE end_date >= CURRENT_DATE"
        query += " ORDER BY start_date DESC"
        with get_cursor() as cur:
            cur.execute(query)
            return [_row_to_dict(r) for r in cur.fetchall()]

    def get_by_id(self, goal_id: str) -> dict | None:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM sales_goals WHERE id = %s", (goal_id,))
            row = cur.fetchone()
            return _row_to_dict(row) if row else None

    def create(self, data: dict) -> dict:
        goal_id = data.get("id", _generate_id())
        now = datetime.now(timezone.utc)
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO sales_goals
                   (id, name, type, target_value, current_value, period, start_date, end_date, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    goal_id,
                    data["name"],
                    data["type"],
                    data["target_value"],
                    data.get("current_value", 0.0),
                    data["period"],
                    data["start_date"],
                    data["end_date"],
                    now,
                    now,
                ),
            )
        return self.get_by_id(goal_id)

    def update(self, goal_id: str, data: dict) -> dict | None:
        updatable = ("name", "target_value", "current_value", "start_date", "end_date")
        fields = [k for k in updatable if k in data]
        if not fields:
            return self.get_by_id(goal_id)

        set_clauses = [f"{f} = %s" for f in fields]
        set_clauses.append("updated_at = %s")
        values = [data[f] for f in fields]
        values.append(datetime.now(timezone.utc))

        with get_cursor() as cur:
            cur.execute(
                f"UPDATE sales_goals SET {', '.join(set_clauses)} WHERE id = %s",
                values + [goal_id],
            )
        return self.get_by_id(goal_id)

    def update_current_value(self, goal_id: str, value: float) -> dict | None:
        """Update just the current_value for a goal."""
        with get_cursor() as cur:
            cur.execute(
                "UPDATE sales_goals SET current_value = %s, updated_at = %s WHERE id = %s",
                (value, datetime.now(timezone.utc), goal_id),
            )
        return self.get_by_id(goal_id)

    def delete(self, goal_id: str) -> bool:
        with get_cursor() as cur:
            cur.execute("DELETE FROM sales_goals WHERE id = %s", (goal_id,))
            return cur.rowcount > 0

    def get_progress(self) -> dict:
        """Get progress summary for all active goals."""
        with get_cursor() as cur:
            cur.execute("""SELECT g.*,
                   CASE WHEN g.target_value > 0
                        THEN ROUND((g.current_value / g.target_value) * 100, 1)
                        ELSE 0 END AS progress_percent
                   FROM sales_goals g
                   WHERE g.end_date >= CURRENT_DATE
                   ORDER BY g.start_date DESC""")
            goals = []
            for r in cur.fetchall():
                d = _row_to_dict(r)
                d["progress_percent"] = (
                    float(r["progress_percent"]) if r["progress_percent"] else 0.0
                )
                goals.append(d)

            total_progress = (
                sum(g["progress_percent"] for g in goals) / len(goals) if goals else 0.0
            )
            return {"goals": goals, "overall_progress": round(total_progress, 1)}
