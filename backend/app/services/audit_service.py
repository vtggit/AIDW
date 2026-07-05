"""Audit service - central place for writing audit events.

AUDIT FAILURE POLICY — Option B: Audit failure causes the mutation to fail.

    When a business mutation succeeds but the subsequent audit write fails,
    the entire operation is rolled back.  This guarantees that every persisted
    mutation has a corresponding audit record, at the cost of availability
    when the audit table is unreachable.

    Rationale:
    • Audit completeness is a compliance requirement.
    • Silent data mutations without audit trails are worse than failed mutations.
    • The audit table lives in the same database, so audit-only failures are rare.

    If the audit subsystem becomes a reliability bottleneck, the policy can be
    changed to Option A (succeed + log) with a compensating background writer.
"""

import logging

from app.models.audit import AuditEvent, AuditEventResponse
from app.observability.logging import get_request_id
from app.repositories.audit_repository import AuditRepository

logger = logging.getLogger(__name__)


def _req() -> str:
    """Return a request-ID suffix for log lines, or empty string."""
    rid = get_request_id()
    return f" request_id={rid}" if rid else ""


class AuditService:
    """Writes audit events through the repository layer.

    Audit writes are synchronous and blocking.  If the audit write fails,
    the exception propagates to the caller, which should treat the entire
    mutation as failed (see module docstring for policy rationale).
    """

    def __init__(self, repository: AuditRepository):
        self.repository = repository

    def write(self, event: AuditEvent) -> AuditEventResponse:
        """Persist an audit event.

        Raises:
            Exception: If the audit write fails. The caller should treat
                       the entire business mutation as failed.
        """
        try:
            return self.repository.write_event(event)
        except Exception as exc:
            logger.error(
                "audit: failed to write event — entity_type=%s entity_id=%s action=%s error=%s%s",
                event.entity_type,
                event.entity_id,
                event.action,
                exc,
                _req(),
            )
            raise

    def list_events(
        self,
        entity_type: str | None = None,
        limit: int = 100,
    ) -> list[AuditEventResponse]:
        """Return recent audit events."""
        return self.repository.list_events(entity_type=entity_type, limit=limit)
