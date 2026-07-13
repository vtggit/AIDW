"""DeletionRequest API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.models import AuthUser
from app.governance.lifecycle import WrongState, reject_request, verify_request
from app.models.deletion_requests import (
    DeletionRequestCreate,
    DeletionRequestResponse,
    DeletionRequestUpdate,
)
from app.repositories.deletion_requests_postgres_repository import (
    DeletionRequestPostgresRepository,
)
from app.services.deletion_requests_service import DeletionRequestService

router = APIRouter(prefix="/api/deletion-requests", tags=["deletion-requests"])

_repository = DeletionRequestPostgresRepository()
_service = DeletionRequestService(repository=_repository)


def get_service() -> DeletionRequestService:
    return _service


@router.get("", response_model=list[DeletionRequestResponse])
def list_deletion_requests(
    # reads are ADMIN-ONLY: subject_key is PII (#76; interim for the missing [E]-lane
    # read-restriction grammar — CodeAgent engine candidate recorded on the issue)
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DeletionRequestService = Depends(get_service),
):
    return service.list_deletion_requests()


@router.post(
    "", response_model=DeletionRequestResponse, status_code=status.HTTP_201_CREATED
)
def create_deletion_request(
    payload: DeletionRequestCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DeletionRequestService = Depends(get_service),
):
    return service.create_deletion_request(payload)


@router.get("/{entity_id}", response_model=DeletionRequestResponse)
def get_deletion_request(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),  # PII: admin-only reads (#76)
    service: DeletionRequestService = Depends(get_service),
):
    entity = service.get_deletion_request(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DeletionRequest '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=DeletionRequestResponse)
def update_deletion_request(
    entity_id: str,
    payload: DeletionRequestUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DeletionRequestService = Depends(get_service),
):
    entity = service.update_deletion_request(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DeletionRequest '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deletion_request(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DeletionRequestService = Depends(get_service),
):
    if not service.delete_deletion_request(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DeletionRequest '{entity_id}' not found.",
        )


@router.post("/{entity_id}/verify", response_model=DeletionRequestResponse)
def verify_deletion_request(
    entity_id: str,
    user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DeletionRequestService = Depends(get_service),
):
    """Identity verified off-system: received -> verifying (the claimable state). In inline
    executor mode the erasure then runs synchronously (no egress, no egress gate)."""
    try:
        found = verify_request(entity_id, actor=user.username or user.sub)
    except WrongState as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DeletionRequest '{entity_id}' not found.",
        )
    return service.get_deletion_request(entity_id)


@router.post("/{entity_id}/reject", response_model=DeletionRequestResponse)
def reject_deletion_request(
    entity_id: str,
    user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DeletionRequestService = Depends(get_service),
):
    """received|verifying -> rejected; terminal states win (409 on anything else)."""
    try:
        found = reject_request(entity_id, actor=user.username or user.sub)
    except WrongState as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DeletionRequest '{entity_id}' not found.",
        )
    return service.get_deletion_request(entity_id)
