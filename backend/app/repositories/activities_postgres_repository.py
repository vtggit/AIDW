"""PostgreSQL-backed repository for Activities."""

import logging
import uuid
from datetime import date, datetime, timezone

from app.db.connection import get_cursor
from app.observability.logging import get_request_id

logger = logging.getLogger(__name__)


def _req() -> str:
    """Return a request-ID suffix for log lines, or empty string."""
    rid = get_request_id()
    return f" request_id={rid}" if rid else ""


def _generate_id() -> str:
    """Generate a UUID-based unique ID."""
    return str(uuid.uuid4())


def _row_to_dict(row) -> dict:
    """Convert a RealDictRow (or dict) into a plain dict with ISO timestamps."""
    d = dict(row)
    for key in ("occurred_at", "created_at", "updated_at"):
        if d.get(key):
            ts = d[key]
            if isinstance(ts, datetime):
                d[key] = ts.isoformat()
    # due_date is a date object — convert to ISO string
    if d.get("due_date") and isinstance(d["due_date"], date):
        d["due_date"] = d["due_date"].isoformat()
    return d


class ActivitiesPostgresRepository:
    """PostgreSQL-backed repository for activity CRUD operations."""

    def list_all(self) -> list[dict]:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM activities ORDER BY occurred_at DESC")
            rows = cur.fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_by_id(self, activity_id: str) -> dict | None:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM activities WHERE id = %s", (activity_id,))
            row = cur.fetchone()
        if row is None:
            return None
        return _row_to_dict(row)

    def create(self, data: dict) -> dict:
        activity_id = data.get("id", _generate_id())
        now = datetime.now(timezone.utc)
        occurred_at = data.get("occurred_at")
        if isinstance(occurred_at, str):
            try:
                occurred_at = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                occurred_at = now

        try:
            with get_cursor() as cur:
                cur.execute(
                    """INSERT INTO activities
                       (id, type, description, contact_name, occurred_at, due_date, status, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        activity_id,
                        data["type"],
                        data["description"],
                        data.get("contact_name"),
                        occurred_at if occurred_at else now,
                        data.get("due_date"),
                        data.get("status", "pending"),
                        now,
                        now,
                    ),
                )
        except Exception as exc:
            logger.error(
                "activities: failed to create activity id=%s — %s%s",
                activity_id,
                exc,
                _req(),
            )
            raise

        return self.get_by_id(activity_id)

    def update(self, activity_id: str, data: dict) -> dict | None:
        updatable = (
            "type",
            "description",
            "contact_name",
            "occurred_at",
            "due_date",
            "status",
        )
        fields = [k for k in updatable if k in data]

        if fields:
            set_clauses = [f"{f} = %s" for f in fields]
            values = []
            for f in fields:
                val = data[f]
                # Parse occurred_at if it's a string
                if f == "occurred_at" and isinstance(val, str):
                    try:
                        val = datetime.fromisoformat(val.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        pass
                values.append(val)
        else:
            set_clauses = []
            values = []

        set_clauses.append("updated_at = %s")
        values.append(datetime.now(timezone.utc))
        values.append(activity_id)

        try:
            with get_cursor() as cur:
                if set_clauses:
                    sql = (
                        f"UPDATE activities SET {', '.join(set_clauses)} WHERE id = %s"
                    )
                    cur.execute(sql, values)
                else:
                    cur.execute(
                        "SELECT 1 FROM activities WHERE id = %s", (activity_id,)
                    )
        except Exception as exc:
            logger.error(
                "activities: failed to update activity id=%s — %s%s",
                activity_id,
                exc,
                _req(),
            )
            raise

        return self.get_by_id(activity_id)

    def delete(self, activity_id: str) -> bool:
        try:
            with get_cursor() as cur:
                cur.execute("DELETE FROM activities WHERE id = %s", (activity_id,))
                return cur.rowcount > 0
        except Exception as exc:
            logger.error(
                "activities: failed to delete activity id=%s — %s%s",
                activity_id,
                exc,
                _req(),
            )
            raise
