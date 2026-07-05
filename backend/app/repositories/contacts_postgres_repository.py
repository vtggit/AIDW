"""PostgreSQL-backed repository for Contacts."""

import logging
import uuid
from datetime import datetime, timezone

from app.db.connection import get_cursor
from app.observability.logging import get_request_id
from app.repositories.tags_postgres_repository import TagsPostgresRepository

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


class ContactsPostgresRepository:
    """PostgreSQL-backed repository for contact CRUD operations."""

    def __init__(self):
        self._tags_repo = TagsPostgresRepository()

    def list_all(self, company_id: str | None = None) -> list[dict]:
        with get_cursor() as cur:
            if company_id is not None:
                cur.execute(
                    "SELECT * FROM contacts WHERE company_id = %s ORDER BY created_at DESC",
                    (company_id,),
                )
            else:
                cur.execute("SELECT * FROM contacts ORDER BY created_at DESC")
            rows = cur.fetchall()
        results = []
        for r in rows:
            d = _row_to_dict(r)
            d["tags"] = self._tags_repo.get_tags_for_contact(d["id"])
            results.append(d)
        return results

    def get_by_id(self, contact_id: str, include_tags: bool = True) -> dict | None:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM contacts WHERE id = %s", (contact_id,))
            row = cur.fetchone()
        if row is None:
            return None
        d = _row_to_dict(row)
        if include_tags:
            d["tags"] = self._tags_repo.get_tags_for_contact(contact_id)
        return d

    def create(self, data: dict) -> dict:
        contact_id = data.get("id", _generate_id())
        now = datetime.now(timezone.utc)
        tag_ids = data.pop("tag_ids", [])

        try:
            with get_cursor() as cur:
                cur.execute(
                    """INSERT INTO contacts
                       (id, name, email, phone, company, status, notes, company_id, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        contact_id,
                        data["name"],
                        data.get("email"),
                        data.get("phone"),
                        data.get("company"),
                        data.get("status", "active"),
                        data.get("notes"),
                        data.get("company_id"),
                        now,
                        now,
                    ),
                )
        except Exception as exc:
            logger.error(
                "contacts: failed to create contact id=%s — %s%s",
                contact_id,
                exc,
                _req(),
            )
            raise

        if tag_ids:
            self._tags_repo.set_tags_for_contact(contact_id, tag_ids)

        return self.get_by_id(contact_id)

    def update(self, contact_id: str, data: dict) -> dict | None:
        tag_ids = data.pop("tag_ids", None)

        updatable = (
            "name",
            "email",
            "phone",
            "company",
            "status",
            "notes",
            "company_id",
        )
        fields = [k for k in updatable if k in data]
        if not fields:
            fields = []

        if fields:
            set_clauses = [f"{f} = %s" for f in fields]
            values = [data[f] for f in fields]
        else:
            set_clauses = []
            values = []

        set_clauses.append("updated_at = %s")
        values.append(datetime.now(timezone.utc))
        values.append(contact_id)

        try:
            with get_cursor() as cur:
                if set_clauses:
                    sql = f"UPDATE contacts SET {', '.join(set_clauses)} WHERE id = %s"
                    cur.execute(sql, values)
                else:
                    cur.execute("SELECT 1 FROM contacts WHERE id = %s", (contact_id,))
        except Exception as exc:
            logger.error(
                "contacts: failed to update contact id=%s — %s%s",
                contact_id,
                exc,
                _req(),
            )
            raise

        if tag_ids is not None:
            self._tags_repo.set_tags_for_contact(contact_id, tag_ids)

        return self.get_by_id(contact_id)

    def delete(self, contact_id: str) -> bool:
        try:
            with get_cursor() as cur:
                cur.execute("DELETE FROM contacts WHERE id = %s", (contact_id,))
                return cur.rowcount > 0
        except Exception as exc:
            logger.error(
                "contacts: failed to delete contact id=%s — %s%s",
                contact_id,
                exc,
                _req(),
            )
            raise

    def bulk_delete(self, contact_ids: list[str]) -> int:
        """Delete multiple contacts by ID. Returns count of deleted rows."""
        try:
            with get_cursor() as cur:
                # Also clean up tag mappings
                cur.execute(
                    "DELETE FROM contact_tag_mapping WHERE contact_id = ANY(%s)",
                    (contact_ids,),
                )
                cur.execute(
                    "DELETE FROM contacts WHERE id = ANY(%s)",
                    (contact_ids,),
                )
                return cur.rowcount
        except Exception as exc:
            logger.error(
                "contacts: failed to bulk delete ids=%s — %s%s",
                contact_ids,
                exc,
                _req(),
            )
            raise

    def bulk_update_status(self, contact_ids: list[str], status: str) -> int:
        """Update status for multiple contacts. Returns count of updated rows."""
        try:
            with get_cursor() as cur:
                cur.execute(
                    "UPDATE contacts SET status = %s, updated_at = NOW() WHERE id = ANY(%s)",
                    (status, contact_ids),
                )
                return cur.rowcount
        except Exception as exc:
            logger.error(
                "contacts: failed to bulk update status ids=%s — %s%s",
                contact_ids,
                exc,
                _req(),
            )
            raise

    def find_duplicates(self) -> list[dict]:
        """Find duplicate contacts grouped by email, phone, and name+company.

        Returns a list of dicts, each with:
            - group_id: int
            - match_type: "email" | "phone" | "name_company"
            - contacts: list[dict]  (full contact rows with tags)
        """
        groups: list[dict] = []
        group_id = 0

        # --- Email duplicates ---
        with get_cursor() as cur:
            cur.execute("""SELECT email, COUNT(*) AS cnt
                   FROM contacts WHERE email IS NOT NULL AND email != ''
                   GROUP BY email HAVING COUNT(*) > 1""")
            for row in cur.fetchall():
                group_id += 1
                contacts = []
                with get_cursor() as cur2:
                    cur2.execute(
                        "SELECT * FROM contacts WHERE email = %s ORDER BY created_at ASC",
                        (row["email"],),
                    )
                    for r in cur2.fetchall():
                        d = _row_to_dict(r)
                        d["tags"] = self._tags_repo.get_tags_for_contact(d["id"])
                        contacts.append(d)
                groups.append(
                    {"group_id": group_id, "match_type": "email", "contacts": contacts}
                )

        # --- Phone duplicates ---
        with get_cursor() as cur:
            cur.execute("""SELECT phone, COUNT(*) AS cnt
                   FROM contacts WHERE phone IS NOT NULL AND phone != ''
                   GROUP BY phone HAVING COUNT(*) > 1""")
            for row in cur.fetchall():
                group_id += 1
                contacts = []
                with get_cursor() as cur2:
                    cur2.execute(
                        "SELECT * FROM contacts WHERE phone = %s ORDER BY created_at ASC",
                        (row["phone"],),
                    )
                    for r in cur2.fetchall():
                        d = _row_to_dict(r)
                        d["tags"] = self._tags_repo.get_tags_for_contact(d["id"])
                        contacts.append(d)
                groups.append(
                    {"group_id": group_id, "match_type": "phone", "contacts": contacts}
                )

        # --- Name + Company duplicates ---
        with get_cursor() as cur:
            cur.execute(
                """SELECT LOWER(name) AS lname, LOWER(company) AS lcompany, COUNT(*) AS cnt
                   FROM contacts
                   WHERE name IS NOT NULL AND name != ''
                     AND company IS NOT NULL AND company != ''
                   GROUP BY LOWER(name), LOWER(company)
                   HAVING COUNT(*) > 1"""
            )
            for row in cur.fetchall():
                group_id += 1
                contacts = []
                with get_cursor() as cur2:
                    cur2.execute(
                        "SELECT * FROM contacts WHERE LOWER(name) = %s AND LOWER(company) = %s ORDER BY created_at ASC",
                        (row["lname"], row["lcompany"]),
                    )
                    for r in cur2.fetchall():
                        d = _row_to_dict(r)
                        d["tags"] = self._tags_repo.get_tags_for_contact(d["id"])
                        contacts.append(d)
                groups.append(
                    {
                        "group_id": group_id,
                        "match_type": "name_company",
                        "contacts": contacts,
                    }
                )

        return groups
