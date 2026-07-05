"""PostgreSQL-backed repository for contact tags."""

import logging
import uuid
from datetime import datetime, timezone

from app.db.connection import get_cursor

logger = logging.getLogger(__name__)


def _row_to_dict(row) -> dict:
    d = dict(row)
    if d.get("created_at") and isinstance(d["created_at"], datetime):
        d["created_at"] = d["created_at"].isoformat()
    return d


class TagsPostgresRepository:
    """Repository for managing contact tag definitions and mappings."""

    # ---- Tag CRUD ----

    def list_all(self) -> list[dict]:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM contact_tags ORDER BY name ASC")
            return [_row_to_dict(r) for r in cur.fetchall()]

    def get_by_id(self, tag_id: str) -> dict | None:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM contact_tags WHERE id = %s", (tag_id,))
            row = cur.fetchone()
        return _row_to_dict(row) if row else None

    def get_by_name(self, name: str) -> dict | None:
        with get_cursor() as cur:
            cur.execute(
                "SELECT * FROM contact_tags WHERE LOWER(name) = LOWER(%s)", (name,)
            )
            row = cur.fetchone()
        return _row_to_dict(row) if row else None

    def create(self, name: str, color: str = "#3b82f6") -> dict:
        tag_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        try:
            with get_cursor() as cur:
                cur.execute(
                    "INSERT INTO contact_tags (id, name, color, created_at) VALUES (%s, %s, %s, %s)",
                    (tag_id, name.strip(), color, now),
                )
        except Exception as exc:
            if "duplicate" in str(exc).lower():
                existing = self.get_by_name(name)
                if existing:
                    return existing
            raise
        return self.get_by_id(tag_id)

    def update(self, tag_id: str, data: dict) -> dict | None:
        fields = []
        values = []
        for key in ("name", "color"):
            if key in data:
                fields.append(f"{key} = %s")
                values.append(data[key])
        if not fields:
            return self.get_by_id(tag_id)

        values.append(tag_id)
        try:
            with get_cursor() as cur:
                sql = f"UPDATE contact_tags SET {', '.join(fields)} WHERE id = %s"
                cur.execute(sql, values)
        except Exception as exc:
            if "duplicate" in str(exc).lower():
                raise ValueError("Tag with this name already exists.") from exc
            raise
        return self.get_by_id(tag_id)

    def delete(self, tag_id: str) -> bool:
        with get_cursor() as cur:
            cur.execute("DELETE FROM contact_tags WHERE id = %s", (tag_id,))
            return cur.rowcount > 0

    # ---- Tag mappings (contact ↔ tag) ----

    def get_tags_for_contact(self, contact_id: str) -> list[dict]:
        with get_cursor() as cur:
            cur.execute(
                """SELECT ct.* FROM contact_tags ct
                   JOIN contact_tag_mapping ctm ON ct.id = ctm.tag_id
                   WHERE ctm.contact_id = %s
                   ORDER BY ct.name ASC""",
                (contact_id,),
            )
            return [_row_to_dict(r) for r in cur.fetchall()]

    def set_tags_for_contact(self, contact_id: str, tag_ids: list[str]) -> None:
        with get_cursor() as cur:
            cur.execute(
                "DELETE FROM contact_tag_mapping WHERE contact_id = %s", (contact_id,)
            )
            for tag_id in tag_ids:
                cur.execute(
                    "INSERT INTO contact_tag_mapping (contact_id, tag_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (contact_id, tag_id),
                )

    def get_contacts_for_tag(self, tag_id: str) -> list[str]:
        with get_cursor() as cur:
            cur.execute(
                "SELECT contact_id FROM contact_tag_mapping WHERE tag_id = %s",
                (tag_id,),
            )
            return [row[0] for row in cur.fetchall()]
