"""AuditLog API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.audit_logs import AuditLogCreate, AuditLogResponse, AuditLogUpdate
from app.repositories.audit_logs_postgres_repository import AuditLogPostgresRepository
from app.services.audit_logs_service import AuditLogService

router = APIRouter(prefix="/api/audit-logs", tags=["audit-logs"])

_repository = AuditLogPostgresRepository()
_service = AuditLogService(repository=_repository)


def get_service() -> AuditLogService:
    return _service


@router.get("", response_model=list[AuditLogResponse])
def list_audit_logs(
    _user: AuthUser = Depends(require_authenticated_user),
    service: AuditLogService = Depends(get_service),
):
    return service.list_audit_logs()


@router.post("", response_model=AuditLogResponse, status_code=status.HTTP_201_CREATED)
def create_audit_log(
    payload: AuditLogCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: AuditLogService = Depends(get_service),
):
    return service.create_audit_log(payload)


@router.get("/{entity_id}", response_model=AuditLogResponse)
def get_audit_log(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: AuditLogService = Depends(get_service),
):
    entity = service.get_audit_log(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"AuditLog '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=AuditLogResponse)
def update_audit_log(
    entity_id: str,
    payload: AuditLogUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: AuditLogService = Depends(get_service),
):
    entity = service.update_audit_log(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"AuditLog '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_audit_log(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: AuditLogService = Depends(get_service),
):
    if not service.delete_audit_log(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"AuditLog '{entity_id}' not found.",
        )
