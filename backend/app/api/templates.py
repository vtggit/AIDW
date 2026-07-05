"""Templates API routes — CRUD for email template records."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.templates import TemplateCreate, TemplateResponse, TemplateUpdate
from app.repositories.audit_postgres_repository import AuditPostgresRepository
from app.repositories.templates_postgres_repository import TemplatesPostgresRepository
from app.services.audit_service import AuditService
from app.services.templates_service import TemplatesService

router = APIRouter(prefix="/api/templates", tags=["templates"])

_repository = TemplatesPostgresRepository()
_audit_repository = AuditPostgresRepository()
_audit_service = AuditService(_audit_repository)
_service = TemplatesService(_repository, _audit_service)


@router.get("", response_model=list[TemplateResponse])
def list_templates(
    response: Response,
    limit: int = Query(20, ge=0, le=100),
    offset: int = Query(0, ge=0),
    _user: AuthUser = Depends(require_authenticated_user),
):
    """List all templates. Requires authentication."""
    rows = _service.list_templates()
    response.headers["X-Total-Count"] = str(len(rows))
    return rows[offset : offset + limit]


@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
def create_template(
    payload: TemplateCreate,
    user: AuthUser = Depends(require_role(ROLE_ADMIN)),
):
    """Create a new template. Requires admin role."""
    try:
        template = _service.create_template(payload, user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return template


@router.put("/{template_id}", response_model=TemplateResponse)
def update_template(
    template_id: str,
    payload: TemplateUpdate,
    user: AuthUser = Depends(require_role(ROLE_ADMIN)),
):
    """Update an existing template. Requires admin role."""
    result = _service.update_template(template_id, payload, user)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Template not found"
        )
    return result


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(
    template_id: str,
    user: AuthUser = Depends(require_role(ROLE_ADMIN)),
):
    """Delete a template. Requires admin role."""
    deleted = _service.delete_template(template_id, user)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Template not found"
        )
    return None
