"""Suppression list & unsubscribe routes — the send-gate enforcement API (#186)."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.audit import AuditEvent
from app.models.suppressions import (
    MaySendResponse,
    SuppressionCreate,
    SuppressionResponse,
    UnsubscribeRequest,
)
from app.repositories.contacts_postgres_repository import ContactsPostgresRepository
from app.repositories.suppressions_postgres_repository import (
    SuppressionsPostgresRepository,
)

router = APIRouter(prefix="/api/suppressions", tags=["suppressions"])

_repository = SuppressionsPostgresRepository()
_contacts_repository = ContactsPostgresRepository()


def _iso(row: dict) -> dict:
    out = dict(row)
    ts = out.get("created_at")
    if hasattr(ts, "isoformat"):
        out["created_at"] = ts.isoformat()
    return out


@router.get("", response_model=list[SuppressionResponse])
def list_suppressions(
    response: Response,
    limit: int = Query(20, ge=0, le=100),
    offset: int = Query(0, ge=0),
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
):
    """List suppression entries (the #179 hardened list contract). Admin only."""
    rows = [_iso(r) for r in _repository.list_all()]
    response.headers["X-Total-Count"] = str(len(rows))
    return rows[offset : offset + limit]


@router.post(
    "", response_model=SuppressionResponse, status_code=status.HTTP_201_CREATED
)
def add_suppression(
    payload: SuppressionCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
):
    """Add an address to the suppression list. A duplicate (any case) returns 409 via the
    central UniqueViolation handler. Admin only."""
    return _iso(_repository.add(payload.email, payload.reason, payload.note))


@router.delete("/{suppression_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_suppression(
    suppression_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
):
    """Remove a suppression entry (re-enabling the address). Admin only."""
    if not _repository.remove(suppression_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Suppression {suppression_id} not found",
        )


@router.post("/unsubscribe", response_model=MaySendResponse)
def unsubscribe_contact(
    payload: UnsubscribeRequest,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
):
    """Admin-initiated unsubscribe: suppress the contact's address AND flip their consent to
    opted_out/source=unsubscribe in ONE transaction, audit-logged (#185-consistent)."""
    contact = _contacts_repository.get_by_id(payload.contact_id)
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Contact {payload.contact_id} not found",
        )
    email = contact.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Contact has no email address to unsubscribe",
        )
    _repository.unsubscribe_with_audit(
        payload.contact_id,
        email,
        AuditEvent(
            entity_type="contact",
            entity_id=payload.contact_id,
            action="consent_change",
            actor_sub=_user.sub,
            actor_username=_user.username,
            actor_email=_user.email,
            actor_roles=_user.roles,
            details={"old": "*", "new": "opted_out", "source": "unsubscribe"},
        ),
    )
    may, reasons = _repository.may_send(email)
    return MaySendResponse(email=email, may_send=may, reasons=reasons)


@router.get("/may-send", response_model=MaySendResponse)
def may_send(
    email: str = Query(min_length=3, max_length=300),
    _user: AuthUser = Depends(require_authenticated_user),
):
    """The deterministic send gate (AC-3): not suppressed AND consent opted_in. The contract
    every future send path must call before dispatching."""
    may, reasons = _repository.may_send(email)
    return MaySendResponse(email=email, may_send=may, reasons=reasons)
