"""Audit log API routes — read-only access to audit event history."""

from fastapi import APIRouter, Depends

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.models import AuthUser
from app.models.audit import AuditEventResponse
from app.repositories.audit_postgres_repository import AuditPostgresRepository
from app.services.audit_service import AuditService

router = APIRouter(prefix="/api/audit", tags=["audit"])

_audit_repository = AuditPostgresRepository()
_audit_service = AuditService(_audit_repository)


@router.get("", response_model=list[AuditEventResponse])
def get_audit_log(
    entity_type: str | None = None,
    limit: int = 100,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
):
    """List recent audit events. Requires admin role.

    Optionally filter by entity type and limit the number of results.
    """
    events = _audit_service.list_events(entity_type=entity_type, limit=limit)
    return [AuditEventResponse.model_validate(e.model_dump()) for e in events]
