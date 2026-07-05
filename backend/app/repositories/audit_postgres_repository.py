"""PostgreSQL-backed audit repository."""

import json
import logging
from datetime import datetime

from app.db.connection import get_cursor
from app.models.audit import AuditEvent, AuditEventResponse
from app.observability.logging import get_request_id
from app.repositories.audit_repository import AuditRepository

logger = logging.getLogger(__name__)


def _req() -> str:
    """Return a request-ID suffix for log lines, or empty string."""
    rid = get_request_id()
    return f" request_id={rid}" if rid else ""


def _row_to_response(row) -> AuditEventResponse:
    """Convert a database row into an AuditEventResponse."""
    d = dict(row)
    ts = d.get("timestamp")
    if isinstance(ts, datetime):
        ts = ts.isoformat()

    details = d.get("details_json")
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except (json.JSONDecodeError, TypeError):
            details = {}

    return AuditEventResponse(
        id=d["id"],
        entity_type=d["entity_type"],
        entity_id=d["entity_id"],
        action=d["action"],
        actor_sub=d["actor_sub"],
        actor_username=d.get("actor_username"),
        actor_email=d.get("actor_email"),
        actor_roles=d.get("actor_roles"),
        timestamp=str(ts),
        details=details or {},
    )


class AuditPostgresRepository(AuditRepository):
    """PostgreSQL implementation of the audit repository."""

    def write_event(self, event: AuditEvent) -> AuditEventResponse:
        roles_str = json.dumps(event.actor_roles) if event.actor_roles else None
        details_json = json.dumps(event.details) if event.details else None

        try:
            with get_cursor() as cur:
                cur.execute(
                    """INSERT INTO audit_log
                       (entity_type, entity_id, action, actor_sub,
                        actor_username, actor_email, actor_roles,
                        timestamp, details_json)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                       RETURNING id""",
                    (
                        event.entity_type,
                        event.entity_id,
                        event.action,
                        event.actor_sub,
                        event.actor_username,
                        event.actor_email,
                        roles_str,
                        event.timestamp,
                        details_json,
                    ),
                )
                row_id = cur.fetchone()["id"]
        except Exception as exc:
            logger.error(
                "audit: DB write failed — entity_type=%s entity_id=%s action=%s error=%s%s",
                event.entity_type,
                event.entity_id,
                event.action,
                exc,
                _req(),
            )
            raise

        return self._get_by_id(row_id)

    def list_events(
        self,
        entity_type: str | None = None,
        limit: int = 100,
    ) -> list[AuditEventResponse]:
        with get_cursor() as cur:
            if entity_type:
                cur.execute(
                    "SELECT * FROM audit_log WHERE entity_type = %s "
                    "ORDER BY timestamp DESC LIMIT %s",
                    (entity_type, limit),
                )
            else:
                cur.execute(
                    "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT %s",
                    (limit,),
                )
            rows = cur.fetchall()
        return [_row_to_response(r) for r in rows]

    def _get_by_id(self, row_id: int) -> AuditEventResponse:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM audit_log WHERE id = %s", (row_id,))
            row = cur.fetchone()
        return _row_to_response(row)
