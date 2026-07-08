"""PostgreSQL repository for discovered_fields."""

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
    return d


class DiscoveredFieldPostgresRepository:
    """PostgreSQL repository for the discovered_fields table."""

    def list_all(self) -> list[dict]:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM discovered_fields ORDER BY created_at DESC")
            return [_row_to_dict(r) for r in cur.fetchall()]

    def get_by_id(self, entity_id: str) -> dict | None:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM discovered_fields WHERE id = %s", (entity_id,))
            row = cur.fetchone()
            return _row_to_dict(row) if row else None

    def create(self, data: dict) -> dict:
        new_id = data.get("id", _generate_id())
        now = datetime.now(timezone.utc)
        with get_cursor() as cur:
            cur.execute(
                "INSERT INTO discovered_fields (id, name, data_type, dataset_id, is_nullable, is_key, field_position, first_seen_run_id, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    new_id,
                    data.get("name"),
                    data.get("data_type"),
                    data.get("dataset_id"),
                    data.get("is_nullable"),
                    data.get("is_key"),
                    data.get("field_position"),
                    data.get("first_seen_run_id"),
                    now,
                    now,
                ),
            )
        return self.get_by_id(new_id)

    def update(self, entity_id: str, data: dict) -> dict | None:
        updatable = (
            "name",
            "data_type",
            "dataset_id",
            "is_nullable",
            "is_key",
            "field_position",
            "first_seen_run_id",
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
                f"UPDATE discovered_fields SET {', '.join(set_clauses)} WHERE id = %s",
                values + [entity_id],
            )
        return self.get_by_id(entity_id)

    def delete(self, entity_id: str) -> bool:
        with get_cursor() as cur:
            cur.execute("DELETE FROM discovered_fields WHERE id = %s", (entity_id,))
            return cur.rowcount > 0
