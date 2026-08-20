"""PostgreSQL repository for load_sequences."""

from datetime import datetime, timezone
from uuid import uuid4

from app.db.connection import get_cursor


def _generate_id() -> str:
    return str(uuid4())


def _row_to_dict(row) -> dict:
    d = dict(row)
    for key in ("last_fired_at", "created_at", "updated_at"):
        if d.get(key) and isinstance(d[key], datetime):
            d[key] = d[key].isoformat()
    return d


class LoadSequencePostgresRepository:
    """PostgreSQL repository for the load_sequences table."""

    def list_all(
        self, limit: int | None = None, offset: int | None = None
    ) -> list[dict]:
        sql = "SELECT * FROM load_sequences ORDER BY created_at DESC"
        params: list = []
        if limit is not None:
            sql += " LIMIT %s"
            params.append(limit)
        if offset is not None:
            sql += " OFFSET %s"
            params.append(offset)
        with get_cursor() as cur:
            cur.execute(sql, tuple(params))
            return [_row_to_dict(r) for r in cur.fetchall()]

    def get_by_id(self, entity_id: str) -> dict | None:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM load_sequences WHERE id = %s", (entity_id,))
            row = cur.fetchone()
            return _row_to_dict(row) if row else None

    def create(self, data: dict) -> dict:
        new_id = data.get("id", _generate_id())
        now = datetime.now(timezone.utc)
        with get_cursor() as cur:
            cur.execute(
                "INSERT INTO load_sequences (id, name, description, schedule_cadence, schedule_enabled, last_fired_at, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    new_id,
                    data.get("name"),
                    data.get("description"),
                    data.get("schedule_cadence"),
                    data.get("schedule_enabled"),
                    data.get("last_fired_at"),
                    now,
                    now,
                ),
            )
        return self.get_by_id(new_id)

    def update(self, entity_id: str, data: dict) -> dict | None:
        updatable = (
            "name",
            "description",
            "schedule_cadence",
            "schedule_enabled",
            "last_fired_at",
        )
        fields = [k for k in updatable if k in data]
        if not fields:
            return self.get_by_id(entity_id)
        set_clauses = [f"{f} = %s" for f in fields]
        set_clauses.append("updated_at = %s")
        values = [data[f] for f in fields]
        values.append(datetime.now(timezone.utc))
        with get_cursor() as cur:
            cur.execute(
                f"UPDATE load_sequences SET {', '.join(set_clauses)} WHERE id = %s",
                values + [entity_id],
            )
        return self.get_by_id(entity_id)

    def delete(self, entity_id: str) -> bool:
        with get_cursor() as cur:
            cur.execute("DELETE FROM load_sequences WHERE id = %s", (entity_id,))
            return cur.rowcount > 0
