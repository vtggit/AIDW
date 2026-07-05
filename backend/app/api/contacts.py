"""Contacts API routes — CRUD and bulk operations for contact records."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.models import AuthUser
from app.models.contacts import (
    BulkContactIds,
    BulkOperationResult,
    BulkStatusUpdate,
    ContactCreate,
    ContactResponse,
    ContactUpdate,
    DuplicateDetectionResponse,
)
from app.repositories.audit_postgres_repository import AuditPostgresRepository
from app.repositories.contacts_postgres_repository import ContactsPostgresRepository
from app.services.audit_service import AuditService
from app.services.contacts_service import ContactsService

router = APIRouter(prefix="/api/contacts", tags=["contacts"])

_repository = ContactsPostgresRepository()
_audit_repository = AuditPostgresRepository()
_audit_service = AuditService(_audit_repository)
_service = ContactsService(_repository, _audit_service)


@router.get("", response_model=list[ContactResponse])
def list_contacts(
    response: Response,
    limit: int = Query(20, ge=0, le=100),
    offset: int = Query(0, ge=0),
    company_id: str | None = None,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
):
    """List all contacts. Requires admin role."""
    rows = _service.list_contacts(company_id=company_id)
    response.headers["X-Total-Count"] = str(len(rows))
    return rows[offset : offset + limit]


@router.get("/duplicates", response_model=DuplicateDetectionResponse)
def find_duplicate_contacts(_user: AuthUser = Depends(require_role(ROLE_ADMIN))):
    """Find duplicate contacts grouped by email, phone, and name+company. Requires admin role."""
    groups = _repository.find_duplicates()
    total_duplicates = sum(len(g["contacts"]) for g in groups)
    return DuplicateDetectionResponse(
        total_groups=len(groups),
        total_duplicates=total_duplicates,
        groups=groups,
    )


@router.get("/{contact_id}", response_model=ContactResponse)
def get_contact(
    contact_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
):
    """Get a contact by ID. Requires admin role."""
    contact = _service.get_contact(contact_id)
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Contact {contact_id} not found",
        )
    return contact


@router.post("", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
def create_contact(
    payload: ContactCreate,
    user: AuthUser = Depends(require_role(ROLE_ADMIN)),
):
    """Create a new contact. Requires admin role."""
    try:
        contact = _service.create_contact(payload, actor=user)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    return contact


@router.put("/{contact_id}", response_model=ContactResponse)
def update_contact(
    contact_id: str,
    payload: ContactUpdate,
    user: AuthUser = Depends(require_role(ROLE_ADMIN)),
):
    """Update an existing contact. Requires admin role."""
    contact = _service.update_contact(contact_id, payload, actor=user)
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Contact {contact_id} not found",
        )
    return contact


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contact(
    contact_id: str,
    user: AuthUser = Depends(require_role(ROLE_ADMIN)),
):
    """Delete a contact. Requires admin role."""
    deleted = _service.delete_contact(contact_id, actor=user)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Contact {contact_id} not found",
        )
    return None


@router.post("/bulk-delete", response_model=BulkOperationResult)
def bulk_delete_contacts(
    payload: BulkContactIds,
    user: AuthUser = Depends(require_role(ROLE_ADMIN)),
):
    """Delete multiple contacts in a single request. Requires admin role."""
    count = _service.bulk_delete_contacts(payload.ids, actor=user)
    return BulkOperationResult(
        success_count=count,
        message=f"Successfully deleted {count} contact(s).",
    )


@router.post("/bulk-update-status", response_model=BulkOperationResult)
def bulk_update_status(
    payload: BulkStatusUpdate,
    user: AuthUser = Depends(require_role(ROLE_ADMIN)),
):
    """Update status for multiple contacts. Requires admin role."""
    count = _service.bulk_update_status(payload.ids, payload.status, actor=user)
    return BulkOperationResult(
        success_count=count,
        message=f"Successfully updated status to '{payload.status}' for {count} contact(s).",
    )
