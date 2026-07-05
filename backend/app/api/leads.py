"""Leads API routes."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.leads import LeadCreate, LeadResponse, LeadUpdate
from app.repositories.audit_postgres_repository import AuditPostgresRepository
from app.repositories.leads_postgres_repository import LeadsPostgresRepository
from app.services.audit_service import AuditService
from app.services.leads_service import LeadsService

router = APIRouter(prefix="/api/leads", tags=["leads"])

_repository = LeadsPostgresRepository()
_audit_repository = AuditPostgresRepository()
_audit_service = AuditService(_audit_repository)
_service = LeadsService(repository=_repository, audit_service=_audit_service)


def get_service() -> LeadsService:
    return _service


# ------------------------------------------------------------------ #
#  Routes                                                               #
# ------------------------------------------------------------------ #


@router.get("", response_model=list[LeadResponse])
def list_leads(
    response: Response,
    limit: int = Query(20, ge=0, le=100),
    offset: int = Query(0, ge=0),
    company_id: str | None = None,
    _user: AuthUser = Depends(require_authenticated_user),
    service: LeadsService = Depends(get_service),
):
    """List all leads. Requires authentication."""
    rows = service.list_leads(company_id=company_id)
    response.headers["X-Total-Count"] = str(len(rows))
    return rows[offset : offset + limit]


@router.post("", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
def create_lead(
    payload: LeadCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: LeadsService = Depends(get_service),
):
    """Create a new lead. Requires admin role."""
    try:
        return service.create_lead(payload, actor=_user)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get("/{lead_id}", response_model=LeadResponse)
def get_lead(
    lead_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: LeadsService = Depends(get_service),
):
    """Get a single lead by ID. Requires authentication."""
    lead = service.get_lead(lead_id)
    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead '{lead_id}' not found.",
        )
    return lead


@router.put("/{lead_id}", response_model=LeadResponse)
def update_lead(
    lead_id: str,
    payload: LeadUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: LeadsService = Depends(get_service),
):
    """Update a lead. Requires admin role."""
    lead = service.update_lead(lead_id, payload, actor=_user)
    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead '{lead_id}' not found.",
        )
    return lead


@router.patch("/{lead_id}/stage", response_model=LeadResponse)
def update_lead_stage(
    lead_id: str,
    payload: LeadUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: LeadsService = Depends(get_service),
):
    """Patch a lead's stage. Requires admin role. Used by Kanban drag-and-drop."""
    lead = service.update_lead(lead_id, payload, actor=_user)
    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead '{lead_id}' not found.",
        )
    return lead


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lead(
    lead_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: LeadsService = Depends(get_service),
):
    """Delete a lead. Requires admin role."""
    deleted = service.delete_lead(lead_id, actor=_user)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead '{lead_id}' not found.",
        )
