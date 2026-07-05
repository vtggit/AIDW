"""Settings API routes — get and update the single application settings record."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.settings import SettingsResponse, SettingsUpdate
from app.repositories.audit_postgres_repository import AuditPostgresRepository
from app.repositories.settings_postgres_repository import SettingsPostgresRepository
from app.services.audit_service import AuditService
from app.services.settings_service import SettingsService

router = APIRouter(prefix="/api/settings", tags=["settings"])

_repository = SettingsPostgresRepository()
_audit_repository = AuditPostgresRepository()
_audit_service = AuditService(_audit_repository)
_service = SettingsService(_repository, _audit_service)


@router.get("", response_model=SettingsResponse)
def get_settings(_user: AuthUser = Depends(require_authenticated_user)):
    """Return the current application settings. Requires authentication."""
    return _service.get_settings()


@router.put("", response_model=SettingsResponse)
def update_settings(
    payload: SettingsUpdate,
    user: AuthUser = Depends(require_role(ROLE_ADMIN)),
):
    """Update application settings. Requires admin role.

    The incoming payload is merged into the existing settings record.
    """
    try:
        settings = _service.update_settings(payload, user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return settings
