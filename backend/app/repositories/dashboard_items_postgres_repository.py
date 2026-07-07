"""PostgreSQL repository for dashboard_items."""

from datetime import datetime, timezone
from uuid import uuid4

from app.db.connection import get_cursor

_COLUMNS = (
    "name",
    "dashboard_id",
    "source_suggestion_id",
    "title",
    "item_type",
    "aggregation",
    "position",
)


def _generate_id() -> str:
    return str(uuid4())


def _row_to_dict(row) -> dict:
    d = dict(row)
    for key in ("created_at", "updated_at"):
        if d.get(key) and isinstance(d[key], datetime):
            d[key] = d[key].isoformat()
    return d


class DashboardItemPostgresRepository:
    """PostgreSQL repository for the dashboard_items table."""

    def list_all(self) -> list[dict]:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM dashboard_items ORDER BY created_at DESC")
            return [_row_to_dict(r) for r in cur.fetchall()]

    def get_by_id(self, entity_id: str) -> dict | None:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM dashboard_items WHERE id = %s", (entity_id,))
            row = cur.fetchone()
            return _row_to_dict(row) if row else None

    def create(self, data: dict) -> dict:
        new_id = data.get("id", _generate_id())
        now = datetime.now(timezone.utc)
        with get_cursor() as cur:
            cur.execute(
                "INSERT INTO dashboard_items (id, name, dashboard_id, source_suggestion_id, "
                "title, item_type, aggregation, position, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    new_id,
                    data.get("name"),
                    data.get("dashboard_id"),
                    data.get("source_suggestion_id"),
                    data.get("title"),
                    data.get("item_type"),
                    data.get("aggregation"),
                    data.get("position"),
                    now,
                    now,
                ),
            )
        return self.get_by_id(new_id)

    def update(self, entity_id: str, data: dict) -> dict | None:
        fields = [k for k in _COLUMNS if k in data]
        if not fields:
            return self.get_by_id(entity_id)
        set_clauses = [f"{f} = %s" for f in fields]
        set_clauses.append("updated_at = %s")
        values = [data[f] for f in fields]
        values.append(datetime.now(timezone.utc))
        with get_cursor() as cur:
            cur.execute(
                f"UPDATE dashboard_items SET {', '.join(set_clauses)} WHERE id = %s",
                values + [entity_id],
            )
        return self.get_by_id(entity_id)

    def delete(self, entity_id: str) -> bool:
        with get_cursor() as cur:
            cur.execute("DELETE FROM dashboard_items WHERE id = %s", (entity_id,))
            return cur.rowcount > 0
