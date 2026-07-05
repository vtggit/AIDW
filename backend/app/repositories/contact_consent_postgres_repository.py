"""Contact consent repository — normalized per-channel consent (contact_consent).

The consent mutation and its audit event execute on ONE cursor (get_cursor commits on
clean exit, rolls back on exception), so a failed audit write atomically reverts the
consent change. _audit_insert is a deliberate seam the rollback proof patches.
"""

import json
import uuid
from datetime import datetime, timezone

from app.db.connection import get_cursor
from app.models.audit import AuditEvent


class ContactConsentPostgresRepository:
    """PostgreSQL repository for the contact_consent table."""

    def get_for_contact(self, contact_id: str, channel: str = "email") -> dict | None:
        with get_cursor() as cur:
            cur.execute(
                "SELECT * FROM contact_consent WHERE contact_id = %s AND channel = %s",
                (contact_id, channel),
            )
            return cur.fetchone()

    def get_for_contacts(self, contact_ids: list, channel: str = "email") -> dict:
        if not contact_ids:
            return {}
        with get_cursor() as cur:
            cur.execute(
                "SELECT * FROM contact_consent WHERE contact_id = ANY(%s) AND channel = %s",
                (list(contact_ids), channel),
            )
            return {row["contact_id"]: row for row in cur.fetchall()}

    def _audit_insert(self, cur, event: AuditEvent) -> None:
        cur.execute(
            """INSERT INTO audit_log
               (entity_type, entity_id, action, actor_sub, actor_username,
                actor_email, actor_roles, timestamp, details_json)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                event.entity_type,
                event.entity_id,
                event.action,
                event.actor_sub,
                event.actor_username,
                event.actor_email,
                json.dumps(event.actor_roles) if event.actor_roles else None,
                event.timestamp,
                json.dumps(event.details) if event.details else None,
            ),
        )

    def set_consent_with_audit(
        self,
        contact_id: str,
        status: str,
        source: str,
        event: AuditEvent,
        channel: str = "email",
    ) -> dict:
        """Upsert the consent row AND write its audit event in one transaction."""
        now = datetime.now(timezone.utc)
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO contact_consent
                   (id, contact_id, channel, status, source, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (contact_id, channel)
                   DO UPDATE SET status = EXCLUDED.status,
                                 source = EXCLUDED.source,
                                 updated_at = EXCLUDED.updated_at
                   RETURNING *""",
                (str(uuid.uuid4()), contact_id, channel, status, source, now),
            )
            row = cur.fetchone()
            self._audit_insert(cur, event)
        return row
