"""PostgreSQL-backed repository for Leads."""

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


class LeadsPostgresRepository:
    """PostgreSQL-backed repository for lead CRUD operations."""

    def list_all(self, company_id: str | None = None) -> list[dict]:
        with get_cursor() as cur:
            if company_id is not None:
                cur.execute(
                    "SELECT * FROM leads WHERE company_id = %s ORDER BY created_at DESC",
                    (company_id,),
                )
            else:
                cur.execute("SELECT * FROM leads ORDER BY created_at DESC")
            rows = cur.fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_by_id(self, lead_id: str) -> dict | None:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM leads WHERE id = %s", (lead_id,))
            row = cur.fetchone()
        if row is None:
            return None
        return _row_to_dict(row)

    def create(self, data: dict) -> dict:
        lead_id = data.get("id", _generate_id())
        now = datetime.now(timezone.utc)

        try:
            with get_cursor() as cur:
                cur.execute(
                    """INSERT INTO leads
                       (id, name, company, email, phone, value, stage, source, notes, company_id, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        lead_id,
                        data["name"],
                        data.get("company"),
                        data.get("email"),
                        data.get("phone"),
                        data.get("value"),
                        data.get("stage", "new"),
                        data.get("source"),
                        data.get("notes"),
                        data.get("company_id"),
                        now,
                        now,
                    ),
                )
        except Exception as exc:
            logger.error(
                "leads: failed to create lead id=%s — %s%s",
                lead_id,
                exc,
                _req(),
            )
            raise

        return self.get_by_id(lead_id)

    def update(self, lead_id: str, data: dict) -> dict | None:
        updatable = (
            "name",
            "company",
            "email",
            "phone",
            "value",
            "stage",
            "source",
            "notes",
            "company_id",
        )
        fields = [k for k in updatable if k in data]

        if fields:
            set_clauses = [f"{f} = %s" for f in fields]
            values = [data[f] for f in fields]
        else:
            set_clauses = []
            values = []

        set_clauses.append("updated_at = %s")
        values.append(datetime.now(timezone.utc))
        values.append(lead_id)

        try:
            with get_cursor() as cur:
                if set_clauses:
                    sql = f"UPDATE leads SET {', '.join(set_clauses)} WHERE id = %s"
                    cur.execute(sql, values)
                else:
                    cur.execute("SELECT 1 FROM leads WHERE id = %s", (lead_id,))
        except Exception as exc:
            logger.error(
                "leads: failed to update lead id=%s — %s%s",
                lead_id,
                exc,
                _req(),
            )
            raise

        return self.get_by_id(lead_id)

    def delete(self, lead_id: str) -> bool:
        try:
            with get_cursor() as cur:
                cur.execute("DELETE FROM leads WHERE id = %s", (lead_id,))
                return cur.rowcount > 0
        except Exception as exc:
            logger.error(
                "leads: failed to delete lead id=%s — %s%s",
                lead_id,
                exc,
                _req(),
            )
            raise
