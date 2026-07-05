"""Suppressions repository — the send-gate enforcement store (#186).

The unsubscribe operation (suppression insert + consent upsert + audit event) executes on
ONE cursor: get_cursor commits on clean exit and rolls back on exception, so partial
unsubscribes cannot exist. _audit_insert is the same deliberate seam shape the consent
lane proved rollback-safe.
"""

import json
import uuid
from datetime import datetime, timezone

from app.db.connection import get_cursor
from app.models.audit import AuditEvent


class SuppressionsPostgresRepository:
    """PostgreSQL repository for the suppressions table."""

    def list_all(self) -> list[dict]:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM suppressions ORDER BY created_at DESC")
            return list(cur.fetchall())

    def get_by_email(self, email: str) -> dict | None:
        with get_cursor() as cur:
            cur.execute(
                "SELECT * FROM suppressions WHERE LOWER(email) = LOWER(%s)", (email,)
            )
            return cur.fetchone()

    def add(self, email: str, reason: str, note: str | None = None) -> dict:
        """Plain INSERT — a duplicate (any case) raises UniqueViolation, which the central
        handler translates to a clear 409 naming the duplicate."""
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO suppressions (id, email, reason, note, created_at)
                   VALUES (%s, %s, %s, %s, %s) RETURNING *""",
                (str(uuid.uuid4()), email, reason, note, datetime.now(timezone.utc)),
            )
            return cur.fetchone()

    def remove(self, suppression_id: str) -> bool:
        with get_cursor() as cur:
            cur.execute("DELETE FROM suppressions WHERE id = %s", (suppression_id,))
            return cur.rowcount > 0

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

    def unsubscribe_with_audit(
        self, contact_id: str, email: str, event: AuditEvent
    ) -> dict:
        """The AC-2 transaction, on ONE cursor: idempotent suppression insert (case-
        insensitive), consent upsert to opted_out/source=unsubscribe (#185 model), audit.
        """
        now = datetime.now(timezone.utc)
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO suppressions (id, email, reason, note, created_at)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT ((LOWER(email))) DO NOTHING""",
                (str(uuid.uuid4()), email, "unsubscribed", None, now),
            )
            cur.execute(
                """INSERT INTO contact_consent
                   (id, contact_id, channel, status, source, updated_at)
                   VALUES (%s, %s, 'email', 'opted_out', 'unsubscribe', %s)
                   ON CONFLICT (contact_id, channel)
                   DO UPDATE SET status = 'opted_out',
                                 source = 'unsubscribe',
                                 updated_at = EXCLUDED.updated_at
                   RETURNING *""",
                (str(uuid.uuid4()), contact_id, now),
            )
            row = cur.fetchone()
            self._audit_insert(cur, event)
        return row

    def may_send(self, email: str) -> tuple[bool, list[str]]:
        """The send-gate contract (AC-3): NOT suppressed AND the email's contact consent is
        opted_in. Conservative v1: no contact, unknown consent, or ANY opted_out -> not
        sendable. Every future send path must call this."""
        reasons: list[str] = []
        with get_cursor() as cur:
            cur.execute(
                "SELECT reason FROM suppressions WHERE LOWER(email) = LOWER(%s)",
                (email,),
            )
            sup = cur.fetchone()
            if sup:
                reasons.append(f"suppressed: {sup['reason']}")
            cur.execute(
                """SELECT cc.status FROM contacts c
                   LEFT JOIN contact_consent cc
                          ON cc.contact_id = c.id AND cc.channel = 'email'
                   WHERE LOWER(c.email) = LOWER(%s)""",
                (email,),
            )
            statuses = [(r["status"] or "unknown") for r in cur.fetchall()]
        if not statuses:
            reasons.append("no contact record for this address")
        elif "opted_out" in statuses:
            reasons.append("contact consent: opted_out")
        elif "opted_in" not in statuses:
            reasons.append("contact consent: unknown (opt-in required)")
        return (not reasons), reasons
