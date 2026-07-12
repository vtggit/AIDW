"""PostgreSQL repository for pipelines."""

from datetime import datetime, timezone
from uuid import uuid4

from app.audit.recorder import record_audit
from app.db.connection import get_cursor

_COLUMNS = (
    "name",
    "dataset_id",
    "cdc_pattern",
    "schedule",
    "is_enabled",
)


def _generate_id() -> str:
    return str(uuid4())


def _row_to_dict(row) -> dict:
    d = dict(row)
    for key in ("created_at", "updated_at"):
        if d.get(key) and isinstance(d[key], datetime):
            d[key] = d[key].isoformat()
    return d


class PipelinePostgresRepository:
    """PostgreSQL repository for the pipelines table."""

    def list_all(self) -> list[dict]:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM pipelines ORDER BY created_at DESC")
            return [_row_to_dict(r) for r in cur.fetchall()]

    def get_by_id(self, entity_id: str) -> dict | None:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM pipelines WHERE id = %s", (entity_id,))
            row = cur.fetchone()
            return _row_to_dict(row) if row else None

    def create(self, data: dict, actor: str | None = None) -> dict:
        new_id = data.get("id", _generate_id())
        now = datetime.now(timezone.utc)
        with get_cursor() as cur:
            cur.execute(
                "INSERT INTO pipelines (id, name, dataset_id, cdc_pattern, schedule, "
                "is_enabled, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    new_id,
                    data.get("name"),
                    data.get("dataset_id"),
                    data.get("cdc_pattern"),
                    data.get("schedule"),
                    data.get("is_enabled"),
                    now,
                    now,
                ),
            )
            if (
                actor
            ):  # same cursor: the write and its audit row commit or roll back together
                record_audit(cur, actor, "create", "pipelines", new_id)
        return self.get_by_id(new_id)

    def update(
        self, entity_id: str, data: dict, actor: str | None = None
    ) -> dict | None:
        fields = [k for k in _COLUMNS if k in data]
        if not fields:
            return self.get_by_id(entity_id)
        set_clauses = [f"{f} = %s" for f in fields]
        set_clauses.append("updated_at = %s")
        values = [data[f] for f in fields]
        values.append(datetime.now(timezone.utc))
        with get_cursor() as cur:
            cur.execute(
                f"UPDATE pipelines SET {', '.join(set_clauses)} WHERE id = %s",
                values + [entity_id],
            )
            if actor and cur.rowcount > 0:  # audit only a write that actually happened
                record_audit(
                    cur,
                    actor,
                    "update",
                    "pipelines",
                    entity_id,
                    detail=", ".join(fields),
                )
        return self.get_by_id(entity_id)

    def delete(self, entity_id: str, actor: str | None = None) -> bool:
        with get_cursor() as cur:
            cur.execute("DELETE FROM pipelines WHERE id = %s", (entity_id,))
            deleted = cur.rowcount > 0
            if actor and deleted:
                record_audit(cur, actor, "delete", "pipelines", entity_id)
            return deleted
