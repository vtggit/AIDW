"""PostgreSQL-backed repository for Templates."""

import logging
import uuid
from datetime import datetime, timezone

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
    for key in ("created_at", "updated_at"):
        if d.get(key):
            ts = d[key]
            if isinstance(ts, datetime):
                d[key] = ts.isoformat()
    return d


class TemplatesPostgresRepository:
    """PostgreSQL-backed repository for template CRUD operations."""

    def list_all(self) -> list[dict]:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM templates ORDER BY created_at DESC")
            rows = cur.fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_by_id(self, template_id: str) -> dict | None:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM templates WHERE id = %s", (template_id,))
            row = cur.fetchone()
        if row is None:
            return None
        return _row_to_dict(row)

    def create(self, data: dict) -> dict:
        template_id = data.get("id", _generate_id())
        now = datetime.now(timezone.utc)

        try:
            with get_cursor() as cur:
                cur.execute(
                    """INSERT INTO templates
                       (id, name, category, subject, content, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (
                        template_id,
                        data["name"],
                        data.get("category", "other"),
                        data.get("subject"),
                        data.get("content", ""),
                        now,
                        now,
                    ),
                )
        except Exception as exc:
            logger.error(
                "templates: failed to create template id=%s — %s%s",
                template_id,
                exc,
                _req(),
            )
            raise

        return self.get_by_id(template_id)

    def update(self, template_id: str, data: dict) -> dict | None:
        updatable = ("name", "category", "subject", "content")
        fields = [k for k in updatable if k in data]

        if fields:
            set_clauses = [f"{f} = %s" for f in fields]
            values = [data[f] for f in fields]
        else:
            set_clauses = []
            values = []

        set_clauses.append("updated_at = %s")
        values.append(datetime.now(timezone.utc))
        values.append(template_id)

        try:
            with get_cursor() as cur:
                if set_clauses:
                    sql = f"UPDATE templates SET {', '.join(set_clauses)} WHERE id = %s"
                    cur.execute(sql, values)
                else:
                    cur.execute("SELECT 1 FROM templates WHERE id = %s", (template_id,))
        except Exception as exc:
            logger.error(
                "templates: failed to update template id=%s — %s%s",
                template_id,
                exc,
                _req(),
            )
            raise

        return self.get_by_id(template_id)

    def delete(self, template_id: str) -> bool:
        try:
            with get_cursor() as cur:
                cur.execute("DELETE FROM templates WHERE id = %s", (template_id,))
                return cur.rowcount > 0
        except Exception as exc:
            logger.error(
                "templates: failed to delete template id=%s — %s%s",
                template_id,
                exc,
                _req(),
            )
            raise
