"""PostgreSQL repository for source_credentials."""

from datetime import datetime, timezone
from uuid import uuid4

from app.audit.recorder import record_audit
from app.db.connection import get_cursor


def _generate_id() -> str:
    return str(uuid4())


def _row_to_dict(row) -> dict:
    d = dict(row)
    for key in ("created_at", "updated_at"):
        if d.get(key) and isinstance(d[key], datetime):
            d[key] = d[key].isoformat()
    return d


class SourceCredentialPostgresRepository:
    """PostgreSQL repository for the source_credentials table."""

    def list_all(self) -> list[dict]:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM source_credentials ORDER BY created_at DESC")
            return [_row_to_dict(r) for r in cur.fetchall()]

    def get_by_id(self, entity_id: str) -> dict | None:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM source_credentials WHERE id = %s", (entity_id,))
            row = cur.fetchone()
            return _row_to_dict(row) if row else None

    def create(self, data: dict, actor: str | None = None) -> dict:
        new_id = data.get("id", _generate_id())
        now = datetime.now(timezone.utc)
        with get_cursor() as cur:
            cur.execute(
                "INSERT INTO source_credentials (id, name, auth_scheme, principal, source_id, secret_ref, token_endpoint, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    new_id,
                    data.get("name"),
                    data.get("auth_scheme"),
                    data.get("principal"),
                    data.get("source_id"),
                    data.get("secret_ref"),
                    data.get("token_endpoint"),
                    now,
                    now,
                ),
            )
            if (
                actor
            ):  # same cursor: the write and its audit row commit or roll back together
                record_audit(cur, actor, "create", "source_credentials", new_id)
        return self.get_by_id(new_id)

    def update(
        self, entity_id: str, data: dict, actor: str | None = None
    ) -> dict | None:
        updatable = (
            "name",
            "auth_scheme",
            "principal",
            "source_id",
            "secret_ref",
            "token_endpoint",
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
                f"UPDATE source_credentials SET {', '.join(set_clauses)} WHERE id = %s",
                values + [entity_id],
            )
            if actor and cur.rowcount > 0:  # audit only a write that actually happened
                record_audit(
                    cur,
                    actor,
                    "update",
                    "source_credentials",
                    entity_id,
                    detail=", ".join(fields),
                )
        return self.get_by_id(entity_id)

    def delete(self, entity_id: str, actor: str | None = None) -> bool:
        with get_cursor() as cur:
            cur.execute("DELETE FROM source_credentials WHERE id = %s", (entity_id,))
            deleted = cur.rowcount > 0
            if actor and deleted:
                record_audit(cur, actor, "delete", "source_credentials", entity_id)
            return deleted
